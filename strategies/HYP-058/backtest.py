"""
HYP-058: Nygraduerad small-cap-momentum (micro-cap till small-cap-bandet).

Se research/hypothesis_registry/HYP-058-nygraduerad-smallcap-momentum.yaml
for det lasta kriteriet - LAST 2026-08-10. LONG-ONLY, ingen kort sida.

MEKANISM I KORTHET (fullstandig text i YAML:n):
  1. GRADUERINGSHANDELSE: en ticker "graduerar" i manad M om den (a)
     finns i det eligible small-cap-universumet ($100M-$2B) i manad M,
     (b) INTE fanns i universumet i manad M-1, OCH (c) hade minst 250
     handelsdagars prishistorik FORE manad M (utesluter farska IPO:er).
  2. POSITION: LONG samtliga graduerande tickers en given manad,
     likaviktat, ingangen VID NASTA SNAPPADE KVARTALSVISA
     OMBALANSERINGSDATUM efter graduering. HALLPERIOD: ETT KVARTAL
     (63 handelsdagar). Ingen kort sida.

IMPLEMENTATIONSVAL, INTE FRIA PARAMETRAR I KRITERIETS MENING (dokumenterade
har, samma disciplin som redan etablerad for HYP-055/057 - se dessas
backtest.py-docstrings for prejudikat pa detta monster):

  - "Universumet" i kriteriets (b)-klausul ("INTE fanns i universumet i
    manad M-1, varken small-cap- eller storre-klassad") tolkas OPERATIONELLT
    som EXAKT de tva redan byggda manatliga small-cap-universumfilerna
    (smallcap_universe_by_month_filed_date.json +
    smallcap_universe_2025_extension_filed_date.json), sammanslagna, per
    explicit uppdragsinstruktion - ingen bredare "alla storleksklasser"-
    universumfil existerar i repot (verifierat: data/cache/ innehaller
    bara dessa tva manatliga small-cap-filer plus current_universe.json,
    ingen historisk large-cap-motsvarighet). En ticker som lamnar
    small-cap-bandet uppat (blir large-cap) och senare kommer tillbaka
    skulle darfor ocksa raknas som "graduerande" nar den ateruppstar -
    detta ar en INTE en bugg utan den enda datamassigt mojliga tolkningen
    av kriteriets egen (b)-klausul med den data som faktiskt finns,
    konsistent med hur registret redan hanterar liknande databeroende-
    gap (jmf HYP-052/054:s feasibility-FAIL dar motsvarande data INTE
    fanns alls och hypotesen darfor inte kunde koras - har finns
    tillrackligt mycket data for att kora kriteriet sasom skrivet).
  - "250 handelsdagars prishistorik FORE manad M" tolkas som: antal
    GILTIGA (icke-NaN, EFTER samtliga fyra motorfix-saneringssteg -
    clean_price_matrix, mask_unrecovered_price_breaks,
    flag_implausible_liquidity, mask_implausible_adjusted_close_ratio)
    adjusted_close-observationer strikt FORE den forsta kalenderdagen i
    manad M (inte fore manadsslutsnyckelns eget datum) - den mest
    konservativa lasningen, utesluter all data inom sjalva
    gradueringsmanaden fran historik-rakningen.
  - "Nasta snappade kvartalsvisa ombalanseringsdatum efter graduering":
    kvartalsslut (QE, close_adj.resample("QE")) snappade via
    snap_rebalance_dates (samma konvention som resten av registret).
    "Nasta" tolkas strikt (>), inte >=: om gradueringsmanadens egna
    nyckeldatum RAKAR vara ett kvartalsslut (t.ex. "2010-03-31"), racker
    INTE det kvartalsslutet sjalvt som entry - signalen ar bara kand
    fran och med det datumet (filed-datum-korrigerat), sa det finns ingen
    intradagsmojlighet att agera SAMMA dag; entry sker vid NASTA
    kvartalsslut darefter. Flera gradueringsmanader kan darfor rutinmassigt
    mappa till SAMMA exekveringsdatum (t.ex. januari- och februari-
    graduerare mappar bada till marsslutet) - dessa poolas till EN
    likaviktad korg per exekveringsdatum (se nedan).
  - "Likaviktat... samtliga graduerande tickers en given manad": nar
    flera manaders gradueringskohorter mappar till SAMMA exekverings-
    datum (rutinmassigt, se ovan) poolas de till EN likaviktad korg per
    NAMN (inte en tva-nivas manads-sedan-namn-viktning) - den enklaste,
    minst godtyckliga tolkningen som undviker en extra, kriteriet-fri
    viktningsniva mellan manader.
  - Kapitalallokering: ALL tillganglig cash investeras i varje ny
    kvartalskohort nar den uppstar (eftersom korgarna redan ar poolade
    per exekveringsdatum ar det bara EN ny kohort per dag - "cash / 1"
    - samma monster som HYP-042/050/057s "cash / antal nya positioner
    den dagen"), begransat av ADV-kapacitetstaket (se nedan) och
    tillganglig cash.
  - KAPACITETSSPARR (ADV-tak): eftersom detta ar en small-cap-hypotes med
    tested_capital_levels 100k/1M/10M och kriteriet i sig inte
    specificerar en storleksmekanism, ateranvands SAMMA ADV-tak (rullande
    20-dagars dollarvolym x 10%, MAX_ADV_PCT) som redan etablerat i
    HYP-037/050/057 - annars skulle alla tre kapitalnivaer ge identiska
    resultat.
  - Entry sker till NASTA handelsdags OPPNINGSKURS (adjusted_open, samma
    "motorfix 2"-princip som HYP-037/040/042/049/050/057) pa det snappade
    exekveringsdatumet sjalvt (dvs. exekveringsdatumets EGEN
    oppningskurs - signalen ar redan kand fore det datumet borjar).
  - Position "hallperiod" mats EXAKT som i HYP-050/057 (samma
    "date_i - entry_date_i >= HOLD_DAYS"-monster): entry-dagen fangar
    open->close, varje foljande dag fangar close->close, exit sker DEN
    dag hallperioden lopt ut (dess EGEN dags avkastning inraknas i
    exit-varderingen) - 63 handelsdagar totalt fran entry till exit.
  - Namn utan giltig data en given dag exkluderas fran korgens dagliga
    likaviktade medelavkastning (INTE satta till 0) - "0 om alla NaN"-
    fallbacket anvands bara om HELA korgen saknar data den dagen, samma
    monster som resten av registret.

MOTORKRAV (last): filed-datum-universum, maskad adjusted_close-kvot,
mask_unrecovered_price_breaks(), flag_implausible_liquidity() (samtliga
fyra), Corwin-Schultz-spread pa entry/exit. Ingen borrow_cost behovs
(long-only) - ett explicit, dokumenterat noll-anrop finns for att
tillfredsstalla validate_friction_usage.py-grinden, samma monster som
redan etablerat i HYP-053/040.
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

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

FULL_START = "2010-01-01"
FULL_END = "2025-12-31"   # 2025 kravs for genuin blind OOS, se data_range i kriteriet

MIN_HISTORY_DAYS = 250     # last, utesluter farska IPO:er
HOLD_DAYS = 63              # last, "ett kvartal"

MAX_MARKET_CAP = 2_000_000_000
ADV_WINDOW = 20
MAX_ADV_PCT = 0.10
BORROW_ANNUAL_RATE = 0.03    # anvands aldrig pa riktigt (long-only), bara for noll-anropet nedan
RF_ANNUAL = 0.02

SHARPE_FLOOR = 0.55            # last pass_fail_criterion, enda gating-villkoret (ingen MaxDD-spärr)

OOS_START = "2025-01-01"
FULL_END_MAIN = "2024-12-31"

K_TOTAL_TRIALS = 57            # k_total_hypotheses_before_this (56) + 1, se YAML

HEDGE = "SPY"   # bara for handelskalendern


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
    """Samma "motorfix 2"-princip som HYP-037/040/042/049/050/057."""
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    return open_ * ratio


def build_graduation_entry_buckets(close_adj: pd.DataFrame, universe_by_month: dict):
    """
    Identifierar gradueringshandelser manad for manad, filtrerar pa
    250-dagars prishistorikkravet, och mappar varje kvalificerande
    graduerare till dess "nasta snappade kvartalsvisa
    ombalanseringsdatum"-exekveringsdag.

    Returnerar:
      entry_buckets: dict date_i (int, position i close_adj.index) ->
          sorterad lista av tickers som ska ga LONG den dagen
      diag: diagnostik for den obligatoriska disclosuren + sanity-check
    """
    idx = close_adj.index
    tickers = list(close_adj.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    valid_mask = close_adj.notna().values
    cumulative_valid = np.cumsum(valid_mask, axis=0)   # [n_days, n_tickers]

    month_keys = sorted(universe_by_month.keys())
    month_dates = pd.to_datetime(month_keys)

    # Kvartalsvisa exekveringsdatum (samma snap_rebalance_dates-konvention som resten av registret)
    quarter_labels = close_adj.resample("QE").last().index
    quarter_labels = quarter_labels[(quarter_labels >= idx[0]) & (quarter_labels <= idx[-1])]
    q_snap = snap_rebalance_dates(quarter_labels, idx)
    q_calendar_labels = q_snap["calendar_label"].to_numpy()
    q_execution_dates = q_snap["execution_date"].to_numpy()
    di = {d: i for i, d in enumerate(idx)}

    entry_buckets = defaultdict(set)

    n_months_evaluated = 0
    monthly_raw_grad_count = {}      # month_key -> antal graduerande FORE 250-dagarsfiltret
    monthly_filtered_grad_count = {}  # month_key -> antal graduerande EFTER 250-dagarsfiltret
    monthly_universe_size = {}
    n_skipped_no_future_quarter = 0
    n_skipped_no_price_data = 0

    prev_set = None
    for mi, mkey in enumerate(month_keys):
        cur_set = set(universe_by_month[mkey])
        monthly_universe_size[mkey] = len(cur_set)
        if prev_set is None:
            prev_set = cur_set
            continue
        n_months_evaluated += 1
        graduating_raw = cur_set - prev_set
        monthly_raw_grad_count[mkey] = len(graduating_raw)

        month_date = month_dates[mi]
        month_start = pd.Timestamp(year=month_date.year, month=month_date.month, day=1)
        pos0 = idx.searchsorted(month_start, side="left")

        qualifying = []
        for t in graduating_raw:
            if t not in tidx:
                n_skipped_no_price_data += 1
                continue
            t_i = tidx[t]
            history_count = int(cumulative_valid[pos0 - 1, t_i]) if pos0 > 0 else 0
            if history_count < MIN_HISTORY_DAYS:
                continue
            qualifying.append(t)

        monthly_filtered_grad_count[mkey] = len(qualifying)

        if qualifying:
            q_pos = np.searchsorted(q_calendar_labels, np.datetime64(month_date), side="right")
            if q_pos >= len(q_calendar_labels):
                n_skipped_no_future_quarter += len(qualifying)
            else:
                execution_date = q_execution_dates[q_pos]
                date_i = di[pd.Timestamp(execution_date)]
                for t in qualifying:
                    entry_buckets[date_i].add(t)

        prev_set = cur_set

    entry_buckets = {k: sorted(v) for k, v in entry_buckets.items()}

    # ---- Disclosure: per kvartal (kalenderkvartal for gradueringsmanaden) ----
    quarter_of_month = {mkey: pd.Timestamp(mkey).to_period("Q") for mkey in monthly_filtered_grad_count}
    quarterly_filtered = defaultdict(int)
    quarterly_raw = defaultdict(int)
    for mkey, cnt in monthly_filtered_grad_count.items():
        quarterly_filtered[quarter_of_month[mkey]] += cnt
    for mkey, cnt in monthly_raw_grad_count.items():
        quarterly_raw[quarter_of_month[mkey]] += cnt

    q_filtered_vals = np.array(list(quarterly_filtered.values()), dtype=float)
    q_raw_vals = np.array(list(quarterly_raw.values()), dtype=float)

    monthly_raw_frac = [monthly_raw_grad_count[m] / monthly_universe_size[m]
                         for m in monthly_raw_grad_count if monthly_universe_size[m] > 0]
    monthly_filtered_frac = [monthly_filtered_grad_count[m] / monthly_universe_size[m]
                              for m in monthly_filtered_grad_count if monthly_universe_size[m] > 0]

    diag = {
        "n_months_evaluated": n_months_evaluated,
        "n_quarters_with_data": len(quarterly_filtered),
        "avg_raw_graduating_per_quarter": float(q_raw_vals.mean()) if len(q_raw_vals) else 0.0,
        "std_raw_graduating_per_quarter": float(q_raw_vals.std()) if len(q_raw_vals) else 0.0,
        "avg_filtered_graduating_per_quarter": float(q_filtered_vals.mean()) if len(q_filtered_vals) else 0.0,
        "std_filtered_graduating_per_quarter": float(q_filtered_vals.std()) if len(q_filtered_vals) else 0.0,
        "avg_raw_graduating_frac_of_universe": float(np.mean(monthly_raw_frac)) if monthly_raw_frac else 0.0,
        "avg_filtered_graduating_frac_of_universe": float(np.mean(monthly_filtered_frac)) if monthly_filtered_frac else 0.0,
        "total_raw_graduating_events": int(sum(monthly_raw_grad_count.values())),
        "total_filtered_graduating_events": int(sum(monthly_filtered_grad_count.values())),
        "n_skipped_no_future_quarter": n_skipped_no_future_quarter,
        "n_skipped_no_price_data": n_skipped_no_price_data,
        "n_entry_dates": len(entry_buckets),
        "n_total_ticker_entries": int(sum(len(v) for v in entry_buckets.values())),
    }
    return entry_buckets, diag


def run_backtest(open_, close, close_adj, spread_df, adv_cap, entry_buckets, capital_level: float,
                  log_trades: bool = False):
    tickers = list(close_adj.columns)
    tidx = {t: i for i, t in enumerate(tickers)}

    daily_ret_v = close_adj.pct_change().values
    open_adj = adjusted_open(open_, close, close_adj)
    entry_day_ret_v = (close_adj / open_adj - 1.0).values
    spread_v = spread_df.reindex(columns=tickers).values
    adv_cap_v = adv_cap.reindex(columns=tickers).values

    if not entry_buckets:
        raise RuntimeError("inga gradueringskohorter byggda - kan inte kora backtest")

    start_idx = min(entry_buckets.keys())
    trade_dates = close_adj.index[start_idx:]

    cash = float(capital_level)
    positions = {}   # cohort_id -> {"names","entry_date_i","value","entry_value"}
    next_cohort_id = 0
    pv_list = [float(capital_level)]
    open_position_counts = []
    n_cohorts_entered = 0
    n_total_tickers_entered = 0
    n_cohorts_skipped_too_small = 0
    trade_log = [] if log_trades else None

    for date_i in range(start_idx, len(close_adj.index)):
        cash += cash * (RF_ANNUAL / 252)

        # ---- EXITS: hallperioden (HOLD_DAYS handelsdagar) har lopt ut ----
        for cid in list(positions.keys()):
            pos = positions[cid]
            days_held = date_i - pos["entry_date_i"]
            if days_held < HOLD_DAYS:
                continue
            idxs = np.array([tidx[t] for t in pos["names"] if t in tidx])
            rets_today = daily_ret_v[date_i, idxs]
            valid = ~np.isnan(rets_today)
            basket_ret = float(rets_today[valid].mean()) if valid.any() else 0.0
            pos["value"] *= (1.0 + basket_ret)
            ex_spreads = spread_v[date_i, idxs]
            valid_s = ~np.isnan(ex_spreads)
            avg_ex_spread = float(ex_spreads[valid_s].mean()) if valid_s.any() else 0.0
            pos["value"] *= (1.0 - avg_ex_spread / 2.0)
            cash += pos["value"]
            if log_trades:
                trade_log.append({
                    "cohort_id": cid, "entry_date_i": pos["entry_date_i"], "exit_date_i": date_i,
                    "entry_value": pos["entry_value"], "exit_value": pos["value"],
                    "net_return": pos["value"] / pos["entry_value"] - 1.0 if pos["entry_value"] > 0 else 0.0,
                    "n_names": len(pos["names"]),
                })
            del positions[cid]

        # ---- ENTRIES: dagens gradueringskohort (om nagon) ----
        todays_names = entry_buckets.get(date_i)
        if todays_names:
            idxs_all = np.array([tidx[t] for t in todays_names if t in tidx])
            names_valid = [t for t in todays_names if t in tidx]
            if len(idxs_all) > 0:
                target_basket_value = cash   # ALL tillganglig cash - bara EN ny kohort per dag (redan poolad)
                cap_row = adv_cap_v[date_i, idxs_all]
                cap_total = np.nansum(cap_row) if not np.all(np.isnan(cap_row)) else 0.0
                realized = min(target_basket_value, cap_total, cash) if cap_total > 0 else 0.0
                if realized < capital_level * 0.0001 or realized <= 0:
                    n_cohorts_skipped_too_small += 1
                else:
                    en_spreads = spread_v[date_i, idxs_all]
                    valid_s = ~np.isnan(en_spreads)
                    avg_en_spread = float(en_spreads[valid_s].mean()) if valid_s.any() else 0.0
                    value = realized * (1.0 - avg_en_spread / 2.0)

                    rets0 = entry_day_ret_v[date_i, idxs_all]
                    valid0 = ~np.isnan(rets0)
                    basket_ret0 = float(rets0[valid0].mean()) if valid0.any() else 0.0
                    value *= (1.0 + basket_ret0)

                    cash -= realized
                    positions[next_cohort_id] = {"names": names_valid, "entry_date_i": date_i,
                                                  "value": value, "entry_value": value}
                    next_cohort_id += 1
                    n_cohorts_entered += 1
                    n_total_tickers_entered += len(names_valid)

        # ---- Daglig vardering for positioner som varken oppnades eller stangdes idag ----
        for cid, pos in positions.items():
            if date_i - pos["entry_date_i"] == 0:
                continue
            idxs = np.array([tidx[t] for t in pos["names"] if t in tidx])
            rets_today = daily_ret_v[date_i, idxs]
            valid = ~np.isnan(rets_today)
            basket_ret = float(rets_today[valid].mean()) if valid.any() else 0.0
            pos["value"] *= (1.0 + basket_ret)

        open_position_counts.append(len(positions))
        total_positions_value = sum(p["value"] for p in positions.values())
        pv_list.append(cash + total_positions_value)

    pv = pd.Series(pv_list[1:], index=trade_dates)
    stats = {
        "n_cohorts_entered": n_cohorts_entered,
        "n_total_tickers_entered": n_total_tickers_entered,
        "n_cohorts_skipped_too_small": n_cohorts_skipped_too_small,
        "avg_open_positions_per_day": float(np.mean(open_position_counts)) if open_position_counts else 0.0,
        "max_open_positions": int(np.max(open_position_counts)) if open_position_counts else 0,
    }
    if log_trades:
        return pv, stats, trade_log
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


def load_and_clean_data():
    print("Laddar universum (huvudserie + 2025-utokning, sammanslaget)...")
    with ORIGINAL_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_orig = json.load(f)
    with EXTENSION_UNIVERSE_FILE.open(encoding="utf-8") as f:
        universe_2025 = json.load(f)
    universe_merged = {**universe_orig, **universe_2025}
    tickers = sorted({t for tks in universe_merged.values() for t in tks})
    print(f"  {len(tickers)} unika tickers, {len(universe_merged)} manader.\n")

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

    print("Beraknar 20-dagars ADV-kapacitetstak (close x volume x 10%, samma konvention som HYP-037/050/057)...")
    adv_cap = (close * volume).rolling(ADV_WINDOW, min_periods=ADV_WINDOW).mean() * MAX_ADV_PCT

    return universe_merged, open_, close, close_adj, high, low, volume, spread_df, adv_cap


def main():
    universe_merged, open_, close, close_adj, high, low, volume, spread_df, adv_cap = load_and_clean_data()

    # Explicit, dokumenterat noll-anrop: ingen kort sida i denna hypotes,
    # men validate_friction_usage.py (Risk Manager-grinden) kraver att
    # BADA friktionsfunktionerna faktiskt importeras OCH anropas i varje
    # small-cap-backtest med en ny motor - samma monster som HYP-040/053.
    _zero_borrow = borrow_cost(position_value=0.0, holding_days=1, annual_rate=BORROW_ANNUAL_RATE)
    assert _zero_borrow == 0.0

    print("Identifierar gradueringshandelser (manad for manad, 250-dagars historikfilter) "
          "och mappar till kvartalsvisa exekveringsdatum...")
    entry_buckets, diag = build_graduation_entry_buckets(close_adj, universe_merged)

    print(f"  Manader utvarderade (med foregaende manad tillganglig): {diag['n_months_evaluated']}")
    print(f"  Gradueringshandelser totalt (FORE 250-dagarsfilter): {diag['total_raw_graduating_events']}")
    print(f"  Gradueringshandelser totalt (EFTER 250-dagarsfilter, farska IPO:er uteslutna): "
          f"{diag['total_filtered_graduating_events']}")
    print(f"  Snitt graduerande/kvartal (FORE filter): {diag['avg_raw_graduating_per_quarter']:.2f} "
          f"(std {diag['std_raw_graduating_per_quarter']:.2f})")
    print(f"  Snitt graduerande/kvartal (EFTER filter, handelsbara): {diag['avg_filtered_graduating_per_quarter']:.2f} "
          f"(std {diag['std_filtered_graduating_per_quarter']:.2f})")
    print(f"  Snitt andel av eligible-universum/manad (FORE filter): {diag['avg_raw_graduating_frac_of_universe']:.2%}")
    print(f"  Snitt andel av eligible-universum/manad (EFTER filter): {diag['avg_filtered_graduating_frac_of_universe']:.2%}")
    print(f"  Hoppade (ingen framtida kvartalsslut kvar i data): {diag['n_skipped_no_future_quarter']}")
    print(f"  Hoppade (ingen prisdatafil for tickern): {diag['n_skipped_no_price_data']}")
    print(f"  Distinkta exekveringsdatum (kvartal med >=1 kohort): {diag['n_entry_dates']}")
    print(f"  Totalt ticker-entries over hela perioden: {diag['n_total_ticker_entries']}\n")

    if diag["total_filtered_graduating_events"] == 0:
        raise RuntimeError("SANITY-CHECK MISSLYCKADES: inga gradueringshandelser alls godkande 250-dagarsfiltret - "
                            "mekanismen exercerades aldrig, nagot ar troligen fel i implementationen.")

    levels = [100_000, 1_000_000, 10_000_000]
    all_results = {}
    RESULTS_DIR.mkdir(exist_ok=True)

    for level in levels:
        print(f"--- Kapitalniva: ${level:,.0f} ---")
        pv, stats = run_backtest(open_, close, close_adj, spread_df, adv_cap, entry_buckets, level)

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
        print(f"  Sharpe (2010-2024) = {r_main['sharpe']:.4f} ({g1} mot >= {SHARPE_FLOOR}, enda gating-villkoret)  "
              f"MaxDD={r_main['max_drawdown']:.2%} (informativt, ej gating)  "
              f"CAGR={r_main['cagr']:+.2%}  Calmar={r_main['calmar']:.3f}")
        print(f"  DSR (K={K_TOTAL_TRIALS}) = {dsr_result['deflated_sharpe_ratio']:.4f}  "
              f"(skew={dsr_result['skewness']:+.2f}, kurt={dsr_result['kurtosis']:.2f}, "
              f"n_obs={dsr_result['n_obs']})")
        if r_oos["total_return"] is not None:
            print(f"  OOS-2025 (informativt): Sharpe={r_oos['sharpe']:.4f}  MaxDD={r_oos['max_drawdown']:.2%}  "
                  f"Avkastning={r_oos['total_return']:+.2%}")
        print(f"  Kohorter: {stats['n_cohorts_entered']}  Tickers totalt: {stats['n_total_tickers_entered']}  "
              f"Snitt oppna positioner/dag: {stats['avg_open_positions_per_day']:.2f}  "
              f"Max samtidiga: {stats['max_open_positions']}  "
              f"Kohorter hoppade (for sma/ADV-tak): {stats['n_cohorts_skipped_too_small']}\n")

        all_results[level] = {
            "main": r_main, "oos_2025": r_oos,
            "condition_1_sharpe_pass": g1 == "PASS",
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
