# Strategispec: HYP-021 — Idiosynkratisk vol mot small-cap-kompositfaktor

**Källhypotes:** `/research/hypothesis_registry/HYP-021-idio-vol-smallcap-faktor.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-30).

## 1. Kodbas

Kopiera `/strategies/HYP-017/backtest.py` (INTE HYP-015 — HYP-021 bygger
vidare på HYP-017 inklusive krasch-overlayen, som ska vara helt
oförändrad). Universum, friktion, kapacitetsspärr, motorfixar,
krasch-overlay-mekaniken — allt oförändrat.

## 2. Ny komponent: small-cap-kompositfaktor

```python
def compute_smallcap_factor(close_adj):
    """Likaviktat medelvarde av dagliga avkastningar over hela
    small-cap-panelen - anvands ENDAST som referens for
    idio-vol-SIGNALEN, inte som hedgeinstrument (det finns inget
    likvitt, blankningsbart 'small-cap-index' att faktiskt hedga med -
    SPY forblir det riktiga hedgeinstrumentet)."""
    daily_ret = close_adj.pct_change()
    return daily_ret.mean(axis=1)  # nanmean over kolumner - hanterar saknade varden naturligt
```

## 3. Tva separata beta-berakningar

- `beta_hedge = compute_beta(close_adj, hedge_spy, BETA_WINDOW)` — OFÖRÄNDRAD,
  används i `run_backtest()` för `hedge_pnl` (portföljens faktiska
  SPY-hedge), exakt som HYP-017.
- `beta_signal = compute_beta(close_adj, smallcap_factor, BETA_WINDOW)` — NY,
  används ENDAST i `compute_idiosyncratic_vol()` för signalen.

## 4. Signalberäkning — enda ändringen mot HYP-017

```python
vol_df = compute_idiosyncratic_vol(close_adj, smallcap_factor, beta_signal, VOL_LOOKBACK_DAYS)
```
i stället för `compute_idiosyncratic_vol(close_adj, hedge, beta_df, ...)`.
Funktionen `compute_idiosyncratic_vol()` själv är oförändrad — den tar
bara emot en annan referensserie och en annan beta-matris.

## 5. Vad som är OFÖRÄNDRAT

Krasch-overlayen bevakar fortfarande `hedge` (SPY), inte
small-cap-kompositfaktorn — den mekanismen är redan validerad
(leave-one-crisis-out-testet) och ska inte röras. Portföljens
`hedge_pnl`-beräkning i `run_backtest()` använder fortfarande
`beta_hedge` (mot SPY), inte `beta_signal`.

## 6. Kapitalnivåer och validering

`[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py research/hypothesis_registry/HYP-021-idio-vol-smallcap-faktor.yaml`
och få exit 0 innan körning.
