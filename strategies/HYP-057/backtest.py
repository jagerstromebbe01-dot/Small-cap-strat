"""
HYP-057: Etablerad lead-lag-effekt - sektorlikviditet, POSITIV riktning
(spegelvand HYP-055).

Se research/hypothesis_registry/HYP-057-etablerad-lead-lag-sektorlikviditet-positiv.yaml
for det lasta kriteriet - LAST 2026-08-10. EXAKT SAMMA MEKANISKA
INFRASTRUKTUR SOM HYP-055 (kopierad rakt av fran
strategies/HYP-055/backtest.py) - ENDA SKILLNADEN ar signalens RIKTNING:
dar HYP-055 KORTAR foljarkorgen nar ledarkorgen ar i OVERSTA kvintilen
(>= 80:e percentilen) och KOPER nar ledarkorgen ar i NEDERSTA kvintilen
(<= 20:e percentilen), gor HYP-057 tvartom - KOPER pa oversta kvintilen,
KORTAR pa nedersta. Detta isolerar om det ar signalRIKTNINGEN (positiv/
samstamd spridning, Lo & MacKinlay 1990; Cohen & Frazzini 2008) eller
negativ/substituerande spridning (HYP-055:s CEO-hypotes) som avgor
utfallet i detta universum - HYP-055:s postmortem (katastrofalt FAIL,
Sharpe -2.97/-3.00/-2.74, MaxDD -99.99%/-99.99%/-99.98% pa alla tre
nivaer) antydde bred, jamn forlust snarare an en enskild bugg, vilket
antyder att foljarkorgen faktiskt ROR SIG MED ledarkorgen (positiv
spridning) snarare an mot den - denna hypotes testar det direkt.

All ovrig mekanik (branschgruppering, tredjedelsuppdelning, 5-dagars
ledaravkastning, 504-dagars 2-ars-fordelning, kvintiltroskar, 5-dagars
hallperiod, friktion, motorkrav, ADV-kapacitetstak) ar OFORANDRAD fran
HYP-055 - bara IMPLEMENTATIONSVAL (dokumenterade nedan, inte fria
parametrar i kriteriets mening) aterstar, identiska med HYP-055.

MEKANISM I KORTHET (fullstandig text i YAML:n):
  1. Varje vecka, inom varje SIC-branschgrupp (2-siffrig SIC-huvudgrupp,
     strategies/common/sector.py::load_ticker_major_group - samma
     funktion som redan anvands av HYP-036/attribution.py): rangordna
     eligible-namn (fran filed-datum-universumet) efter 60-dagars
     genomsnittlig dollarvolym (adjusted_close x volume). Oversta
     tredjedelen = "ledare", nedersta tredjedelen = "foljare". Bara
     branscher med >= 6 eligible namn (efter att namn utan giltig
     60-dagars volymdata rensats bort) deltar den veckan.
  2. Ledarkorgens (likaviktade, pa adjusted_close) 5-handelsdagars
     trailing-avkastning (per namn: pris idag / pris for 5 handelsdagar
     sedan - 1, sedan likaviktat medelvarde over ledarna) beraknas VARJE
     VECKA per bransch.
  3. Detta varde jamfors mot branschens EGEN rullande 2-ars (504
     handelsdagars) historik av SAMMA veckovisa matt - >= 80:e
     percentilen -> KORTA foljarkorgen kommande 5 handelsdagar,
     <= 20:e percentilen -> KOP foljarkorgen, annars ingen position.
  4. Positioner over samtliga kvalificerande branscher kombineras
     likaviktat (branschexponeringar normaliseras sa att ingen enskild
     bransch dominerar). Redan oppna positioner vars 5-dagarsperiod inte
     lopt ut halls oforandrade - ingen ny signalkontroll for dem.

IMPLEMENTATIONSVAL, INTE FRIA PARAMETRAR I KRITERIETS MENING:
  - "Rullande 2-ars (504 handelsdagars) fordelning" av ett matt som
    SJALVT bara beraknas VECKOVIS (inte dagligen) tolkas har som: samla
    branschens egna veckovisa observationer vars handelsdags-POSITION
    (inte kalenderdatum) ligger inom [aktuell_position-503,
    aktuell_position] (dvs. en literal 504-handelsdagars fonster pa den
    riktiga handelskalendern, INTE en 100-nagot-veckors-observationer-
    approximation) - samma "504 handelsdagar" som resten av registret
    anvander (t.ex. HYP-051:s dispersionsfonster), bara applicerat pa en
    i grunden veckovis, inte daglig, matt-serie. Percentilen ar andelen
    OVRIGA observationer i fonstret som ar STRIKT mindre an dagens
    (samma konvention som HYP-051:s rolling_percentile/_pct_rank).
  - "Fullt fonster" (varmkorning) tolkas branschspecifikt: en bransch
    kan borja trigga forst nar dess EGEN forsta kvalificerande vecka
    ligger >= 504 handelsdagar tillbaka (samma "min_periods=window"-
    princip som resten av registret anvander for rullande fonster,
    oversatt fran daglig till veckovis samplingstakt).
  - Entry sker till NASTA handelsdags OPPNINGSKURS (adjusted_open, samma
    "motorfix 2"-princip som HYP-037/040/042/049/050) - signalen kands
    vid veckoslutets stangning, exekveras forst nasta handelsdag.
  - Position "hallperiod" mats EXAKT som i HYP-050 (samma
    "date_i - entry_date_i >= HOLD_DAYS"-monster): entry-dagen fangar
    open->close, varje foljande dag fangar close->close, exit sker DEN
    dag hallperioden lopt ut (dess EGEN dags avkastning inraknas i
    exit-varderingen) - 5 handelsdagar totalt fran entry till exit.
  - Kapitalallokering: cash / antal NYA branschpositioner den dagen
    (samma monster som HYP-042/050), inte en fast bracdel av total
    portfoljekvitet - later overlappande kohorter samexistera.
  - KAPACITETSSPARR (ADV-tak): eftersom detta ar en small-cap-hypotes
    med tested_capital_levels 100k/1M/10M (spec §2, princip 3 - friktion
    OCH kapacitet fran dag ett, inte bolagen i efterhand) och kriteriet
    i sig inte specificerar en storlek-mekanism, ateranvands SAMMA
    ADV-tak (rullande 20-dagars dollarvolym x 10%, MAX_ADV_PCT) som
    redan etablerat i HYP-037/050 - annars skulle alla tre kapitalnivaer
    ge identiska resultat, vilket vore en dold, oredovisad avvikelse
    fran hur resten av registret hanterar smacap-kapacitet.
  - Foljarkorgens dagliga avkastning ar likaviktad over de namn som har
    giltig data den dagen (NaN-namn exkluderas, INTE satta till 0 -
    "0 om alla NaN"-fallbacket anvands bara om HELA korgen saknar data
    den dagen, samma monster som HYP-043/051s daily_r-hantering).
  - Okand SIC ("XX") behandlas som sin EGEN bransch, exkluderas ALDRIG
    tyst - identisk princip som redan etablerad i
    strategies/common/sector.py::load_ticker_major_group() och anvand
    av HYP-036.

MOTORKRAV (last): filed-datum-universum, maskad adjusted_close-kvot,
mask_unrecovered_price_breaks(), flag_implausible_liquidity() (samtliga
fyra, se kriteriets MOTORKRAV-stycke), Corwin-Schultz-spread pa
entry/exit BADA benen, borrow_cost (3%/ar) pa kortbenet.
"""

