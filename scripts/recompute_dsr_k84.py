#!/usr/bin/env python3
"""
Overfitting Detector-uppgift (CLAUDE.md, avsnitt om hypotesregistret):
"recomputes Deflated Sharpe Ratio for all still-under-consideration
hypotheses (not just the latest) after every test". K gick fran 68 till
84 pa en dag (2026-08-12), sa detta ar en betydande eftersläpning -
samma monster som redan en gang upptacktes och atgardades vid K=46 (se
recompute_dsr_k46.py).

Scope: bara den AKTIVA referenslinjen (inte hela registret - de flesta
av de 84 hypoteserna ar redan dda/FAILED och deras DSR paverkar inget
levande beslut): HYP-037/043/047 (befintliga ben), HYP-056 (tidigare
referens), HYP-079 (basta fristaende HYP-072-variant), HYP-081 (femte-
bens-kombination). HYP-087 (havstang) UTESLUTEN har - dess DSR
beraknades redan FARSKT mot K=84 i samma korning som lasningen, ingen
omrakning behovs.

INGA redan lasta Sharpe/MaxDD/CAGR-siffror andras - bara DSR-faltet
skrivs ut for manuell, daterad tilläggsnot i respektive YAML.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
STRATEGIES_ROOT = REPO_ROOT / "strategies"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from deflated_sharpe_ratio import deflated_sharpe_ratio_from_returns  # noqa: E402

K_TOTAL = 84
LEVELS = [100_000, 1_000_000, 10_000_000]
RF_ANNUAL = 0.02
RF_PER_PERIOD = RF_ANNUAL / 252

# (namn, HYP-mapp, filnamnsmonster, tidigare K vid ursprunglig/senaste DSR-berakning)
TARGETS = [
    ("HYP-037 (leg 2, idio-vol+krasch)", "HYP-037", "portfolio_value_{level}.csv", 36),
    ("HYP-043 (leg 3, momentum L/S-kombo)", "HYP-043", "portfolio_value_combined_{level}.csv", 42),
    ("HYP-047 (leg 4, bear catcher, 4-bensportfolj)", "HYP-047", "portfolio_value_combined_{level}.csv", 46),
    ("HYP-056 (tidigare referens, vol-malsatt)", "HYP-056", "portfolio_value_combined_scaled_{level}.csv", 55),
    ("HYP-079 (basta fristaende HYP-072-variant)", "HYP-079", "portfolio_value_{level}.csv", None),
    ("HYP-081 (femte-bens-kombination)", "HYP-081", "portfolio_value_combined_{level}.csv", None),
]


def load_returns(hyp_dir: str, pattern: str, level: int) -> pd.Series:
    path = STRATEGIES_ROOT / hyp_dir / "results" / pattern.format(level=level)
    pv = pd.read_csv(path, index_col=0, parse_dates=True)["portfolio_value"]
    return pv.pct_change().dropna()


def main():
    print(f"=== DSR omraknad mot dagens k_total={K_TOTAL} (RF={RF_ANNUAL:.0%}/ar avdraget) ===\n")
    for name, hyp_dir, pattern, old_k in TARGETS:
        prev = f"tidigare DSR vid K={old_k + 1}" if old_k is not None else "ALDRIG tidigare beraknad"
        print(f"{name} ({prev}):")
        for level in LEVELS:
            try:
                returns = load_returns(hyp_dir, pattern, level)
            except FileNotFoundError as e:
                print(f"  ${level:>10,.0f}  (fil saknas: {e})")
                continue
            result = deflated_sharpe_ratio_from_returns(returns.values, n_trials=K_TOTAL,
                                                          risk_free_per_period=RF_PER_PERIOD)
            print(f"  ${level:>10,.0f}  SR={result['sharpe_ratio']:.4f}  "
                  f"DSR(K={K_TOTAL})={result['deflated_sharpe_ratio']:.4f}  n_obs={result['n_obs']}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
