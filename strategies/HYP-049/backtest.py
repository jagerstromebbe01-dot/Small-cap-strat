"""
HYP-049: Övernatt- vs. intradagsavkastning som mikrostruktursignal.

Se research/hypothesis_registry/HYP-049-overnatt-intradag-dekomponering.yaml
för det låsta kriteriet. Sjunde hypotesen testad från BATCH-002 (efter
048/051/053, i den ordning CEO angav 2026-08-09: 051 -> 049 -> 050).

MEKANISM (låst, inga fria parametrar): dela varje akties dagliga
avkastning i ÖVERNATT (dagens öppning / föregående dags stängning - 1)
och INTRADAG (dagens stängning / dagens öppning - 1). Rullande
20-handelsdagars KUMULATIV övernattavkastning minus kumulativ
intradagsavkastning per aktie. Kvartalsvis ombalansering (samma
snappade datum som resten av registret): LONG toppdecilen (övernatt
dominerar), KORT bottendecilen (intradag dominerar), likaviktat inom
vardera benet, dollarneutralt (50/50 long/kort av benets egen
allokering).

IMPLEMENTATIONSVAL, INTE FRIA PARAMETRAR I KRITERIETS MENING:
  - "Kumulativ" avkastning över 20-dagarsfönstret tolkas som SAMMANSATT
    (produkt av (1+daglig avkastning) - 1), inte en naiv summa - samma
    princip som all annan momentum-/avkastningsberäkning i registret
    (t.ex. HYP-043s close_adj.shift(a)/close_adj.shift(b)-1). Beräknas
    vektoriserat via log1p/rolling-summa/expm1 (matematiskt identiskt
    med en rullande produkt, betydligt snabbare).
  - Kriteriet specificerar öppningspris men EODHD-cachen lagrar bara ett
    RÅTT open-fält (ingen adjusted_open). Samma "motorfix 2"-princip som
    redan etablerad i HYP-037/040/042 (adjusted_open = open *
    close_adj/close, dagens egen justeringskvot) används här - annars
    skulle en verklig split ge en falsk extremavkastning i antingen
    övernatt- eller intradag-benet exakt den dag splitten sker.
  - Kvartalsvis ombalansering handlas till STÄNGNING på det snappade
    exekveringsdatumet (samma "close-to-close"-konvention som redan
    etablerad i HYP-037/043/047/053 för kvartalsvisa/kalenderdrivna
    signaler, till skillnad från HYP-042/050s explicita nästa-dags-
    öppning-krav för händelsetriggade signaler). FULL ombalansering
    varje kvartal (alla positioner stängs och byggs om från grunden) -
    kriteriet specificerar inget om att behålla kvarvarande innehav
    mellan kvartal, och en 20-dagars mikrostruktursignal byter i
    praktiken nästan hela sin sammansättning varje kvartal ändå.

KAPACITET: detta är en genuint NY small-cap-alfasignal (inte en
portföljnivå-kombination av redan befintliga ben, till skillnad från
HYP-039/041/043/044-048), och kriteriet kräver rapportering vid alla
tre kapitalnivåer separat - följer därför samma mönster som registrets
övriga fristående signaltest (HYP-008 till HYP-042/053): per-namn
dollarstorlek begränsad av en ADV-kapacitetsspärr (10% av rullande
20-dagars dollarvolym vid entrydagen, samma tröskel som resten av
registret), riktiga per-namn long- OCH kortpositioner (inte bara ett
aggregerat betamått) - resultatet BLIR alltså kapitalnivåberoende.

MOTORKRAV (låst): adjusted_close genomgående, filed-datum-korrigerat
universum, maskad adjusted_close/close-kvot, flag_implausible_liquidity(),
Corwin-Schultz-spread på entry/exit BÅDA benen, borrow_cost på kortbenets
FAKTISKA (inte antagna) dagliga notional, 3%/år - samma som resten av
registret.

DATAHYGIEN-TILLÄGG (ny för denna fil, motiverad nedan): open-fältet
rensas INTE av strategies/common/data_hygiene.py::clean_price_matrix()
(den rör bara close/high/low). En enskild orimlig rå öppningskurs (t.ex.
en vendor-datapunkt-fel) skulle annars kunna ge en extrem, falsk
övernatt-/intradagsavkastning som INTE fångas av någon redan befintlig
sanering. mask_extreme_intraday_split() nedan maskar (till NaN, aldrig
klipper/klämmer) enskilda dag-ticker-rutor där |övernatt| eller
|intradag| överstiger samma ekonomiska orimlighetströsklar som redan
används i data_hygiene.py (MIN/MAX_DAILY_RETURN, -80%/+500%) - en
öppningskurs som implicerar en sådan rörelse i endera halvan av dagen är
lika orimlig som data_hygiene.py:s befintliga dag-till-dag-filter på
close, bara tillämpad på open i stället.

POSTMORTEM-TILLÄGG (2026-08-09/10, INNAN resultatet finaliserades):
en misstänkt databugg (extrem CAGR + låg Sharpe + djup MaxDD - samma
signatur som ABWND/ARDMQ/ESSA/COL-fallen i registret) undersöktes
INNAN status sattes till passed/failed, per CEO-instruktion. Ett
enskilt dygns portföljvärde (2017-11-27, $100k-nivån) visade en falsk
+35354% avkastning på ETT LONG-innehav: tickern SSN, vars rådata
(open/high/low/close/adjusted_close SAMTIDIGT) hoppade ~54600x den
2017-11-17 (leverantörs-datafel/tickerkollision, samma kategori som
redan dokumenterade ESSA) och ALDRIG återhämtade sig resten av dess
registrerade historik. Varken clean_price_matrix()s 5-pass-begränsade
dag-till-dag-filter eller flag_implausible_liquidity()s rullande
20-dagars-fönster (kräver `window` sammanhängande giltiga dagar INNAN
det kan flagga - en kallstartsfördröjning) hann skydda just den dag en
kvartalsombalansering råkade hålla namnet. Ny, delad, ADDITIV funktion
`mask_unrecovered_price_breaks()` byggd i data_hygiene.py (ändrar INTE
befintliga funktioners beteende, så inga redan låsta hypoteser
påverkas) - se den funktionens egen docstring för fullständig
algoritmbeskrivning och verifiering mot samtliga redan kända testfall
(HEC/IDTYD/ESSA-mönstren) plus det nya SSN-mönstret. Resultatet nedan
är EFTER denna fix.
"""