import json
import sys
import warnings
from collections import defaultdict
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
from sector import load_ticker_major_group  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2025-12-31"   # 2025 kravs for genuin blind OOS, se data_range i kriteriet

LIQUIDITY_WINDOW = 60          # dagar, ledare/foljare-rankning (last)
MIN_ELIGIBLE_PER_GROUP = 6     # last
LEADER_RET_WINDOW = 5          # handelsdagar, last
DIST_WINDOW = 504              # 2 ar, last
TOP_QUINTILE = 0.80            # last
BOTTOM_QUINTILE = 0.20         # last
HOLD_DAYS = 5                  # last

WEEKLY_SELECTION_FREQ = "W-FRI"

MAX_MARKET_CAP = 2_000_000_000
ADV_WINDOW = 20
MAX_ADV_PCT = 0.10
BORROW_ANNUAL_RATE = 0.03    # last, kriteriets friktionsmetodik
RF_ANNUAL = 0.02

SHARPE_FLOOR = 0.55            # last pass_fail_criterion, villkor 1
MAXDD_FLOOR = -0.50            # last pass_fail_criterion, villkor 2 (explicit tak)

OOS_START = "2025-01-01"
FULL_END_MAIN = "2024-12-31"

K_TOTAL_TRIALS = 56           # k_total_hypotheses_before_this (55) + 1, se YAML

