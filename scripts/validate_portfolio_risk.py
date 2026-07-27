#!/usr/bin/env python3
"""
STUB - INTE AKTIV ÄN. Portföljnivå-risk för Risk Manager-rollen, se
/agents/risk_manager/ROLE.md ("portföljnivå-risk när fler än en
strategi är aktiv samtidigt").

Just nu finns bara EN hypotes i registret (HYP-008, status: failed) -
det finns inget portföljscenario att skydda, så det finns inget
meningsfullt att bygga logik mot än. Detta skript är ett MEDVETET
ofärdigt skelett, inte en riktig spärr - anropa det inte som en
enforcement-gate någonstans än (till skillnad från
validate_hypothesis.py/validate_friction_usage.py, som BÅDA är
aktiva spärrar).

AKTIVERA NÄR: minst 2 hypoteser samtidigt har status: passed.

TODO när detta ska byggas på riktigt:
  - Total kapitalallokering över alla aktiva (passed) strategier
    samtidigt - säkerställ att summan inte överskrider tillgängligt
    kapital om flera strategier skulle köras parallellt i produktion.
  - Korrelation mellan aktiva strategiers avkastningsserier - en portfölj
    av strategier som alla har hög inbördes korrelation ger inte den
    diversifieringsvinst kombinationsregeln i spec-dokumentet avsnitt 5b
    kräver innan man ens överväger att kombinera dem.
  - Per spec-dokumentet avsnitt 5b: en kombination av flera hypoteser är
    en EGEN, ny pre-registrerad hypotes med sitt eget K-bidrag - detta
    skript ska INTE bli en genväg som smygande tillåter kombination utan
    att gå via det steget.
"""

import sys


def validate_portfolio_risk() -> dict:
    """
    STUB. Returnerar alltid detta tills minst 2 hypoteser har
    status: passed - se modulens docstring för vad som ska byggas då.
    """
    return {
        "ok": True,
        "enforced": False,
        "message": "not yet enforced, activate when 2+ hypotheses have status: passed",
    }


def main() -> int:
    result = validate_portfolio_risk()
    print(f"{result['message']} (enforced={result['enforced']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
