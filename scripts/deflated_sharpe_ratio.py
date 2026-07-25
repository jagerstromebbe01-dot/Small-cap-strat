"""
Deflated Sharpe Ratio (DSR) - Bailey & López de Prado (2014),
"The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest
Overfitting, and Non-Normality".

Ägs av Overfitting Detector-rollen, se /agents/overfitting_detector/ROLE.md.
Detta är kärnan i skyddet mot exakt den typ av multipel-testnings-bias som
dödförklarade de 7 Ejay-varianterna (spec-dokumentet avsnitt 2, princip 2).

Idé i korthet: en observerad Sharpe Ratio (SR) från EN backtest säger inte
om strategin har verklig edge eller om den bara råkade se bra ut efter att
K olika varianter testats. DSR svarar på: "vad är sannolikheten att den
här SR:n är genuint bättre än noll, GIVET att vi redan sökt igenom K
varianter?" Ju högre K, desto högre SR krävs för samma DSR - för att man
FÖRVÄNTAS hitta någon slumpmässigt hög SR bland tillräckligt många försök.

Alla Sharpe-tal i denna modul är PER-PERIOD (t.ex. dagliga), INTE
annualiserade - blanda inte ihop dessa, det ger fel resultat.
"""

import math

import numpy as np
from scipy.stats import norm

EULER_MASCHERONI = 0.5772156649015328606


def sharpe_ratio(returns: np.ndarray, risk_free_per_period: float = 0.0) -> float:
    """Per-period Sharpe ratio (inte annualiserad) för en avkastningsserie."""
    excess = np.asarray(returns, dtype=float) - risk_free_per_period
    std = excess.std(ddof=1)
    if std == 0:
        return 0.0
    return float(excess.mean() / std)


def skewness(returns: np.ndarray) -> float:
    """Sample skewness (γ3)."""
    r = np.asarray(returns, dtype=float)
    n = len(r)
    m = r.mean()
    s = r.std(ddof=1)
    if s == 0 or n < 3:
        return 0.0
    return float(((r - m) ** 3).mean() / s**3)


def kurtosis(returns: np.ndarray) -> float:
    """Sample kurtosis (γ4, ICKE excess - normalfördelning ger 3.0, inte 0)."""
    r = np.asarray(returns, dtype=float)
    n = len(r)
    m = r.mean()
    s = r.std(ddof=1)
    if s == 0 or n < 4:
        return 3.0
    return float(((r - m) ** 4).mean() / s**4)


def expected_max_sharpe_ratio(n_trials: int, sr_std: float) -> float:
    """
    Förväntad maximal Sharpe Ratio bland N oberoende försök, under
    nollhypotesen att ingen av dem har verklig edge (SR0 i Bailey &
    López de Prado). Detta är jämförelsepunkten DSR mäter den faktiska
    Sharpen mot - inte noll.

    n_trials: K, totala antalet testade varianter (inkl. denna).
    sr_std: standardavvikelse för Sharpe-ratio-estimatorn (se
            deflated_sharpe_ratio() för hur den skattas här).
    """
    if n_trials < 2:
        # Med bara ett försök finns ingen multipel-testnings-korrektion
        # att göra - förväntad max är per definition 0 (ingen sökning).
        return 0.0
    return sr_std * (
        (1 - EULER_MASCHERONI) * norm.ppf(1 - 1.0 / n_trials)
        + EULER_MASCHERONI * norm.ppf(1 - 1.0 / (n_trials * math.e))
    )