HEDGE = "SPY"   # bara for handelskalendern, ingen hedge-position tas


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
    """Samma "motorfix 2"-princip som HYP-037/040/042/049/050."""
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    return open_ * ratio


def build_weekly_group_signals(close_adj: pd.DataFrame, dollar_vol_60: pd.DataFrame,
                                universe_by_month: dict, major_group_map: dict):
    """
    Bygger, for VARJE bransch, en tidsserie av veckovisa observationer
    (ledarkorgens 5-dagars trailing-avkastning) och, dar branschens egen
    504-handelsdagars historik ar tillrackligt fylld, det darav harledda
    kop/salj/inget-signal-beslutet.

    Returnerar:
      weekly_signals: dict entry_date_i -> lista av
          {"group": g, "direction": "long"/"short", "names": foljare}
      diag: diagnostik for den obligatoriska disclosuren + sanity-check
    """
    tidx = {t: i for i, t in enumerate(close_adj.columns)}
    idx = close_adj.index
    close_adj_v = close_adj.values
    dv_v = dollar_vol_60.values

    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)
    day_month_idx = month_dates.searchsorted(idx, side="right") - 1
    day_month_idx = np.clip(day_month_idx, 0, len(month_dates) - 1)

    week_ends = close_adj.resample(WEEKLY_SELECTION_FREQ).last().index
    warmup = max(LIQUIDITY_WINDOW, LEADER_RET_WINDOW)
    week_ends = week_ends[(week_ends >= idx[warmup]) & (week_ends <= idx[-1])]
    snapped = snap_rebalance_dates(week_ends, idx)
    week_snap_dates = list(snapped["execution_date"])

    di = {d: i for i, d in enumerate(idx)}

    # ---- Steg 1: branschgruppering + veckovis matt-serie ----
    group_history = defaultdict(list)   # group -> [{"week_pos", "value", "followers"}]
    n_weeks_evaluated = 0
    n_weeks_any_qualifying_group = 0
    qualifying_group_counts = []

    for we in week_snap_dates:
        we_i = di[we]
        if we_i < LEADER_RET_WINDOW:
            continue
        n_weeks_evaluated += 1
        month_key = month_keys[day_month_idx[we_i]]
        eligible_all = [t for t in universe_by_month.get(month_key, []) if t in tidx]
        if not eligible_all:
            continue

        groups = defaultdict(list)
        for t in eligible_all:
            g = major_group_map.get(t, "XX")
            groups[g].append(t)

        n_qualifying_this_week = 0
        for g, members in groups.items():
            member_idxs = np.array([tidx[t] for t in members])
            dv_row = dv_v[we_i, member_idxs]
            valid = ~np.isnan(dv_row)
            if valid.sum() < MIN_ELIGIBLE_PER_GROUP:
                continue
            valid_members = [members[i] for i in range(len(members)) if valid[i]]
            valid_dv = dv_row[valid]
            order = np.argsort(-valid_dv)   # fallande, storst dollarvolym forst
            ranked = [valid_members[i] for i in order]
            third = len(ranked) // 3
            if third < 2:
                continue
            leaders = ranked[:third]
            followers = ranked[-third:]

            leader_idxs = np.array([tidx[t] for t in leaders])
            p_now = close_adj_v[we_i, leader_idxs]
            p_then = close_adj_v[we_i - LEADER_RET_WINDOW, leader_idxs]
            with np.errstate(invalid="ignore", divide="ignore"):
                rets = p_now / p_then - 1.0
            rets = rets[~np.isnan(rets) & ~np.isinf(rets)]
            if len(rets) == 0:
                continue
            value = float(rets.mean())

            n_qualifying_this_week += 1
            group_history[g].append({"week_pos": we_i, "value": value, "followers": followers})

        qualifying_group_counts.append(n_qualifying_this_week)
        if n_qualifying_this_week > 0:
            n_weeks_any_qualifying_group += 1

    # ---- Steg 2: rullande 2-ars (504-handelsdagars) percentil per bransch, beslut ----
    weekly_signals = defaultdict(list)
    trigger_weeks = set()
    n_long_triggers = 0
    n_short_triggers = 0

    for g, hist in group_history.items():
        week_positions = [h["week_pos"] for h in hist]
        values = [h["value"] for h in hist]
        n = len(hist)
        if n == 0:
            continue
        first_pos = week_positions[0]
        start = 0
        for i in range(n):
            wp = week_positions[i]
            lo = wp - (DIST_WINDOW - 1)
            while week_positions[start] < lo:
                start += 1
            if wp - first_pos < DIST_WINDOW - 1:
                continue
            window = values[start:i + 1]
            if len(window) < 2:
                continue
            cur = window[-1]
            n_less = sum(1 for v in window[:-1] if v < cur)
            pct = n_less / (len(window) - 1)

            # HYP-057: SPEGELVAND mot HYP-055 - detta ar den ENDA
            # funktionella skillnaden mellan de tva filerna. HYP-055:
            # oversta kvintilen -> "short", nedersta -> "long".
            # HYP-057 (positiv/samstamd spridning): oversta kvintilen
            # -> "long" (KOP foljarkorgen), nedersta -> "short" (KORTA).
            direction = None
            if pct >= TOP_QUINTILE:
                direction = "long"
                n_long_triggers += 1
            elif pct <= BOTTOM_QUINTILE:
                direction = "short"
                n_short_triggers += 1
            if direction is None:
                continue

            entry_i = wp + 1
            if entry_i >= len(idx):
                continue
            weekly_signals[entry_i].append({"group": g, "direction": direction, "names": hist[i]["followers"]})
            trigger_weeks.add(wp)

    diag = {
        "n_weeks_evaluated": n_weeks_evaluated,
        "n_weeks_any_qualifying_group": n_weeks_any_qualifying_group,
        "frac_weeks_any_qualifying_group": (n_weeks_any_qualifying_group / n_weeks_evaluated) if n_weeks_evaluated else 0.0,
        "avg_qualifying_groups_per_week": float(np.mean(qualifying_group_counts)) if qualifying_group_counts else 0.0,
        "n_weeks_any_trigger": len(trigger_weeks),
        "frac_weeks_any_trigger": (len(trigger_weeks) / n_weeks_evaluated) if n_weeks_evaluated else 0.0,
        "n_distinct_groups_seen": len(group_history),
        "n_long_triggers": n_long_triggers,
        "n_short_triggers": n_short_triggers,
        "n_triggers_total": n_long_triggers + n_short_triggers,
    }
    return weekly_signals, diag


