"""
HYP-053: Skatteforlust-reversering (januarieffekten).

Se research/hypothesis_registry/HYP-053-skatteforlust-reversering-januari.yaml
for det lasta kriteriet. Femte hypotesen testad fran BATCH-002.

MEKANISM (lockad, inga fria parametrar): varje ar, 15 december (eller
narmast FOREGAENDE handelsdag): rangordna det eligible small-cap-
universumet efter avkastning januari-november SAMMA ar (pa
adjusted_close). Kop den samsta decilen, likaviktat. Hall till 15
januari (eller narmast FOLJANDE handelsdag) paföljande ar. Ingen annan
signal, ingen kort sida.

Kriteriet specificerar INGEN explicit nasta-dags-oppning-exekveringslag
(till skillnad fran t.ex. HYP-042/050) - handel sker darfor direkt pa
close_adj vid de snappade beslut-/exitdatumen, samma konvention som
HYP-043/047:s redan etablerade momentum L/S-svit (ocksa close-till-
close, ingen separat oppningsexekvering).

KAPACITET: eftersom detta AR en genuint ny small-cap-alfasignal (inte
en portfoljniva-kombination av redan befintliga ben) foljer denna fil
samma monster som registrets ovriga fristaende signaltest (HYP-008
till HYP-042): per-namn dollarstorlek begransad av en ADV-kapacitetsspärr
(10% av rullande 20-dagars dollarvolym vid entrydagen), sa resultatet
BLIR kapitalnivaberoende (till skillnad fran de latta, kapitalnivå-
invarianta portfoljbenskombinationerna HYP-039/041/043/044/045/046/047/048).

Endast 15 handelsepisoder totalt (en per ar 2010-2024, ~1 manad aktiv
handel per episod) - motiverar INGEN separat OOS-2025-korning utover
vad kriteriet redan kraver (kriteriet har ingen egen OOS-2025-
gating-villkor, till skillnad fran flertalet andra hypoteser i
registret - se registerpostens result_summary for en explicit notering
om detta).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

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
from data_hygiene import clean_price_matrix, flag_implausible_liquidity, mask_implausible_adjusted_close_ratio  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2025-12-31"   # data behovs t.o.m. mitten av jan 2025 for det sista fonstret (dec-2024-episoden)

DECILE_FRACTION = 0.10
MAX_MARKET_CAP = 2_000_000_000
ADV_WINDOW = 20
MAX_ADV_PCT = 0.10
RF_ANNUAL = 0.02
BORROW_ANNUAL_RATE = 0.03   # oanvand (ingen kort sida) - se den explicita, dokumenterade noll-anropet nedan

MAXDD_WINDOW_FLOOR = -0.40   # explicit tak per kriteriet, samma motivering som HYP-050
HEDGE = "SPY"   # bara for handelskalendern, ingen hedge-position tas


def trading_calendar(start, end):
    df = pd.read_csv(OHLCV_DIR / f"{HEDGE}.csv", usecols=["date"], parse_dates=["date"])
    dates = df["date"].drop_duplicates().sort_values()
    return pd.DatetimeIndex(dates[(dates >= start) & (dates <= end)])


def load_price_matrices(tickers, start, end):
    date_index = trading_calendar(start, end)
    close_s, adj_s, high_s, low_s, vol_s = {}, {}, {}, {}, {}
    for t in tickers:
        path = OHLCV_DIR / f"{t}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path, usecols=["date", "close", "adjusted_close", "high", "low", "volume"],
                          parse_dates=["date"])
        df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
        close_s[t] = df["close"].astype("float32")
        adj_s[t] = df["adjusted_close"].astype("float32")
        high_s[t] = df["high"].astype("float32")
        low_s[t] = df["low"].astype("float32")
        vol_s[t] = df["volume"].astype("float32")

    close = pd.DataFrame(close_s).reindex(date_index)
    close_adj = pd.DataFrame(adj_s).reindex(date_index)
    high = pd.DataFrame(high_s).reindex(date_index)
    low = pd.DataFrame(low_s).reindex(date_index)
    volume = pd.DataFrame(vol_s).reindex(date_index)
    return close, close_adj, high, low, volume


def compute_spread_matrix(high, low):
    spread = {}
    for t in high.columns:
        spread[t] = corwin_schultz_spread(high[t].values, low[t].values)
    return pd.DataFrame(spread, index=high.index)


def snap_backward(label, trading_index):
    """Narmast FOREGAENDE handelsdag <= label (samma som
    rebalancing.snap_rebalance_dates men for en enskild etikett)."""
    snapped = trading_index.asof(label)
    return None if pd.isna(snapped) else snapped


def snap_forward(label, trading_index):
    """Narmast FOLJANDE handelsdag >= label - kriteriet kraver uttryckligen
    detta for 15-januari-exitdatumet (motsatt riktning mot 15-december-
    beslutsdatumet, som ska snappas BAKAT)."""
    pos = trading_index.searchsorted(label, side="left")
    if pos >= len(trading_index):
        return None
    return trading_index[pos]


def build_month_index(universe_by_month: dict):
    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)
    return month_keys, month_dates


def eligible_for_date(date, universe_by_month, month_keys, month_dates, tidx):
    idx = month_dates.searchsorted(date, side="right") - 1
    idx = max(0, min(idx, len(month_dates) - 1))
    key = month_keys[idx]
    return [t for t in universe_by_month.get(key, []) if t in tidx], key


def main():
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    tickers = sorted({t for tks in universe_merged.values() for t in tks})
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser...")
    close, close_adj, high, low, volume = load_price_matrices(tickers, FULL_START, FULL_END)
    print(f"  {close.shape}\n")

    print("Sanerar prisdata...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    print("Beräknar Corwin-Schultz-spread-matris...")
    spread_df = compute_spread_matrix(high, low)

    dollar_volume = (close * volume).rolling(ADV_WINDOW).mean()

    tidx = {t: i for i, t in enumerate(close.columns)}
    trading_index = close.index
    month_keys, month_dates = build_month_index(universe_merged)

    # ── Bygg de arliga fonstren ──
    windows = []
    for year in range(2010, 2025):
        dec_label = pd.Timestamp(f"{year}-12-15")
        jan_label = pd.Timestamp(f"{year + 1}-01-15")
        decision_date = snap_backward(dec_label, trading_index)
        exit_date = snap_forward(jan_label, trading_index)
        if decision_date is None or exit_date is None or exit_date <= decision_date:
            continue
        jan1 = pd.Timestamp(f"{year}-01-01")
        nov30 = pd.Timestamp(f"{year}-11-30")
        first_day = snap_forward(jan1, trading_index)
        last_day = snap_backward(nov30, trading_index)
        if first_day is None or last_day is None or last_day <= first_day:
            continue
        windows.append({"year": year, "decision_date": decision_date, "exit_date": exit_date,
                         "signal_start": first_day, "signal_end": last_day})

    print(f"{len(windows)} arliga fonster byggda (2010-{2010 + len(windows) - 1}).\n")

    # Explicit, dokumenterat noll-anrop: ingen kort sida i denna hypotes,
    # men validate_friction_usage.py (Risk Manager-grinden) kraver att
    # BADA friktionsfunktionerna faktiskt importeras OCH anropas i varje
    # small-cap-backtest med en ny motor - samma monster som HYP-040.
    _zero_borrow = borrow_cost(position_value=0.0, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
    assert _zero_borrow == 0.0

    levels = [100_000, 1_000_000, 10_000_000]
    all_level_results = {}

    for level in levels:
        print(f"--- Kapitalnivå: ${level:,.0f} ---")
        pv = pd.Series(float(level), index=trading_index)
        cash = float(level)
        holdings = {}
        active_mask = pd.Series(False, index=trading_index)
        window_log = []

        di = {d: i for i, d in enumerate(trading_index)}

        for w in windows:
            eligible, month_key = eligible_for_date(w["decision_date"], universe_merged, month_keys, month_dates, tidx)
            sig_start_prices = close_adj.loc[w["signal_start"], eligible]
            sig_end_prices = close_adj.loc[w["signal_end"], eligible]
            ret = (sig_end_prices / sig_start_prices - 1).dropna()
            if len(ret) < 10:
                window_log.append({"year": w["year"], "n_eligible": len(eligible), "n_names": 0,
                                    "window_return": 0.0, "window_max_drawdown": 0.0})
                continue
            ranked = ret.sort_values()
            n_decile = max(1, int(len(ranked) * DECILE_FRACTION))
            names = list(ranked.index[:n_decile])

            entry_i = di[w["decision_date"]]
            exit_i = di[w["exit_date"]]

            entry_spreads = spread_df.loc[w["decision_date"], names].dropna()
            avg_entry_spread = float(entry_spreads.mean()) if len(entry_spreads) else 0.0

            target_per_name = cash / len(names)
            sized = {}
            for t in names:
                adv = dollar_volume.loc[w["decision_date"], t] if t in dollar_volume.columns else np.nan
                cap_dollar = adv * MAX_ADV_PCT if not pd.isna(adv) else target_per_name
                sz = min(target_per_name, cap_dollar, cash)
                if sz < level * 0.0001 or sz <= 0:
                    continue
                sz *= (1 - avg_entry_spread / 2)  # halva spreaden vid entry
                sized[t] = sz

            invested = sum(sized.values())
            cash -= invested
            window_start_value = invested + cash

            window_pv = [invested + cash]
            for date_i in range(entry_i, exit_i + 1):
                date = trading_index[date_i]
                if date_i > entry_i:
                    for t in list(sized.keys()):
                        r = close_adj[t].pct_change().iloc[date_i]
                        r = 0.0 if pd.isna(r) else float(r)
                        sized[t] *= (1 + r)
                    cash *= (1 + RF_ANNUAL / 252)
                total = sum(sized.values()) + cash
                pv.loc[date] = total
                active_mask.loc[date] = True
                window_pv.append(total)

            exit_spreads = spread_df.loc[w["exit_date"], names].dropna()
            avg_exit_spread = float(exit_spreads.mean()) if len(exit_spreads) else 0.0
            exit_cost = sum(sized.values()) * (avg_exit_spread / 2)
            cash += sum(sized.values()) - exit_cost
            pv.loc[w["exit_date"]] = cash
            sized = {}

            window_pv_s = pd.Series(window_pv)
            window_dd = float(((window_pv_s - window_pv_s.cummax()) / window_pv_s.cummax()).min())
            window_ret = float(cash / window_start_value - 1) if window_start_value > 0 else 0.0

            window_log.append({"year": w["year"], "n_eligible": len(eligible), "n_names": len(sized) or len(names),
                                "window_return": window_ret, "window_max_drawdown": window_dd})

            # Utanfor fonster (mellan denna exit och nasta entry) sitter
            # portfoljen kontant, oforandrad i dollar (ingen RF-drift
            # modellerad UTANFOR aktiva fonster - kosmetiskt for
            # helhetskurvan, paverkar INTE Sharpe/MaxDD-matten nedan, som
            # per kriteriet bara raknas over de AKTIVA fonstren). Satts
            # blockvis har och skrivs over av nasta fonsters egen loop.
            pv.loc[trading_index[exit_i:]] = cash

        full_ret = pv.pct_change().dropna()
        RESULTS_DIR.mkdir(exist_ok=True)
        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{level}.csv", header=["portfolio_value"])
        pd.DataFrame(window_log).to_csv(RESULTS_DIR / f"window_log_{level}.csv", index=False)

        active_rets = full_ret[active_mask.reindex(full_ret.index, fill_value=False)]
        active_rets.to_csv(RESULTS_DIR / f"active_returns_{level}.csv", header=["ret"])
        sharpe_active = (float(np.sqrt(252) * (active_rets - RF_ANNUAL / 252).mean() / active_rets.std())
                          if active_rets.std() > 0 else 0.0)
        worst_window_dd = min((w["window_max_drawdown"] for w in window_log), default=0.0)
        annual_returns = {w["year"]: w["window_return"] for w in window_log}

        g1 = "PASS" if sharpe_active >= 0.55 else "FAIL"
        g2 = "PASS" if worst_window_dd >= MAXDD_WINDOW_FLOOR else "FAIL"
        print(f"  Aktiv-fonster-Sharpe (annualiserad) = {sharpe_active:.4f} ({g1} mot >=0.55)")
        print(f"  Varsta enskilda fonstrets MaxDD = {worst_window_dd:.2%} ({g2} mot tak -40%)")
        print(f"  Antal aktiva handelsdagar totalt: {int(active_mask.sum())} over {len(window_log)} fonster")
        for y, r in annual_returns.items():
            print(f"    {y}: {r:+.2%}")
        print()

        all_level_results[level] = {
            "capital_level": level,
            "sharpe_active_window": sharpe_active,
            "worst_window_max_drawdown": worst_window_dd,
            "n_active_days": int(active_mask.sum()),
            "n_windows": len(window_log),
            "annual_window_returns": annual_returns,
        }

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_level_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
