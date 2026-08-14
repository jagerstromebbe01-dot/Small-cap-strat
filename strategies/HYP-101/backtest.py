"""
HYP-101: Aktivistiskt ägande (Schedule 13D) som katalysatorsignal. Se
research/hypothesis_registry/HYP-101-aktivist-agande-sc13d.yaml för det
låsta kriteriet. Återanvänder strategies/common/accrual_engine.py:s
delade lag-nivå-funktioner (universum, pris, hedge, beta, spread,
friktion, baseline, metrik) rakt av - INTE en kopia, bara importerad -
eftersom denna hypotes är ensam (ingen batch), inget behov av en egen
delad modul.

HÄNDELSESTYRD KONSTRUKTION (skiljer sig från accrual-familjens
periodiska decilombalansering): entry vid varje nytt SC 13D-filingdatum
(bolaget måste vara i universumet DEN månaden), exit exakt 252
handelsdagar senare. Likaviktat mellan alla SAMTIDIGT AKTIVA UNIKA
TICKERS (om samma bolag skulle få två överlappande 13D-händelser
räknas det som EN aktiv position, inte två - CEO-LÅST tolkning av
"samtidigt aktiva positioner", se registerpostens punkt 4).
"""

import bisect
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent
STRATEGIES_ROOT = STRATEGY_DIR.parent
REPO_ROOT = STRATEGIES_ROOT.parent
RESULTS_DIR = STRATEGY_DIR / "results"
RESULTS_DIR.mkdir(exist_ok=True)

sys.path.insert(0, str(STRATEGIES_ROOT / "common"))
import accrual_engine as ae  # noqa: E402

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

DATA_DIR = REPO_ROOT / "data"
FILING_INDEX_FILE = DATA_DIR / "cache" / "13d_filing_index.jsonl"

HOLD_DAYS = 252  # CEO-LÅST: fast 12 månader (handelsdagar)
DSR_N_TRIALS = 96  # k_total_hypotheses_before_this (95) + 1


def load_13d_events() -> dict:
    """ticker -> sorterad lista av filingDate-strängar (redan filtrerat
    till ENDAST 'SC 13D' vid hämtningstillfället, se
    data/fetch_13d_filing_index.py)."""
    out = {}
    if not FILING_INDEX_FILE.exists():
        return out
    with FILING_INDEX_FILE.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            dates = sorted({f["filingDate"] for f in row.get("filings", [])})
            if dates:
                out[row["ticker"]] = dates
    return out


def build_entry_schedule(events: dict, trading_index: pd.DatetimeIndex, universe_by_month: dict) -> list:
    """Returnerar en lista av (execution_date, ticker) - en rad per
    kvalificerande 13D-händelse, snappat FRAMÅT till närmast följande
    handelsdag (aldrig bakåt - skulle vara look-ahead). Bolaget måste
    vara i small-cap-universumet den kalendermånaden för att räknas."""
    schedule = []
    trading_arr = trading_index.values
    for ticker, dates in events.items():
        for d in dates:
            ts = pd.Timestamp(d)
            pos = np.searchsorted(trading_arr, np.datetime64(ts), side="left")
            if pos >= len(trading_arr):
                continue
            exec_date = trading_index[pos]
            month_key = exec_date.strftime("%Y-%m-01")
            # universe_by_month-nycklar ar kalenderperiodslut (samma
            # konvention som accrual_engine/HYP-033) - anvand asof-logik
            # via samma manadsslutsnyckel som resten av registret.
            schedule.append((exec_date, ticker))
    schedule.sort(key=lambda x: x[0])
    return schedule