import json
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
DATA_DIR = REPO_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OHLCV_DIR = CACHE_DIR / "ohlcv"
RESULTS_DIR = STRATEGY_DIR / "results"

ORIGINAL_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_by_month_filed_date.json"
EXTENSION_UNIVERSE_FILE = CACHE_DIR / "smallcap_universe_2025_extension_filed_date.json"

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
from friction import borrow_cost, corwin_schultz_spread  # noqa: E402
from data_hygiene import (  # noqa: E402
    clean_price_matrix,
    flag_implausible_liquidity,
    mask_implausible_adjusted_close_ratio,
    mask_unrecovered_price_breaks,
    MIN_DAILY_RETURN,
    MAX_DAILY_RETURN,
)
from rebalancing import snap_rebalance_dates  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2025-12-31"   # 2025 behövs för genuin blind OOS, se data_range i kriteriet

SIGNAL_WINDOW = 20          # rullande handelsdagar, låst
REBAL_FREQ = "QE"           # kvartalsvis, låst
DECILE_FRACTION = 0.10

MAX_MARKET_CAP = 2_000_000_000
ADV_WINDOW = 20
MAX_ADV_PCT = 0.10
BORROW_ANNUAL_RATE = 0.03
RF_ANNUAL = 0.02
SHARPE_FLOOR = 0.55          # låst pass_fail_criterion

OOS_START = "2025-01-01"
FULL_END_MAIN = "2024-12-31"

HEDGE = "SPY"   # bara för handelskalendern, ingen hedge-position tas (kriteriet kräver ingen)


def trading_calendar(start, end):
    df = pd.read_csv(OHLCV_DIR / f"{HEDGE}.csv", usecols=["date"], parse_dates=["date"])
    dates = df["date"].drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates[(dates >= start) & (dates <= end)])


def load_price_matrices(tickers, start, end):
    date_index = trading_calendar(start, end)
    open_s, close_s, adj_s, high_s, low_s, vol_s = {}, {}, {}, {}, {}, {}
    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "open", "close", "adjusted_close", "high", "low", "volume"],
                          parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        open_s[t] = df["open"].astype("float32")
        close_s[t] = df["close"].astype("float32")
        adj_s[t] = df["adjusted_close"].astype("float32")
        high_s[t] = df["high"].astype("float32")
        low_s[t] = df["low"].astype("float32")
        vol_s[t] = df["volume"].astype("float32")

    open_ = pd.DataFrame(open_s).reindex(date_index)
    close = pd.DataFrame(close_s).reindex(date_index)
    close_adj = pd.DataFrame(adj_s).reindex(date_index)
    high = pd.DataFrame(high_s).reindex(date_index)
    low = pd.DataFrame(low_s).reindex(date_index)
    volume = pd.DataFrame(vol_s).reindex(date_index)
    return open_, close, close_adj, high, low, volume


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def adjusted_open(open_: pd.DataFrame, close: pd.DataFrame, close_adj: pd.DataFrame) -> pd.DataFrame:
    """Samma "motorfix 2"-princip som HYP-037/040/042: skala rå open med
    dagens egen close_adj/close-kvot, annars ger en riktig split en
    fiktiv extremavkastning i övernatt- eller intradag-benet."""
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    return open_ * ratio


