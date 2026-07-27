"""
Friktionsmodellering - delad av alla strategier, inte specifik för en
enskild hypotes. Implementerar exakt den friktionsmetodik som är låst i
HYP-008:s pass_fail_criterion (se
/research/hypothesis_registry/HYP-008-v6-smallcap-replication.yaml,
tillägget "FRIKTIONSMETODIK", låst 2026-07-26):

- Bid-ask-spread: Corwin & Schultz (2012), "A Simple Way to Estimate
  Bid-Ask Spreads from Daily High and Low Prices", Journal of Finance
  67(2). Halva den skattade spreaden appliceras vid trade-öppning,
  halva vid stängning (se användning i Coder-implementationen för
  HYP-008 - denna modul levererar bara skattningen, applicerar den
  inte själv).
- Borrow-kostnad: fast 3% årlig ränta på det korta benets
  positionsvärde, proportionellt mot faktisk hålltid.

Kopiera INTE denna fil per hypotes (till skillnad från
/reference_code/) - den är delad, generisk friktionslogik som gäller
oavsett universum. Ändra den bara om friktionsmetodiken själv ändras
genom ett nytt CEO-beslut i chatt, inte per strategi.
"""

import numpy as np


def corwin_schultz_spread(high, low) -> np.ndarray:
    """
    Corwin & Schultz (2012) bid-ask-spread-estimator.

    Tar dagliga high/low-prisserier (samma längd, tidsmässigt justerade)
    och returnerar en array av skattade spreadar som ANDEL av priset
    (t.ex. 0.002 = 0.2%), en per glidande 2-dagarsfönster. Skattningen
    för fönstret (t, t+1) läggs på index t+1 (dagen fönstret avslutas) -
    index 0 är alltid NaN eftersom minst två dagar krävs.

    En enskild skattning kan matematiskt bli negativ trots att en
    verklig spread aldrig är det - Corwin & Schultz rekommendation är
    att klippa dessa till 0, inte kasta bort observationen, vilket görs
    här.

    Rader med icke-positiva priser (high/low <= 0, t.ex. saknad data
    kodad som 0) hoppas över (lämnas som NaN) snarare än att krascha,
    men NaN sväljs aldrig tyst - anroparen ser dem i outputen.
    """
    high = np.asarray(high, dtype=float)
    low = np.asarray(low, dtype=float)
    if high.shape != low.shape:
        raise ValueError(f"high och low måste ha samma form, fick {high.shape} och {low.shape}")

    n = len(high)
    spread = np.full(n, np.nan)
    if n < 2:
        return spread

    k = 3 - 2 * np.sqrt(2)  # konstant från Corwin & Schultz (2012), ekv. 10-11

    for t in range(n - 1):
        h1, l1 = high[t], low[t]
        h2, l2 = high[t + 1], low[t + 1]
        if h1 <= 0 or l1 <= 0 or h2 <= 0 or l2 <= 0 or h1 < l1 or h2 < l2:
            continue

        beta = np.log(h1 / l1) ** 2 + np.log(h2 / l2) ** 2

        h_2day = max(h1, h2)
        l_2day = min(l1, l2)
        if h_2day <= 0 or l_2day <= 0 or h_2day < l_2day:
            continue
        gamma = np.log(h_2day / l_2day) ** 2

        alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / k - np.sqrt(gamma / k)

        s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
        spread[t + 1] = max(0.0, s)

    return spread


def borrow_cost(position_value: float, holding_days: float, annual_rate: float = 0.03) -> float:
    """
    Borrow-kostnad för en kort position: 0.03 * positionsvärde *
    (hålltid_i_dagar / 365) - fast 3% årlig ränta, per HYP-008:s låsta
    friktionsmetodik. annual_rate är parametriserad (inte hårdkodad
    inline) så en framtida, separat pre-registrerad hypotes kan använda
    en annan ränta utan att ändra denna funktions signatur - men för
    HYP-008 ska anroparen alltid använda förvalet 0.03, inte skicka in
    något annat, om inte kriteriet omförhandlas.
    """
    if position_value < 0:
        raise ValueError("position_value ska vara ett icke-negativt belopp")
    if holding_days < 0:
        raise ValueError("holding_days kan inte vara negativt")
    return annual_rate * position_value * (holding_days / 365.0)


if __name__ == "__main__":
    # Sanity-check med SYNTETISK data - kräver ingen riktig prisdata.
    print("--- friction.py: sanity-check med syntetisk data ---\n")

    # Konstant spread (high/low aldrig varierar) -> spreaden ska vara ~0
    flat_high = np.full(10, 100.5)
    flat_low = np.full(10, 99.5)
    flat_spread = corwin_schultz_spread(flat_high, flat_low)
    print(f"Konstant high/low-intervall: spread (icke-NaN) = {flat_spread[~np.isnan(flat_spread)]}")

    # Vidare intervall -> högre skattad spread
    wide_high = np.full(10, 110.0)
    wide_low = np.full(10, 90.0)
    wide_spread = corwin_schultz_spread(wide_high, wide_low)
    print(f"Vidare high/low-intervall: spread (icke-NaN) = {wide_spread[~np.isnan(wide_spread)]}")
    print(
        "Förväntat: vidare intervall ska ge STÖRRE skattad spread än smalt "
        f"intervall: {np.nanmean(wide_spread) > np.nanmean(flat_spread)}"
    )

    print(f"\nFörsta värdet är alltid NaN (kräver 2 dagar): {np.isnan(flat_spread[0])}")

    print("\n--- borrow_cost: sanity-check ---")
    bc = borrow_cost(position_value=10_000, holding_days=365, annual_rate=0.03)
    print(f"borrow_cost($10,000, 365 dagar, 3%) = {bc:.2f} (väntat: 300.00)")
    bc_half_year = borrow_cost(position_value=10_000, holding_days=182.5, annual_rate=0.03)
    print(f"borrow_cost($10,000, 182.5 dagar, 3%) = {bc_half_year:.2f} (väntat: 150.00)")