def deflated_sharpe_ratio(
    observed_sr: float,
    n_trials: int,
    n_obs: int,
    skew: float = 0.0,
    kurt: float = 3.0,
) -> float:
    """
    Beräknar DSR: sannolikheten (0-1) att den observerade per-period-
    Sharpen är genuint > 0, efter korrektion för att n_trials varianter
    redan sökts igenom och för att avkastningsseriens skevhet/kurtosis
    avviker från normalfördelning.

    observed_sr: den testade hypotesens egen, per-period Sharpe.
    n_trials:    k_total_hypotheses_before_this + 1 (denna hypotes räknas
                 med) - läs alltid från registrets löpande räknare, mata
                 aldrig in ett gissat tal.
    n_obs:       antal avkastningsobservationer (T) i backtesten.
    skew, kurt:  skevhet/kurtosis för samma avkastningsserie som
                 observed_sr beräknades på.

    Returnerar ett DSR-värde i [0, 1]. Ett vanligt tröskelval är DSR >
    0.95 ("95% sannolikt genuin edge givet K försök"), men det exakta
    tröskelvärdet är en del av respektive hypotes låsta
    pass_fail_criterion, inte hårdkodat här.
    """
    if n_obs < 2:
        raise ValueError("n_obs måste vara >= 2 för att beräkna DSR")

    # Standardavvikelse för SR-estimatorn, evaluerad vid den observerade
    # skevheten/kurtosis (samma uttryck som nämnaren nedan) men vid SR=0 -
    # den konservativa, standardmässiga förenklingen när man inte har hela
    # fördelningen av samtliga K försöks individuella Sharpe-tal
    # tillgänglig (se Bailey & López de Prado, avsnitt om SR^~).
    sr_std = math.sqrt(max((1 - skew * 0 + (kurt - 1) / 4 * 0**2), 1e-12) / (n_obs - 1))

    sr0 = expected_max_sharpe_ratio(n_trials, sr_std)

    denom = math.sqrt(max(1 - skew * observed_sr + (kurt - 1) / 4 * observed_sr**2, 1e-12))
    z = (observed_sr - sr0) * math.sqrt(n_obs - 1) / denom

    return float(norm.cdf(z))


def deflated_sharpe_ratio_from_returns(
    returns: np.ndarray, n_trials: int, risk_free_per_period: float = 0.0
) -> dict:
    """
    Bekvämlighetsfunktion: räknar ut SR, skevhet, kurtosis direkt från en
    avkastningsserie och returnerar DSR plus mellanstegen (för loggning/
    granskning - skriv aldrig bara ut DSR-talet utan sammanhanget bakom).
    """
    r = np.asarray(returns, dtype=float)
    sr = sharpe_ratio(r, risk_free_per_period)
    skew = skewness(r)
    kurt = kurtosis(r)
    dsr = deflated_sharpe_ratio(sr, n_trials, len(r), skew, kurt)
    return {
        "sharpe_ratio": sr,
        "n_obs": len(r),
        "n_trials": n_trials,
        "skewness": skew,
        "kurtosis": kurt,
        "deflated_sharpe_ratio": dsr,
    }


if __name__ == "__main__":
    # Sanity-check med SYNTETISK data - kräver ingen riktig prisdata.
    # Bekräftar det förväntade beteendet: samma råa Sharpe ska ge LÄGRE
    # DSR ju fler försök (K) den ställs mot.
    rng = np.random.default_rng(42)

    print("--- Deflated Sharpe Ratio: sanity-check med syntetisk data ---\n")

    # En avkastningsserie med en liten men verklig positiv drift
    daily_returns = rng.normal(loc=0.0004, scale=0.01, size=1000)

    print("Samma avkastningsserie, ökande antal försök (K):\n")
    for k in [1, 7, 8, 50, 200]:
        result = deflated_sharpe_ratio_from_returns(daily_returns, n_trials=k)
        print(
            f"  K={k:>4}  SR={result['sharpe_ratio']:.3f}  "
            f"skew={result['skewness']:+.2f}  kurt={result['kurtosis']:.2f}  "
            f"DSR={result['deflated_sharpe_ratio']:.4f}"
        )

    print(
        "\nFörväntat mönster: DSR ska SJUNKA när K stiger, för samma "
        "underliggande data - högre K kräver starkare bevis för att lita "
        "på att SR:n inte bara är den bästa av många slumpmässiga försök."
    )

    # Ren slumpmässig brus (sann SR = 0) vid K=1: DSR ska då reflektera
    # tecknet på den FAKTISKT realiserade sample-SR:n (som pga slumpen
    # sällan blir exakt 0) - inte ett fast tal. Med T=1000 observationer
    # är även en liten slumpmässig avvikelse från SR=0 statistiskt
    # urskiljbar (sqrt(T-1)-skalningen förstärker den), så DSR kan hamna
    # klart över eller under 0.5 beroende på slumpfröet - det är korrekt
    # beteende, inte ett fel.
    noise_returns = rng.normal(loc=0.0, scale=0.01, size=1000)
    noise_result = deflated_sharpe_ratio_from_returns(noise_returns, n_trials=1)
    sign = "positiv" if noise_result["sharpe_ratio"] >= 0 else "negativ"
    print(
        f"\nRent brus (sann edge = 0), K=1: "
        f"SR={noise_result['sharpe_ratio']:.3f} (slumpmässigt {sign} i detta drag)  "
        f"DSR={noise_result['deflated_sharpe_ratio']:.4f}"
    )