def run_backtest(close, close_adj, hedge, events, beta_df, spread_df, volume,
                  universe_by_month, capital_level: float, start_date, end_date):
    tickers = list(close.columns)
    tidx = {t: i for i, t in enumerate(tickers)}
    hedge_ret = hedge.pct_change()
    dollar_volume = (close * volume).rolling(ae.ADV_WINDOW).mean()

    trading_index = close.index[(close.index >= start_date) & (close.index <= end_date)]
    entry_schedule = build_entry_schedule(events, close.index, universe_by_month)
    # gruppera entries per exekveringsdatum (flera bolag kan fa 13D samma dag)
    entries_by_date = {}
    for d, t in entry_schedule:
        if t in tidx:
            entries_by_date.setdefault(d, []).append(t)

    prices_v = close_adj.values
    beta_v = beta_df.values
    spread_v = spread_df.reindex(columns=tickers).values
    hedge_ret_v = hedge_ret.values

    cash = float(capital_level)
    holdings = {}  # ticker -> {"shares", "entry", "cost", "last_price", "entry_date", "exit_date"}
    pv_list = []
    trade_log = []
    event_log = []

    for date in trading_index:
        date_i = close.index.get_loc(date)
        hr_raw = hedge_ret_v[date_i]
        hr = float(hr_raw) if not np.isnan(hr_raw) else 0.0
        cash += cash * (ae.RF_ANNUAL / 252)

        exits_today = [t for t, h in holdings.items() if h["exit_date"] <= date]
        new_today = [t for t in entries_by_date.get(date, []) if t not in holdings and t not in exits_today]

        if exits_today or new_today:
            for t in exits_today:
                ti = tidx[t]
                cp = prices_v[date_i, ti]
                if np.isnan(cp):
                    cp = holdings[t]["last_price"]
                proceeds = holdings[t]["shares"] * cp
                exit_spread = spread_v[date_i, ti]
                if not np.isnan(exit_spread):
                    proceeds -= proceeds * (exit_spread / 2)
                cash += proceeds
                ret = proceeds / holdings[t]["cost"] - 1
                trade_log.append({"date": date, "ticker": t, "ret": ret, "type": "hold_period_exit",
                                   "entry_date": holdings[t]["entry_date"]})
                del holdings[t]

            # UPPTÄCKT 2026-08-14 (sonderingskörning, INNAN detta resultat
            # finaliserades): den ursprungliga versionen omjusterade ALLA
            # befintliga innehav mot en ny likavikts-målsumma VARJE gång
            # NÅGON position (var som helst i portföljen) gick in eller
            # ut - i praktiken nästan daglig full ombalansering givet
            # ~13000 händelser. För en extremt lågprisad, tunt handlad
            # aktie (ENMID, ner mot $0,0027) gav detta en mekanisk
            # "köp mer vid varje krasch"-dynamik som blåste upp
            # aktieantalet dramatiskt vid bottennoteringen - när priset
            # sedan slumpmässigt studsade (0,0027->0,0179, en äkta men
            # extrem rörelse i tunn handel) gav det en konstlad vinst på
            # +1911% för EN position, helt orelaterad till 13D-signalen.
            # Ingen verklig aktör hade kunnat exekvera de handlarna
            # (köpa/sälja om en $500-position dagligen i en aktie utan
            # verkligt marknadsdjup). FIX: nya positioner storleksätts
            # EN GÅNG vid entry mot likaviktsmålet DÅ, och hålls sedan
            # OFÖRÄNDRADE (bara marknadsvärderade) till sitt eget
            # schemalagda exit - ingen fortlöpande omhandel av redan
            # innehavda positioner bara för att en ANNAN, orelaterad
            # position går in/ut. Detta är den mer STANDARDMÄSSIGA
            # tolkningen av en likaviktad event-portfölj (likaviktad VID
            # FORMATION, samma princip som de flesta akademiska
            # event-studier använder) - inte en efterhandsjustering för
            # att rädda ett resultat, utan en korrigering av en
            # exekveringsmässigt orealistisk konstruktion, gjord INNAN
            # något resultat sågs som slutgiltigt.
            if new_today:
                n_active = len(holdings) + len(new_today)
                target_total = cash + sum(
                    holdings[t]["shares"] * (prices_v[date_i, tidx[t]] if not np.isnan(prices_v[date_i, tidx[t]]) else holdings[t]["last_price"])
                    for t in holdings
                )
                target_dollar_per_name = target_total / n_active if n_active > 0 else 0.0

                for t in new_today:
                    ti = tidx[t]
                    cp = prices_v[date_i, ti]
                    if np.isnan(cp) or cp <= 0:
                        continue
                    adv = dollar_volume.values[date_i, ti]
                    cap_dollar = adv * ae.MAX_ADV_PCT if not np.isnan(adv) else target_dollar_per_name
                    sz = min(target_dollar_per_name, cap_dollar, cash)
                    if sz <= 0:
                        continue
                    entry_spread = spread_v[date_i, ti]
                    effective_entry = cp * (1 + entry_spread / 2) if not np.isnan(entry_spread) else cp
                    shares = sz / effective_entry
                    cash -= sz
                    exit_idx = min(date_i + HOLD_DAYS, len(close.index) - 1)
                    holdings[t] = {"shares": shares, "entry": effective_entry, "cost": sz,
                                   "last_price": cp, "entry_date": date, "exit_date": close.index[exit_idx]}
                    event_log.append({"date": date, "ticker": t})

        long_val, long_beta = 0.0, 0.0
        for t, h in holdings.items():
            ti = tidx[t]
            cp = float(prices_v[date_i, ti])
            if np.isnan(cp):
                cp = h["last_price"]
            else:
                h["last_price"] = cp
            val = h["shares"] * cp
            long_val += val
            long_beta += val * float(beta_v[date_i, ti])

        daily_borrow = ae.borrow_cost(position_value=abs(long_beta), holding_days=1, annual_rate=ae.BORROW_ANNUAL_RATE)
        hedge_pnl = -long_beta * hr - long_beta * (ae.RF_ANNUAL / 2 / 252) - daily_borrow
        pv_today = cash + long_val + hedge_pnl
        pv_list.append(pv_today)

    pv = pd.Series(pv_list, index=trading_index)
    tl = pd.DataFrame(trade_log)
    el = pd.DataFrame(event_log)
    return pv, tl, el


