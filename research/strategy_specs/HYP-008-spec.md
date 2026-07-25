# Strategispec: HYP-008 — v6-kärna replikerad på small-cap

**Skriven av:** Strategy Builder (`/agents/strategy_builder/ROLE.md`)
**Källhypotes:** `/research/hypothesis_registry/HYP-008-v6-smallcap-replication.yaml`
**Input-krav bekräftade:** `status: pre-registered` ✅, `pass_fail_criterion`
ifyllt ✅ (låst 2026-07-24 av CEO). Detta är en spec, INTE körbar kod —
Coder implementerar från den.

---

## 1. Universum

Från hypotesens `small_cap_definition`: **$100M–$2B börsvärde, EODHD
All-World som datakälla.**

- Tickerkälla: `/data/eodhd_adapter.py::get_smallcap_universe()`
  (`MIN_CAP=100_000_000`, `MAX_CAP=2_000_000_000`, `include_delisted=True`).
- Avlistade bolag måste vara med (survivorship bias) — redan implementerat
  i adaptern via `&delisted=1`.
- **Känd begränsning att bära vidare till Coder:** adapterns
  `get_market_cap()` returnerar senast kända börsvärde, inte historiskt
  börsvärde vid varje handelsdag. För en strikt korrekt replikering borde
  universumet omdefinieras löpande (månadsvis, som `identify_pairs()`
  redan gör för par) baserat på börsvärde VID DEN TIDPUNKTEN — annars
  smyger sig en mild look-ahead-snedvridning in (bolag inkluderas/
  exkluderas baserat på var de slutade, inte var de var). Flaggat här,
  inte löst — Risk Manager bör granska innan resultat litas på.

## 2. Signaler — identiska med v6-kärnan, inga nya alfa-idéer

Per hypotesens låsta kriterium ("v6-kärnan, identisk kod") och
Strategy Builders hårda regel (inga nya alfa-idéer i v1): signalerna
återanvänds ORÖRDA från `/reference_code/v6_core_large_cap.py`.

| Steg | Funktion i referensfilen | Parametrar (identiska, ändras inte) |
|---|---|---|
| Par-identifiering | `identify_pairs()` | `COINT_WINDOW=252`, `MIN_PAIRS=3`, `CORR_THRESH=0.70`, `MAX_PAIRS=8`, månadsvis ombalansering |
| Z-score | `compute_zscore()` | `ZSCORE_WINDOW=63`, rullande OLS, look-ahead-fri |
| Beta/hedge | `compute_beta()` | `BETA_WINDOW=126` |
| Entry/exit | `run_v6_core()` | `TRADE_Z_THRESH=1.5`, exit vid `|z|<0.3`, `STOP_LOSS=0.06` |
| Positionsstorlek | `run_v6_core()` | `FIXED_FRAC=0.05` — FAST storlek, ingen Kelly, ingen ejay |
| Max samtidiga positioner | `run_v6_core()` | `MAX_POS=12` |
| Riskfri ränta (hedge-kostnad) | `run_v6_core()` | `RF_ANNUAL=0.02` |

**Hedge-instrument (SPY):** behålls oförändrat trots att SPY är ett
large-cap-index och därmed inte nödvändigtvis det metodologiskt
"renaste" hedge-valet för ett small-cap-universum. Detta är medvetet —
kriteriet kräver identisk metodik, och att byta hedge-instrument vore en
metodikändring som i så fall borde vara sin egen, separat
pre-registrerade hypotes (spec-dokumentet avsnitt 5b), inte en
"förbättring" som smygs in här.

## 3. Vad som MÅSTE ändras (datakälla, inte metodik)

- `load_data()` i referensfilen använder `yfinance`. Coder ska INTE
  ändra referensfilen — kopiera den till `/strategies/HYP-008/` och byt
  ENDAST datahämtningsfunktionen mot `/data/eodhd_adapter.py`
  (`get_smallcap_universe()` för universum, `get_daily_ohlcv()` per
  ticker). Signallogiken (`identify_pairs`, `compute_zscore`,
  `compute_beta`, `run_v6_core`) kopieras oförändrad.
- `TICKERS`-listan (hårdkodad large-cap-lista i referensfilen) ersätts
  med det dynamiska small-cap-universumet från adaptern.

## 4. Ny beräkning som kriteriet kräver (inte i referensfilen som den är)

Hypotesens `pass_fail_criterion` punkt 3 kräver: **Sharpe/Calmar-kraven i
punkt 1 måste hålla även efter att bästa enskilda traden exkluderats**
(outlier-skydd). `/reference_code/v6_core_large_cap.py` har idag ingen
sådan funktion. Coder behöver lägga till en liten beräkning ovanpå
befintlig `trade_log`/`sharpe()`/`calmar()` — ta bort trade:n med högst
`ret` i `trade_log`, räkna om portföljvärdeserien (eller en approximation
därav), och rapportera Sharpe/Calmar utan den traden. Detta räknas INTE
som en ny alfa-idé (ingen ny signal, inget nytt filter) — det är ett
robusthetsmått kriteriet redan kräver.

## 5. Kapitalnivåer

Kör identisk strategi vid `tested_capital_levels: [100000, 1000000, 10000000]`
(startkapital i `run_v6_core`/motsvarande, i stället för `cash=1.0`).
`FIXED_FRAC=0.05` skalar naturligt med kapitalbasen, men vid $10M i ett
small-cap-universum ($100M–$2B bolag) är market impact/slippage en reell
risk som inte fångas av nuvarande platshållar-friktionsfält — se punkt 6.

## 6. Kända blockerare innan detta kan köras skarpt (för protokollet, löses inte här)

1. **EODHD-prenumerationen medger idag bara ~1 års historik** — hypotesens
   mål (2010–2024) går inte att köra förrän kontot uppgraderats
   (flaggat till CEO 2026-07-24).
2. **Friktionsfälten (`borrow_cost`, `borrow_available`, `bid_ask_spread`)
   är `None`-platshållare i adaptern.** Ett resultat på dessa är
   preliminärt — Risk Manager ska blockera det som slutgiltigt svar på
   hypotesen tills riktig friktionsdata finns.
3. Historiskt (inte bara senast kända) börsvärde per ticker — se punkt 1.

## 7. Rekommenderad kodstruktur för Coder

```
/strategies/HYP-008/
  backtest.py        # kopia av v6_core_large_cap.py-logiken, load_data
                      # bytt mot eodhd_adapter, resten oförändrat
  outlier_check.py    # bästa-trade-exkluderad-beräkningen (punkt 4 ovan)
  results/            # Backtesters output per kapitalnivå
```

Coder måste köra `python scripts/validate_hypothesis.py
research/hypothesis_registry/HYP-008-v6-smallcap-replication.yaml` och få
exit code 0 innan Backtester får exekvera något av ovanstående.