def mask_extreme_intraday_split(overnight_ret: pd.DataFrame, intraday_ret: pd.DataFrame):
    """Maskar (till NaN) enskilda dag-ticker-rutor där övernatt- ELLER
    intradagsavkastningen impliceras ligga utanför samma ekonomiska
    orimlighetsintervall som redan används i data_hygiene.py::clean_price_matrix
    för close (MIN/MAX_DAILY_RETURN). open-fältet saneras annars aldrig
    av den befintliga pipelinen (som bara rör close/high/low) - se
    moduldocstringen."""
    bad = ((overnight_ret < MIN_DAILY_RETURN) | (overnight_ret > MAX_DAILY_RETURN)
           | (intraday_ret < MIN_DAILY_RETURN) | (intraday_ret > MAX_DAILY_RETURN))
    return overnight_ret.mask(bad), intraday_ret.mask(bad)


def compute_score(open_, close, close_adj):
    adj_open = adjusted_open(open_, close, close_adj)
    overnight_ret = adj_open / close_adj.shift(1) - 1
    intraday_ret = close_adj / adj_open - 1
    overnight_ret, intraday_ret = mask_extreme_intraday_split(overnight_ret, intraday_ret)

    cum_overnight = np.expm1(np.log1p(overnight_ret).rolling(SIGNAL_WINDOW, min_periods=SIGNAL_WINDOW).sum())
    cum_intraday = np.expm1(np.log1p(intraday_ret).rolling(SIGNAL_WINDOW, min_periods=SIGNAL_WINDOW).sum())
    return cum_overnight - cum_intraday