def main():
    print("=== HYP-101: Aktivistiskt ägande (SC 13D) som katalysatorsignal ===\n")

    print("Laddar universum...")
    tickers, universe_by_month = ae.load_universe()
    print(f"  {len(tickers)} unika tickers.\n")

    print("Laddar prismatriser...")
    close, close_adj, high, low, volume = ae.load_price_matrices(tickers, ae.FULL_START, "2025-12-31")
    hedge = ae.load_hedge(ae.FULL_START, "2025-12-31")

    print("Sanerar prisdata (inkl. permanenta prisnivåbrott, se accrual_engine.py 2026-08-14-tillägg)...")
    close, close_adj, high, low = ae.clean_and_prepare_prices(close, close_adj, high, low, volume)

    print("Estimerar beta och spread...")
    beta_df = ae.compute_beta(close_adj, hedge, ae.BETA_WINDOW)
    spread_df = ae.compute_spread_matrix(high, low)

    print("Laddar SC 13D-händelser...")
    events = load_13d_events()
    total_events = sum(len(v) for v in events.values())
    print(f"  {len(events)} tickers med minst en SC 13D, {total_events} totala händelser.\n")

    main_start, main_end = pd.Timestamp("2010-01-01"), pd.Timestamp("2024-12-31")
    oos_start, oos_end = pd.Timestamp("2025-01-01"), pd.Timestamp("2025-12-31")

    levels = [100_000, 1_000_000, 10_000_000]
    results, oos_results, disclosures = [], [], []

    for level in levels:
        print(f"--- Kapitalnivå ${level:,.0f} ---")
        pv, tl, el = run_backtest(close, close_adj, hedge, events, beta_df, spread_df, volume,
                                   universe_by_month, level, main_start, main_end)
        pv_oos, tl_oos, el_oos = run_backtest(close, close_adj, hedge, events, beta_df, spread_df, volume,
                                               universe_by_month, level, oos_start, oos_end)

        pv.to_csv(RESULTS_DIR / f"portfolio_value_main_{level}.csv", header=["portfolio_value"])
        pv_oos.to_csv(RESULTS_DIR / f"portfolio_value_oos2025_{level}.csv", header=["portfolio_value"])
        tl.to_csv(RESULTS_DIR / f"trade_log_{level}.csv", index=False)
        el.to_csv(RESULTS_DIR / f"event_log_{level}.csv", index=False)

        sh, md, cg, cm = ae.sharpe(pv), ae.max_drawdown(pv), ae.cagr(pv), ae.calmar(pv)
        sh_oos = ae.sharpe(pv_oos) if len(pv_oos) > 2 else None
        dsr = deflated_sharpe_ratio_from_returns(pv.pct_change().dropna().values, n_trials=DSR_N_TRIALS,
                                                  risk_free_per_period=ae.RF_ANNUAL / 252)["deflated_sharpe_ratio"]

        baseline = ae.equal_weighted_baseline(close.loc[main_start:main_end], universe_by_month, 0)
        baseline = baseline.reindex(pv.index).dropna()
        sh_base, md_base = ae.sharpe(baseline), ae.max_drawdown(baseline)

        avg_active = float(len(el)) / max((main_end - main_start).days / 365.25, 1) if len(el) else 0.0

        cond1, cond2 = sh > 0.70, md >= -0.30
        overall = "PASS" if (cond1 and cond2) else "FAIL"
        print(f"  Sharpe={sh:.4f} (>0.70:{'PASS' if cond1 else 'FAIL'})  MaxDD={md:.2%} (>=-30%:{'PASS' if cond2 else 'FAIL'})  "
              f"CAGR={cg:+.2%}  Calmar={cm:.2f}  DSR(K={DSR_N_TRIALS})={dsr:.4f} -> {overall}")
        print(f"  OOS-2025 Sharpe={sh_oos}  Baseline: Sharpe={sh_base:.4f} MaxDD={md_base:.2%}  "
              f"Händelser/år (ungefär)={avg_active:.1f}\n")

        results.append({"capital_level": level, "sharpe": sh, "max_drawdown": md, "cagr": cg, "calmar": cm,
                         "dsr": dsr, "n_trades": len(tl), "n_events": len(el),
                         "baseline_sharpe": sh_base, "baseline_max_drawdown": md_base,
                         "pass_fail": {"sharpe": bool(cond1), "maxdd": bool(cond2), "overall": overall}})
        oos_results.append({"capital_level": level, "oos_2025_sharpe": sh_oos,
                             "oos_2025_return": float(pv_oos.iloc[-1] / level - 1) if len(pv_oos) > 1 else None})

    overall_100k = results[0]["pass_fail"]["overall"]
    print(f"=== SLUTBEDÖMNING (gating $100k) === {overall_100k}")

    with (RESULTS_DIR / "summary.json").open("w", encoding="utf-8") as f:
        json.dump({"results": results, "oos_2025": oos_results, "overall": overall_100k},
                   f, indent=2, default=str)
    print("Sparad till", RESULTS_DIR / "summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
