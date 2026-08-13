"""
HYP-050: Volymchock utan prisabsorption - kortsiktig reversal med
distress-filter.

Se research/hypothesis_registry/HYP-050-volymchock-absorption-reversal.yaml
för det låsta kriteriet. Åttonde och sista hypotesen testad från
BATCH-002 i denna omgång (ordning enligt CEO 2026-08-09: 051 -> 049 -> 050).

MEKANISM (låst, inga fria parametrar): TRIGGER kontrolleras VARJE
handelsdag - en akties volym > 3x sin egen rullande 60-dagars
medianvolym, OCH samma dags absoluta avkastning ligger under 20:e
percentilen av dess egen rullande 60-dagars absolut-avkastnings-
fördelning ("mycket volym, litet prisutslag"). LONG nästa handelsdag
efter trigger, likaviktat över samtliga namn triggade samma vecka
(undviker överkoncentration i en enskild trigger-dag). Håll 7
handelsdagar (låst mittpunkt). Ingen kort sida.

IMPLEMENTATIONSVAL, INTE FRIA PARAMETRAR I KRITERIETS MENING:
  - Bade volym-baslinjen (rullande 60-dagars median) och avkastnings-
    baslinjen (rullande 60-dagars 20:e percentil) beräknas över de 60
    handelsdagarna FÖRE dagens dag (shift(1).rolling(60)), inte
    inklusive dagens egen observation - annars skulle dagens EGEN
    extremvärde blanda in sig i sin egen jämförelsebaslinje och
    systematiskt försvaga triggerns känslighet (självreferens), inte en
    look-ahead-fråga men en intern konsistensfråga.
  - "Likaviktat över samtliga namn triggade samma vecka" och "nästa
    handelsdag efter trigger" står i ett litet spänningsförhållande om
    de tolkas per enskild trigger-dag: vikten för ett namn som triggar
    på veckans MÅNDAG skulle vara okänd förrän veckans FREDAG (alla
    dagars triggers måste vara kända för att räkna ut "samtliga namn
    triggade samma vecka") - antingen kräver det framåtblick (känna
    fredagens facit på måndagen) eller en retroaktiv storleksändring av
    redan öppnade positioner. Löst genom att tillämpa "nästa handelsdag
    efter trigger" PÅ VECKONIVÅ: veckans samtliga triggers (måndag-
    fredag, snappat till narmaste faktiska handelsdag <= fredag - SAMMA
    W-FRI-mönster som redan etablerat i HYP-042) samlas till EN batch
    som handlas GEMENSAMT på första handelsdagen EFTER veckoslutet,
    likaviktat inom den batchen. Samma princip som redan etablerad i
    detta register för fönsterbaserade signaler (HYP-042: veckovis
    urval -> nästa dags öppning; HYP-053: årligt fönster -> fast
    beslutsdatum).
  - Entry sker till NÄSTA dags ÖPPNINGSKURS (adjusted_open, samma
    "motorfix 2"-princip som HYP-037/040/042/049 - open är rått i
    cachen, skalas med dagens egen close_adj/close-kvot).
  - Kapitalallokering per veckobatch: samma mönster som redan etablerat
    i HYP-042 (cash / antal nya namn den dagen) - IGENOM overlappande
    kohorter (en veckas 7-dagars-innehav kan fortfarande vara öppet när
    nästa veckas batch ska in), inte en fast bråkdel av total
    portföljekvitet.
  - DISTRESS-PROXY (för den obligatoriska, ICKE-gatande disclosuren):
    kriteriet specificerar inte HUR "finansiell distress" ska mätas.
    Registret saknar en befintlig kod-baserad distress-flagga (kollat:
    ingen i strategies/common/). Använder en ren, i förväg specificerad,
    bakåtblickande (aldrig look-ahead) prisbaserad proxy: en akties
    trailing 252-handelsdagars avkastning (på adjusted_close) vid
    triggertillfället <= -70% räknas som "distress" - konsistent med
    HYP-042:s egen diagnostiserade dödsorsak (köpa in sig i bolag som
    redan är i en STRUKTURELL, utdragen nedgång, inte ett tillfälligt
    prisfall). Disclosure-only, påverkar INTE PASS/FAIL.

MOTORKRAV (låst): samma tre grundfixar (filed-datum-universum, maskad
adjusted_close-kvot, flag_implausible_liquidity()), Corwin-Schultz-
spread på entry/exit. Ingen kort sida -> borrow_cost anropas EXPLICIT
med noll-notional (samma dokumenterade mönster som HYP-053) enbart för
att uppfylla scripts/validate_friction_usage.py:s krav att BÅDA
friktionsfunktionerna faktiskt importeras OCH anropas.

DATAHYGIEN-TILLÄGG (2026-08-09/10, byggd INNAN denna hypotes kördes
första gången - se HYP-049:s postmortem för hur den upptäcktes):
mask_unrecovered_price_breaks() (ny, delad, ADDITIV funktion i
data_hygiene.py) körs här explicit. HYP-049s efterkontroll hittade en
tickers (SSN) rådata som hoppade ~54600x på en enda dag och ALDRIG
återhämtade sig - varken clean_price_matrix()s 5-pass-begränsade
dag-till-dag-filter eller flag_implausible_liquidity()s rullande
kallstartsfördröjda fönster hann skydda mot det i tid. Extra relevant
här: denna hypotes TRIGGAR EXPLICIT på "hög volym + litet prisutslag"
- exakt den signatur en leverantörs-datafel/tickerkollisions
absorptionsliknande övergångsdagar också kan uppvisa - så samma
sanering körs FÖRE triggerberäkningen, inte i efterhand.
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
)
from rebalancing import snap_rebalance_dates  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2025-12-31"   # 2025 behövs för genuin blind OOS, se data_range i kriteriet

VOLUME_BASELINE_WINDOW = 60
ABSRET_BASELINE_WINDOW = 60
VOLUME_MULTIPLE = 3.0
ABSRET_PERCENTILE = 0.20

WEEKLY_SELECTION_FREQ = "W-FRI"
HOLD_DAYS = 7                # låst mittpunkt av 5-10-intervallet
DISTRESS_LOOKBACK_DAYS = 252
DISTRESS_RETURN_THRESHOLD = -0.70

MAX_MARKET_CAP = 2_000_000_000
ADV_WINDOW = 20
MAX_ADV_PCT = 0.10
BORROW_ANNUAL_RATE = 0.03    # oanvänd (ingen kort sida) - se explicit noll-anrop nedan
RF_ANNUAL = 0.02

SHARPE_FLOOR = 0.55           # låst pass_fail_criterion, villkor 1
MAXDD_FLOOR = -0.50            # låst pass_fail_criterion, villkor 2 (explicit tak)

OOS_START = "2025-01-01"
FULL_END_MAIN = "2024-12-31"

HEDGE = "SPY"   # bara för handelskalendern, ingen hedge-position tas


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
    """Samma "motorfix 2"-princip som HYP-037/040/042/049."""
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    return open_ * ratio


def compute_triggers(close_adj: pd.DataFrame, volume: pd.DataFrame):
    """Boolesk DataFrame, True där bade volym- och pris-absorptions-
    villkoren är uppfyllda samma dag. Baslinjerna (median-volym, 20:e
    percentil-avkastning) beräknas över de 60 handelsdagarna FÖRE dagens
    dag - se moduldocstring för motiveringen."""
    daily_ret = close_adj.pct_change()
    abs_ret = daily_ret.abs()

    median_vol_trailing = volume.shift(1).rolling(VOLUME_BASELINE_WINDOW, min_periods=VOLUME_BASELINE_WINDOW).median()
    pct20_absret_trailing = abs_ret.shift(1).rolling(ABSRET_BASELINE_WINDOW,
                                                      min_periods=ABSRET_BASELINE_WINDOW).quantile(ABSRET_PERCENTILE)

    volume_trigger = volume > (VOLUME_MULTIPLE * median_vol_trailing)
    absret_trigger = abs_ret < pct20_absret_trailing
    trigger = volume_trigger & absret_trigger & volume.notna() & abs_ret.notna() & median_vol_trailing.notna() \
        & pct20_absret_trailing.notna()
    return trigger


def compute_distress_flag(close_adj: pd.DataFrame):
    """Disclosure-only proxy (ICKE gatande) - se moduldocstring."""
    trailing_ret = close_adj / close_adj.shift(DISTRESS_LOOKBACK_DAYS) - 1
    return trailing_ret <= DISTRESS_RETURN_THRESHOLD


def build_weekly_batches(close, trigger, universe_by_month, tidx):
    """Kapitalnivå-oberoende (beror bara på trigger-matrisen och
    universumet) - beräknas EN gång i main(), inte per kapitalnivå.
    Vektoriserad över tickers (bara loop over VECKOR, inte tickers*veckor)
    för prestanda - samma numeriska resultat som en ren dubbel-loop skulle
    ge, bara snabbare."""
    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)
    day_month_idx = month_dates.searchsorted(close.index, side="right") - 1
    day_month_idx = np.clip(day_month_idx, 0, len(month_dates) - 1)

    week_ends = close.resample(WEEKLY_SELECTION_FREQ).last().index
    week_ends = week_ends[(week_ends >= close.index[max(VOLUME_BASELINE_WINDOW, ABSRET_BASELINE_WINDOW)])
                           & (week_ends <= close.index[-1])]
    snapped = snap_rebalance_dates(week_ends, close.index)
    week_end_dates = list(snapped["execution_date"])

    trigger_v = trigger.values
    di = {d: i for i, d in enumerate(close.index)}

    weekly_batches = []
    prev_end_i = di[close.index[max(VOLUME_BASELINE_WINDOW, ABSRET_BASELINE_WINDOW)]] - 1
    for we in week_end_dates:
        we_i = di[we]
        window_start_i = prev_end_i + 1
        if window_start_i > we_i:
            prev_end_i = we_i
            continue
        month_key = month_keys[day_month_idx[we_i]]
        eligible = [t for t in universe_by_month.get(month_key, []) if t in tidx]
        if eligible:
            idxs = np.array([tidx[t] for t in eligible])
            window = trigger_v[window_start_i:we_i + 1, idxs]   # (window_len, n_eligible)
            any_trig = window.any(axis=0)
            if any_trig.any():
                triggered_pos = np.where(any_trig)[0]
                first_offsets = np.argmax(window[:, triggered_pos], axis=0)
                triggered_names = [eligible[p] for p in triggered_pos]
                trigger_days = {eligible[p]: window_start_i + int(off)
                                 for p, off in zip(triggered_pos, first_offsets)}
                entry_i = we_i + 1
                if entry_i < len(close.index):
                    weekly_batches.append({"entry_i": entry_i, "names": triggered_names,
                                            "trigger_days": trigger_days})
        prev_end_i = we_i

    return weekly_batches


def run_backtest(open_, close, close_adj, spread_df, volume, weekly_batches, distress_flag,
                  universe_by_month, capital_level: float):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    open_v = adjusted_open(open_, close, close_adj).values
    prices_v = close_adj.values
    spread_v = spread_df.reindex(columns=tickers).values
    distress_v = distress_flag.values

    start_idx = weekly_batches[0]["entry_i"] if weekly_batches else max(VOLUME_BASELINE_WINDOW, ABSRET_BASELINE_WINDOW)
    trade_dates = close.index[start_idx:]

    batches_by_entry = {}
    for wb in weekly_batches:
        batches_by_entry.setdefault(wb["entry_i"], []).append(wb)

    cash = float(capital_level)
    holdings = {}
    pv_list = [float(capital_level)]
    n_triggers_total = 0
    n_distress_at_trigger = 0
    n_batches_with_entries = 0

    for date_i in range(start_idx, len(close.index)):
        date = close.index[date_i]
        cash += cash * (RF_ANNUAL / 252)

        # ── EXITS: exakt HOLD_DAYS handelsdagar efter entry ──
        for t in list(holdings.keys()):
            h = holdings[t]
            if date_i - h["entry_date_i"] < HOLD_DAYS:
                continue
            ti = tidx[t]
            cp = prices_v[date_i, ti]
            if np.isnan(cp):
                cp = h["last_price"]
            proceeds = h["shares"] * cp
            ex_spread = spread_v[date_i, ti]
            if not np.isnan(ex_spread):
                proceeds -= proceeds * (ex_spread / 2)
            cash += proceeds
            del holdings[t]

        # ── ENTRIES: dagens veckobatch(ar), till dagens oppning ──
        if date_i in batches_by_entry:
            new_names_all = []
            for b in batches_by_entry[date_i]:
                new_names_all.extend(b["names"])
            new_names = [t for t in dict.fromkeys(new_names_all) if t not in holdings]
            if new_names:
                n_batches_with_entries += 1
                target_dollar_per_name = cash / len(new_names)
                for t in new_names:
                    ti = tidx[t]
                    op = open_v[date_i, ti]
                    n_triggers_total += 1
                    for b in batches_by_entry[date_i]:
                        if t in b["trigger_days"]:
                            if distress_v[b["trigger_days"][t], ti]:
                                n_distress_at_trigger += 1
                            break
                    if np.isnan(op) or op <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
                    sz = min(target_dollar_per_name, cap_dollar, cash)
                    if sz < capital_level * 0.0001 or sz <= 0:
                        continue
                    en_spread = spread_v[date_i, ti]
                    effective_entry = op * (1 + en_spread / 2) if not np.isnan(en_spread) else op
                    shares = sz / effective_entry
                    cash -= sz
                    holdings[t] = {"shares": shares, "cost": sz, "last_price": op, "entry_date_i": date_i}

        # ── Vardering ──
        long_val = 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            long_val += h["shares"] * cp

        pv_list.append(cash + long_val)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    stats = {
        "n_weekly_batches_with_entries": n_batches_with_entries,
        "n_positions_entered": n_triggers_total,
        "n_distress_at_trigger": n_distress_at_trigger,
        "distress_fraction": (n_distress_at_trigger / n_triggers_total) if n_triggers_total else 0.0,
    }
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

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())

    print("Maskar oåterhämtade prisbrott (SSN-mönstret, upptäckt i HYP-049 2026-08-09/10 - "
          "se data_hygiene.py::mask_unrecovered_price_breaks. Extra motiverat här: denna hypotes "
          "letar EXPLICIT efter extrem volym + litet prisutslag, precis den signatur ett "
          "leverantörs-datafel/tickerkollision kan skapa vid övergångens absorptions-liknande dagar)...")
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

    print("Beräknar dagliga volymchock-/absorptionstriggers...")
    trigger = compute_triggers(close_adj, volume)
    print(f"  {int(trigger.values.sum())} ticker-dagar triggade totalt (fore eligible-filter).\n")

    print("Beräknar distress-proxy (disclosure-only)...")
    distress_flag = compute_distress_flag(close_adj)

    tickers_final = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers_final)}
    print("Bygger veckobatchar (kapitalnivå-oberoende, beräknas EN gång)...")
    weekly_batches = build_weekly_batches(close, trigger, universe_merged, tidx)
    print(f"  {len(weekly_batches)} veckobatchar med minst en trigger.\n")

    # Explicit, dokumenterat noll-anrop: ingen kort sida i denna
    # hypotes, men validate_friction_usage.py (Risk Manager-grinden)
    # kräver att BÅDA friktionsfunktionerna faktiskt importeras OCH
    # anropas - samma mönster som HYP-053.
    _zero_borrow = borrow_cost(position_value=0.0, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
    assert _zero_borrow == 0.0

    levels = [100_000, 1_000_000, 10_000_000]
    all_results = {}

    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        pv, stats = run_backtest(open_, close, close_adj, spread_df, volume, weekly_batches, distress_flag,
                                  universe_merged, level)

        RESULTS_DIR.mkdir(exist_ok=True)
        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{level}.csv", header=["portfolio_value"])

        pv_main = pv.loc[:FULL_END_MAIN]
        pv_oos = pv.loc[OOS_START:FULL_END]

        r_main = {"sharpe": sharpe(pv_main), "cagr": cagr(pv_main), "max_drawdown": max_drawdown(pv_main),
                  "calmar": calmar(pv_main), "n_days": len(pv_main)}
        r_oos = {"sharpe": sharpe(pv_oos), "max_drawdown": max_drawdown(pv_oos),
                 "total_return": float(pv_oos.iloc[-1] / pv_oos.iloc[0] - 1) if len(pv_oos) > 1 else None,
                 "n_days": len(pv_oos)}

        g1 = "PASS" if r_main["sharpe"] >= SHARPE_FLOOR else "FAIL"
        g2 = "PASS" if r_main["max_drawdown"] >= MAXDD_FLOOR else "FAIL"
        print(f"  Sharpe (2010-2024) = {r_main['sharpe']:.4f} ({g1} mot >= {SHARPE_FLOOR})  "
              f"MaxDD={r_main['max_drawdown']:.2%} ({g2} mot tak {MAXDD_FLOOR:.0%})  "
              f"CAGR={r_main['cagr']:+.2%}  Calmar={r_main['calmar']:.3f}")
        if r_oos["total_return"] is not None:
            print(f"  OOS-2025 (informativt): Sharpe={r_oos['sharpe']:.4f}  MaxDD={r_oos['max_drawdown']:.2%}  "
                  f"Avkastning={r_oos['total_return']:+.2%}")
        print(f"  Veckobatchar med entries: {stats['n_weekly_batches_with_entries']}  "
              f"Positioner totalt: {stats['n_positions_entered']}  "
              f"Distress-andel vid trigger: {stats['distress_fraction']:.1%}\n")

        all_results[level] = {
            "main": r_main, "oos_2025": r_oos,
            "condition_1_sharpe_pass": g1 == "PASS", "condition_2_maxdd_pass": g2 == "PASS",
            "stats": stats,
        }

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