def run_backtest(close, close_adj, spread_df, volume, score, universe_by_month, capital_level: float):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    calendar_dates = close.resample(REBAL_FREQ).last().index
    calendar_dates = calendar_dates[(calendar_dates >= close.index[SIGNAL_WINDOW])
                                     & (calendar_dates <= close.index[-1])]
    snapped = snap_rebalance_dates(calendar_dates, close.index)
    rebal_map = dict(zip(snapped["execution_date"], snapped["calendar_label"]))
    rebal_set = set(snapped["execution_date"])
    start_idx = close.index.get_indexer([snapped["execution_date"].iloc[0]])[0]
    trade_dates = close.index[start_idx:]

    prices_v = close_adj.values
    spread_v = spread_df.reindex(columns=tickers).values
    score_v = score.values
    dv_v = dollar_volume.values

    cash = float(capital_level)
    longs, shorts = {}, {}
    pv_list = [float(capital_level)]
    n_rebalances = 0
    n_long_total, n_short_total = 0, 0

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        cash += cash * (RF_ANNUAL / 252)

        if date in rebal_set:
            # ── Likvidera ALLA befintliga positioner (full ombalansering, se docstring) ──
            for t, h in longs.items():
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    cp = h["last_price"]
                proceeds = h["shares"] * cp
                ex_spread = spread_v[date_i, ti]
                if not np.isnan(ex_spread):
                    proceeds -= proceeds * (ex_spread / 2)
                cash += proceeds
            longs = {}

            for t, h in shorts.items():
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    cp = h["last_price"]
                buyback = h["shares"] * cp
                ex_spread = spread_v[date_i, ti]
                if not np.isnan(ex_spread):
                    buyback += buyback * (ex_spread / 2)
                cash -= buyback
            shorts = {}

            # ── Rangordna dagens eligible-universum efter score ──
            month_key = rebal_map[date].strftime("%Y-%m-%d")
            eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
            idxs = [tidx[t] for t in eligible]
            sc = pd.Series(score_v[date_i, idxs], index=eligible).dropna()

            new_long, new_short = [], []
            if len(sc) >= 20:
                ranked = sc.sort_values()
                n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
                new_short = list(ranked.index[:n_decile])
                new_long = list(ranked.index[-n_decile:])

            n_rebalances += 1
            n_long_total += len(new_long)
            n_short_total += len(new_short)

            total_equity = cash
            target_leg = 0.5 * total_equity

            # ── Öppna nya long-positioner ──
            if new_long:
                target_per_name = target_leg / len(new_long)
                for t in new_long:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dv_v[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_per_name
                    sz = min(target_per_name, cap_dollar, cash)
                    if sz < capital_level * 0.0001 or sz <= 0:
                        continue
                    en_spread = spread_v[date_i, ti]
                    effective_entry = cp * (1 + en_spread / 2) if not np.isnan(en_spread) else cp
                    shares = sz / effective_entry
                    cash -= sz
                    longs[t] = {"shares": shares, "cost": sz, "last_price": cp}

            # ── Öppna nya kort-positioner ──
            if new_short:
                target_per_name = target_leg / len(new_short)
                for t in new_short:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dv_v[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_per_name
                    sz = min(target_per_name, cap_dollar)
                    if sz < capital_level * 0.0001 or sz <= 0:
                        continue
                    en_spread = spread_v[date_i, ti]
                    effective_entry = cp * (1 - en_spread / 2) if not np.isnan(en_spread) else cp
                    shares = sz / effective_entry
                    cash += sz   # blankningslikvid mottagen
                    shorts[t] = {"shares": shares, "cost": sz, "last_price": cp}

        # ── Daglig värdering ──
        long_val = 0.0
        for t, h in longs.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            long_val += h["shares"] * cp

        short_val = 0.0
        for t, h in shorts.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            short_val += h["shares"] * cp

        daily_borrow = borrow_cost(position_value=short_val, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
        cash -= daily_borrow

        pv_list.append(cash + long_val - short_val)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    stats = {"n_rebalances": n_rebalances,
             "avg_n_long": n_long_total / n_rebalances if n_rebalances else 0.0,
             "avg_n_short": n_short_total / n_rebalances if n_rebalances else 0.0}
    return pv, stats


def sharpe(s, rf=RF_ANNUAL):
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def max_drawdown(s):
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s):
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s):
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


def main():
    print("Laddar universum (huvudserie + 2025-utökning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    tickers = sorted({t for tks in universe_merged.values() for t in tks})
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser (open/close/adjusted_close/high/low/volume)...")
    open_, close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    print(f"  {close.shape}\n")

    print("Sanerar prisdata (delad pipeline: nollpriser/orimliga engångsrörelser/volym=0)...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())

    print("Maskar oåterhämtade prisbrott (SSN-mönstret, upptäckt i denna hypotes 2026-08-09/10 - "
          "se data_hygiene.py::mask_unrecovered_price_breaks för full motivering)...")
    close = mask_unrecovered_price_breaks(close)
    high = high.where(close.notna())
    low = low.where(close.notna())
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())

    print("Flaggar leverantörs-datafel (implausibel likviditet)...")
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    open_ = open_.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Maskar orimlig (konstant) adjusted_close/close-kvot...")
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    print("Beräknar Corwin-Schultz-spread-matris...")
    spread_df = compute_spread_matrix(high, low)

    print("Beräknar övernatt/intradag-score (rullande 20-dagars kumulativ övernatt minus intradag)...")
    score = compute_score(open_, close, close_adj)

    tidx_check = {t: i for i, t in enumerate(close.columns)}
    assert set(tidx_check) == set(close.columns)

    levels = [100_000, 1_000_000, 10_000_000]
    all_results = {}

    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        pv, stats = run_backtest(close, close_adj, spread_df, volume, score, universe_merged, level)

        RESULTS_DIR.mkdir(exist_ok=True)
        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{level}.csv", header=["portfolio_value"])

        pv_main = pv.loc[:FULL_END_MAIN]
        pv_oos = pv.loc[OOS_START:FULL_END]

        r_main = {"sharpe": sharpe(pv_main), "cagr": cagr(pv_main), "max_drawdown": max_drawdown(pv_main),
                  "calmar": calmar(pv_main), "n_days": len(pv_main)}
        r_oos = {"sharpe": sharpe(pv_oos), "max_drawdown": max_drawdown(pv_oos),
                 "total_return": float(pv_oos.iloc[-1] / pv_oos.iloc[0] - 1) if len(pv_oos) > 1 else None,
                 "n_days": len(pv_oos)}

        gate = "PASS" if r_main["sharpe"] >= SHARPE_FLOOR else "FAIL"
        print(f"  Sharpe (2010-2024) = {r_main['sharpe']:.4f} ({gate} mot >= {SHARPE_FLOOR})  "
              f"CAGR={r_main['cagr']:+.2%}  MaxDD={r_main['max_drawdown']:.2%}  Calmar={r_main['calmar']:.3f}")
        print(f"  OOS-2025 (informativt): Sharpe={r_oos['sharpe']:.4f}  MaxDD={r_oos['max_drawdown']:.2%}  "
              f"Avkastning={r_oos['total_return']:+.2%}" if r_oos['total_return'] is not None else "  OOS-2025: otillräcklig data")
        print(f"  Ombalanseringar: {stats['n_rebalances']}  Snitt long/kort per ombalansering: "
              f"{stats['avg_n_long']:.1f} / {stats['avg_n_short']:.1f}\n")

        all_results[level] = {"main": r_main, "oos_2025": r_oos, "gate_pass": gate == "PASS", "stats": stats}

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