def run_backtest(open_, close, close_adj, spread_df, adv_cap, weekly_signals, capital_level: float):
    tickers = list(close_adj.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    daily_ret_v = close_adj.pct_change().values
    open_adj = adjusted_open(open_, close, close_adj)
    entry_day_ret_v = (close_adj / open_adj - 1.0).values
    spread_v = spread_df.reindex(columns=tickers).values
    adv_cap_v = adv_cap.reindex(columns=tickers).values

    if not weekly_signals:
        raise RuntimeError("inga veckosignaler byggda - kan inte kora backtest")

    start_idx = min(weekly_signals.keys())
    trade_dates = close_adj.index[start_idx:]

    cash = float(capital_level)
    positions = {}   # group -> {"direction","names","entry_date_i","value"}
    pv_list = [float(capital_level)]
    open_position_counts = []
    n_new_entries = 0
    n_weeks_with_entry_batch = 0
    n_signals_skipped_already_open = 0
    n_signals_skipped_too_small = 0

    for date_i in range(start_idx, len(close_adj.index)):
        cash += cash * (RF_ANNUAL / 252)

        # ---- EXITS: hallperioden (HOLD_DAYS handelsdagar) har lopt ut ----
        for g in list(positions.keys()):
            pos = positions[g]
            days_held = date_i - pos["entry_date_i"]
            if days_held < HOLD_DAYS:
                continue
            idxs = np.array([tidx[t] for t in pos["names"] if t in tidx])
            rets_today = daily_ret_v[date_i, idxs]
            valid = ~np.isnan(rets_today)
            basket_ret = float(rets_today[valid].mean()) if valid.any() else 0.0
            sign = 1.0 if pos["direction"] == "long" else -1.0
            pos["value"] *= (1.0 + sign * basket_ret)
            if pos["direction"] == "short":
                pos["value"] -= borrow_cost(position_value=max(pos["value"], 0.0), holding_days=1,
                                             annual_rate=BORROW_ANNUAL_RATE)
            ex_spreads = spread_v[date_i, idxs]
            valid_s = ~np.isnan(ex_spreads)
            avg_ex_spread = float(ex_spreads[valid_s].mean()) if valid_s.any() else 0.0
            pos["value"] *= (1.0 - avg_ex_spread / 2.0)
            cash += pos["value"]
            del positions[g]

        # ---- ENTRIES: dagens nya branschsignaler (redan oppna hoppas over) ----
        todays_signals = weekly_signals.get(date_i, [])
        new_signals = []
        for sig in todays_signals:
            if sig["group"] in positions:
                n_signals_skipped_already_open += 1
            else:
                new_signals.append(sig)

        if new_signals:
            n_weeks_with_entry_batch += 1
            target_per_group = cash / len(new_signals)
            for sig in new_signals:
                g, direction, names = sig["group"], sig["direction"], sig["names"]
                idxs = np.array([tidx[t] for t in names if t in tidx])
                if len(idxs) == 0:
                    continue
                cap_row = adv_cap_v[date_i, idxs]
                cap_total = np.nansum(cap_row) if not np.all(np.isnan(cap_row)) else 0.0
                realized = min(target_per_group, cap_total, cash) if cap_total > 0 else 0.0
                if realized < capital_level * 0.0001 or realized <= 0:
                    n_signals_skipped_too_small += 1
                    continue

                en_spreads = spread_v[date_i, idxs]
                valid_s = ~np.isnan(en_spreads)
                avg_en_spread = float(en_spreads[valid_s].mean()) if valid_s.any() else 0.0
                value = realized * (1.0 - avg_en_spread / 2.0)

                rets0 = entry_day_ret_v[date_i, idxs]
                valid0 = ~np.isnan(rets0)
                basket_ret0 = float(rets0[valid0].mean()) if valid0.any() else 0.0
                sign = 1.0 if direction == "long" else -1.0
                value *= (1.0 + sign * basket_ret0)
                if direction == "short":
                    value -= borrow_cost(position_value=max(value, 0.0), holding_days=1,
                                          annual_rate=BORROW_ANNUAL_RATE)

                cash -= realized
                positions[g] = {"direction": direction, "names": names, "entry_date_i": date_i, "value": value}
                n_new_entries += 1

        # ---- Daglig vardering for positioner som varken oppnades eller stangdes idag ----
        for g, pos in positions.items():
            if date_i - pos["entry_date_i"] == 0:
                continue   # entry-dagens avkastning redan applicerad ovan
            idxs = np.array([tidx[t] for t in pos["names"] if t in tidx])
            rets_today = daily_ret_v[date_i, idxs]
            valid = ~np.isnan(rets_today)
            basket_ret = float(rets_today[valid].mean()) if valid.any() else 0.0
            sign = 1.0 if pos["direction"] == "long" else -1.0
            pos["value"] *= (1.0 + sign * basket_ret)
            if pos["direction"] == "short":
                pos["value"] -= borrow_cost(position_value=max(pos["value"], 0.0), holding_days=1,
                                             annual_rate=BORROW_ANNUAL_RATE)

        open_position_counts.append(len(positions))
        total_positions_value = sum(p["value"] for p in positions.values())
        pv_list.append(cash + total_positions_value)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    stats = {
        "n_new_entries": n_new_entries,
        "n_weeks_with_entry_batch": n_weeks_with_entry_batch,
        "n_signals_skipped_already_open": n_signals_skipped_already_open,
        "n_signals_skipped_too_small": n_signals_skipped_too_small,
        "avg_open_positions_per_day": float(np.mean(open_position_counts)) if open_position_counts else 0.0,
        "max_open_positions": int(np.max(open_position_counts)) if open_position_counts else 0,
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
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
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

    print("Sanerar prisdata (clean_price_matrix)...")
    close, high, low = clean_price_matrix(close, high, low, volume=volume)
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())

    print("Maskar oaterhamtade prisbrott (mask_unrecovered_price_breaks)...")
    close = mask_unrecovered_price_breaks(close)
    high = high.where(close.notna())
    low = low.where(close.notna())
    close_adj = close_adj.where(close.notna())
    open_ = open_.where(close.notna())

    print("Flaggar leverantors-datafel (flag_implausible_liquidity)...")
    implausible = flag_implausible_liquidity(close, volume, max_market_cap=MAX_MARKET_CAP,
                                              window=ADV_WINDOW, multiplier=1.0)
    close = close.mask(implausible)
    close_adj = close_adj.mask(implausible)
    open_ = open_.mask(implausible)
    high = high.mask(implausible)
    low = low.mask(implausible)

    print("Maskar orimlig (konstant) adjusted_close/close-kvot...")
    close_adj = mask_implausible_adjusted_close_ratio(close, close_adj)

    print("Beraknar Corwin-Schultz-spread-matris...")
    spread_df = compute_spread_matrix(high, low)

    print("Laddar SIC-huvudgruppsklassificering (strategies/common/sector.py)...")
    major_group_map = load_ticker_major_group(list(close_adj.columns))
    n_known = sum(1 for mg in major_group_map.values() if mg != "XX")
    print(f"  {n_known}/{len(major_group_map)} tickers har kand SIC-huvudgrupp "
          f"({len(set(major_group_map.values()))} distinkta grupper inkl. XX).\n")

    print("Beraknar 60-dagars genomsnittlig dollarvolym (adjusted_close x volume, ledare/foljare-rankning)...")
    dollar_vol_60 = (close_adj * volume).rolling(LIQUIDITY_WINDOW, min_periods=LIQUIDITY_WINDOW).mean()

    print("Beraknar 20-dagars ADV-kapacitetstak (close x volume x 10%, samma konvention som HYP-037/050)...")
    adv_cap = (close * volume).rolling(ADV_WINDOW, min_periods=ADV_WINDOW).mean() * MAX_ADV_PCT

    print("Bygger veckovisa branschsignaler (ledare/foljare + 504-dagars regimkvintil)...")
    weekly_signals, diag = build_weekly_group_signals(close_adj, dollar_vol_60, universe_merged, major_group_map)
    print(f"  Veckor utvarderade: {diag['n_weeks_evaluated']}")
    print(f"  Veckor med >=1 kvalificerande bransch (>=6 eligible): {diag['n_weeks_any_qualifying_group']} "
          f"({diag['frac_weeks_any_qualifying_group']:.1%})")
    print(f"  Genomsnittligt antal kvalificerande branscher/vecka: {diag['avg_qualifying_groups_per_week']:.2f}")
    print(f"  Distinkta branscher sedda totalt: {diag['n_distinct_groups_seen']}")
    print(f"  Veckor med >=1 TRIGGER (kop eller sälj): {diag['n_weeks_any_trigger']} "
          f"({diag['frac_weeks_any_trigger']:.1%})")
    print(f"  Triggers totalt: {diag['n_triggers_total']} (long={diag['n_long_triggers']}, "
          f"short={diag['n_short_triggers']})\n")

    if diag["n_triggers_total"] == 0:
        raise RuntimeError("SANITY-CHECK MISSLYCKADES: inga triggers alls genererades - "
                            "mekanismen exercerades aldrig, nagot ar troligen fel i implementationen.")

    levels = [100_000, 1_000_000, 10_000_000]
    all_results = {}
    RESULTS_DIR.mkdir(exist_ok=True)

    for level in levels:
        print(f"--- Kapitalniva: ${level:,.0f} ---")
        pv, stats = run_backtest(open_, close, close_adj, spread_df, adv_cap, weekly_signals, level)

        pv.to_csv(RESULTS_DIR / f"portfolio_value_full_{level}.csv", header=["portfolio_value"])

        pv_main = pv.loc[:FULL_END_MAIN]
        pv_oos = pv.loc[OOS_START:FULL_END]

        r_main = {"sharpe": sharpe(pv_main), "cagr": cagr(pv_main), "max_drawdown": max_drawdown(pv_main),
                  "calmar": calmar(pv_main), "n_days": len(pv_main)}
        r_oos = {"sharpe": sharpe(pv_oos), "max_drawdown": max_drawdown(pv_oos),
                 "total_return": float(pv_oos.iloc[-1] / pv_oos.iloc[0] - 1) if len(pv_oos) > 1 else None,
                 "n_days": len(pv_oos)}

        main_returns = pv_main.pct_change().dropna().values
        dsr_result = deflated_sharpe_ratio_from_returns(main_returns, n_trials=K_TOTAL_TRIALS,
                                                          risk_free_per_period=RF_ANNUAL / 252)

        g1 = "PASS" if r_main["sharpe"] >= SHARPE_FLOOR else "FAIL"
        g2 = "PASS" if r_main["max_drawdown"] >= MAXDD_FLOOR else "FAIL"
        print(f"  Sharpe (2010-2024) = {r_main['sharpe']:.4f} ({g1} mot >= {SHARPE_FLOOR})  "
              f"MaxDD={r_main['max_drawdown']:.2%} ({g2} mot tak {MAXDD_FLOOR:.0%})  "
              f"CAGR={r_main['cagr']:+.2%}  Calmar={r_main['calmar']:.3f}")
        print(f"  DSR (K={K_TOTAL_TRIALS}) = {dsr_result['deflated_sharpe_ratio']:.4f}  "
              f"(skew={dsr_result['skewness']:+.2f}, kurt={dsr_result['kurtosis']:.2f}, "
              f"n_obs={dsr_result['n_obs']})")
        if r_oos["total_return"] is not None:
            print(f"  OOS-2025 (informativt): Sharpe={r_oos['sharpe']:.4f}  MaxDD={r_oos['max_drawdown']:.2%}  "
                  f"Avkastning={r_oos['total_return']:+.2%}")
        print(f"  Nya positioner: {stats['n_new_entries']}  Veckor med entry-batch: {stats['n_weeks_with_entry_batch']}  "
              f"Snitt oppna positioner/dag: {stats['avg_open_positions_per_day']:.2f}  "
              f"Max samtidiga: {stats['max_open_positions']}  "
              f"Signaler hoppade (redan oppen): {stats['n_signals_skipped_already_open']}  "
              f"Signaler hoppade (for sma/ADV-tak): {stats['n_signals_skipped_too_small']}\n")

        all_results[level] = {
            "main": r_main, "oos_2025": r_oos,
            "condition_1_sharpe_pass": g1 == "PASS", "condition_2_maxdd_pass": g2 == "PASS",
            "deflated_sharpe_ratio": dsr_result["deflated_sharpe_ratio"],
            "dsr_skewness": dsr_result["skewness"], "dsr_kurtosis": dsr_result["kurtosis"],
            "dsr_n_obs": dsr_result["n_obs"], "dsr_n_trials": K_TOTAL_TRIALS,
            "stats": stats,
        }

    all_results["mechanism_diagnostics"] = diag

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    print("KLART. Sammanfattning sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
