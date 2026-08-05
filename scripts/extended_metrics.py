"""
Utökade riskmått utöver de som redan sparas i varje hypotes' summary.json
(CAGR/Sharpe/MaxDD/Calmar): Sortino, beta/korrelation mot en benchmark
(SPY), och en avkastningsbaserad Profit Factor (för strategier utan
diskret trade_log, t.ex. HYP-039:s portföljnivå-ombalansering).

Byggd 2026-08-05 för att jämföra HYP-037 och HYP-039 på lika grund - se
research/hypothesis_registry för respektive hypotes' egna, redan
rapporterade CAGR/Sharpe/MaxDD (denna modul lägger bara till det som
saknades, den ersätter ingenting).

Usage:
    python scripts/extended_metrics.py <path-till-portfolio_value.csv> [--benchmark SPY]
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
OHLCV_DIR = REPO_ROOT / "data" / "cache" / "ohlcv"


def load_benchmark_returns(ticker: str = "SPY") -> pd.Series:
    path = OHLCV_DIR / f"{ticker}.csv"
    df = pd.read_csv(path, usecols=["date", "adjusted_close"], parse_dates=["date"])
    df = df.drop_duplicates(subset="date", keep="last").set_index("date").sort_index()
    return df["adjusted_close"].pct_change().dropna()


def sharpe(s: pd.Series, rf: float = 0.02) -> float:
    r = s.pct_change().dropna()
    return float(np.sqrt(252) * (r - rf / 252).mean() / r.std()) if r.std() > 0 else 0.0


def sortino(s: pd.Series, rf: float = 0.02, target: float = 0.0) -> float:
    """Som Sharpe, men nämnaren är BARA nedsidesvolatilitet (avkastning
    under target, default 0%) - straffar inte uppsidesvariation, som
    Sharpe gör. Ofta mer informativ för strategier med asymmetrisk
    avkastningsfördelning (t.ex. krasch-overlays som medvetet klipper
    nedsidan hårdare än uppsidan)."""
    r = s.pct_change().dropna()
    downside = r[r < target]
    dd = downside.std()
    if not dd or np.isnan(dd):
        return float("nan")
    return float(np.sqrt(252) * (r - rf / 252).mean() / dd)


def max_drawdown(s: pd.Series) -> float:
    return float(((s - s.cummax()) / s.cummax()).min())


def cagr(s: pd.Series) -> float:
    return float((s.iloc[-1] / s.iloc[0]) ** (252 / len(s)) - 1)


def calmar(s: pd.Series) -> float:
    md = abs(max_drawdown(s))
    return cagr(s) / md if md > 0 else 0.0


def beta_and_correlation(strategy_pv: pd.Series, benchmark_ret: pd.Series) -> tuple:
    """OLS-beta (kovarians/varians) och korrelation mot benchmarken,
    på dagliga avkastningar, inner join på datum."""
    r = strategy_pv.pct_change().dropna()
    joined = pd.concat([r.rename("s"), benchmark_ret.rename("b")], axis=1, join="inner").dropna()
    beta = float(joined["s"].cov(joined["b"]) / joined["b"].var())
    corr = float(joined["s"].corr(joined["b"]))
    return beta, corr


def return_based_profit_factor(s: pd.Series) -> float:
    """Profit Factor definierad pa DAGLIGA avkastningar (summa positiva
    dagar / |summa negativa dagar|) - anvandbar for strategier utan ett
    diskret trade_log (t.ex. HYP-039:s portfoljniva-ombalansering, dar
    "en affar" inte ar valdefinierat). Skiljer sig fran den klassiska,
    trade-baserade Profit Factor som redan sparas i strategier MED en
    trade_log (t.ex. HYP-037:s egen, se dess summary.json)."""
    r = s.pct_change().dropna()
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    return float(gains / losses) if losses != 0 else float("nan")


def compute_all(pv: pd.Series, benchmark_ret: pd.Series) -> dict:
    beta, corr = beta_and_correlation(pv, benchmark_ret)
    return {
        "cagr": cagr(pv),
        "sharpe": sharpe(pv),
        "sortino": sortino(pv),
        "max_drawdown": max_drawdown(pv),
        "calmar": calmar(pv),
        "beta": beta,
        "correlation": corr,
        "return_based_profit_factor": return_based_profit_factor(pv),
        "n_days": len(pv),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("portfolio_value_csv", type=Path)
    parser.add_argument("--benchmark", default="SPY")
    args = parser.parse_args()

    pv = pd.read_csv(args.portfolio_value_csv, index_col=0, parse_dates=True).iloc[:, 0]
    benchmark_ret = load_benchmark_returns(args.benchmark)
    result = compute_all(pv, benchmark_ret)

    print(f"{args.portfolio_value_csv}")
    print(f"  CAGR:              {result['cagr']:+.2%}")
    print(f"  Sharpe:            {result['sharpe']:.3f}")
    print(f"  Sortino:           {result['sortino']:.3f}")
    print(f"  MaxDD:             {result['max_drawdown']:.2%}")
    print(f"  Calmar:            {result['calmar']:.3f}")
    print(f"  Beta ({args.benchmark}):        {result['beta']:.3f}")
    print(f"  Korrelation ({args.benchmark}): {result['correlation']:.3f}")
    print(f"  Profit Factor (avkastningsbaserad): {result['return_based_profit_factor']:.3f}")
    print(f"  Handelsdagar:      {result['n_days']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
