# Strategispec: HYP-019 — Storlekssortering inom small-cap-bandet

**Källhypotes:** `/research/hypothesis_registry/HYP-019-storlekssortering-inom-bandet.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion` ifyllt ✅ (låst 2026-07-30).

## 1. Kodbas

Kopiera `/strategies/HYP-015/backtest.py` till `/strategies/HYP-019/backtest.py`
(INTE HYP-017/018 — detta är ett rent signaltest, ingen krasch-overlay
eller stop-loss ska vara med, i linje med principen att utvärdera
kandidatsignaler före riskoverlägg). Universum, friktion, hedge,
kapacitetsspärr, motorfixar, kvartalsvis ombalansering — allt
oförändrat. Enda skillnaden: signalen.

## 2. Signal — ny datakälla, ingen ny beräkning

`data/cache/market_cap_by_ticker_month.csv` (kolumner: `ticker`, `month`
["YYYY-MM-DD", månadsslut], `shares`, `price`, `market_cap`, `in_band`)
finns redan — samma källa som bygger `smallcap_universe_by_month.json`.
Ladda den, pivotera till en DataFrame (index=month, columns=ticker,
values=market_cap). Vid varje kvartalsvis ombalansering: slå upp
marknadsvärde för `rebal_map[date]` (samma kalenderetikett som redan
används för `universe_by_month`-uppslagningen), rangordna de berättigade
tickarna STIGANDE (lägst marknadsvärde först — motsatt sortering mot
HYP-015 som sorterade lägst-volatilitet-först, men samma "lägst av
måttet" konvention), gå lång lägsta decilen.

Ingen rullande fönsterberäkning behövs (till skillnad från
HYP-015/`compute_idiosyncratic_vol` som kräver ett 120-dagars fönster) -
marknadsvärdet är redan färdigberäknat per månad i cachen.

## 3. Vad som INTE ska vara med

Ingen SPY-krasch-overlay (HYP-017), inget stop-loss (HYP-018), ingen
vol-skalning (HYP-016). Detta är avsiktligt ett rent, oskyddat
signaltest — matcha exakt hur HYP-012/013/014/015 utvärderades.

## 4. Kapitalnivåer och validering

`[100000, 1000000, 10000000]`. Kör
`scripts/validate_hypothesis.py research/hypothesis_registry/HYP-019-storlekssortering-inom-bandet.yaml`
och få exit 0 innan körning.
