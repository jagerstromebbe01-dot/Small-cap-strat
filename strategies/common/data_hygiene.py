"""
Delad datasanering for prismatriser - upptackt 2026-07-29 vid HYP-012/013.

Ägs inte av nagon enskild hypotes - detta ar en STRUKTURELL brist i
rå-cachen (data/cache/ohlcv/), inte nagot specifikt for en strategi.
En bred kontroll av hela cachen (9017 tickers) visade:
  - 1010 filer (11%) har minst en rad med close/high/low <= 0
  - 3070 filer (34%) har minst en enskild dag med >500% prisrorelse,
    inklusive orimligheter som en 135 769x-rorelse pa en dag och
    oandliga varden (division med en tidigare nollrad)

HYP-008/009/011 (par-baserade, valjer bara ett fatal narmast-korrelerade
kandidater per manad) rakade undvika att detta fick storre effekt.
HYP-012 (momentum, rankar HELA universumet) och HYP-013 (reversal,
rankar HELA universumet) exponerades direkt - HYP-012 fick ett
portfoljvarde som gick negativt (degenererad beta pa en tunt handlad
ticker), HYP-013 kraschade med ZeroDivisionError (ett pris exakt 0.0).

UPPDATERAD 2026-07-29 (djupare grundorsak, inte bara en punktfix): efter
att ha fixat ovanstaende hittade HYP-012 fortfarande en extrem trade
(BKGMD, +48 700% pa en manad). Undersokning visade att detta INTE var
ett enskilt hopp - priset gick 0.03 -> 14.40 -> 7125 och lag sedan
DODFRUSET pa exakt 7125.00 i flera manader, med VOLYM=0 nastan varje
dag under hela forloppet. Ett rent engangs-hopp-filter (ovan) fangar
bara de tva overgangsdagarna, inte manaderna dar-emellan da priset var
felaktigt men "stabilt". Roten ar mer fundamental: en dag utan handel
(volym=0) har inget verkligt pris att lita pa, oavsett hur "normalt"
priset ser ut jamfort med dagen innan - ingen kunde ha kopt eller salt
till det priset den dagen. clean_price_matrix() tar darfor nu valfritt
en volume-matris och nollstaller close/high/low pa alla dagar med
volym <= 0 eller saknad volymdata, INNAN engangshopp-filtret kors.

Detta ar INTE reverse-engineered fran nagot backtest-resultat - trosklarna
(±80% enskild dag, volym>0) ar valda for att de ar ekonomiskt orimliga/
definitionsmassiga (en aktie kan inte tappa mer an 100% pa en dag; ett
pris utan handel ar inte ett verkligt handelsbart pris) snarare an nagot
kalibrerat mot en specifik strategis resultat.
"""

import numpy as np
import pandas as pd

MIN_DAILY_RETURN = -0.80   # en dag kan aldrig ge mer an -100%, men redan -80% pa EN dag ar extremt ovanligt for riktig handel
MAX_DAILY_RETURN = 5.00    # +500% pa en enda dag - nastan alltid en data-artefakt, inte en riktig rorelse


def clean_price_matrix(close: pd.DataFrame, high: pd.DataFrame = None, low: pd.DataFrame = None,
                        volume: pd.DataFrame = None):
    """
    Rensar en (eller flera, om high/low ges) prismatris:
      1. Om volume ges: dagar med volym <= 0 eller NaN -> close/high/low
         satts till NaN for den tickerns/dagens ruta (ingen handel den
         dagen = inget verkligt pris att lita pa, oavsett hur "normalt"
         prisniva ser ut - detta fangar langvariga felaktiga platan,
         inte bara enskilda hopp).
      2. close/high/low <= 0 -> NaN (ogiltigt pris, inte en riktig handelsdag)
      3. Dagar dar close/close.shift(1) implicerar en avkastning utanfor
         [MIN_DAILY_RETURN, MAX_DAILY_RETURN] -> close (och high/low samma
         dag) satts till NaN. Detta bryter EN dags falska datapunkt utan
         att kasta bort resten av tickerns historik - nasta giltiga dag
         rknar avkastning mot senaste GILTIGA close (pandas pct_change
         hoppar over NaN naturligt).
      4. Appliceras iterativt (tva pass) eftersom en enskild trasig rad
         annars kan ge TVA falska extremrorelser (en in, en ut ur den
         trasiga raden) - andra passet fangar det som blir kvar efter
         forsta passets NaN-sattning.

    Returnerar samma antal DataFrames som gavs in for close/high/low
    (1-3 stycken) - volume returneras ALDRIG, den anvands bara for att
    filtrera, ropande kod behaller sin egen volume-referens.
    """
    close = close.copy()
    if high is not None:
        high = high.copy()
    if low is not None:
        low = low.copy()

    if volume is not None:
        no_trade = volume.reindex_like(close).isna() | (volume.reindex_like(close) <= 0)
        close = close.mask(no_trade)
        if high is not None:
            high = high.mask(no_trade)
        if low is not None:
            low = low.mask(no_trade)

    close = close.where(close > 0)
    if high is not None:
        high = high.where(high > 0)
    if low is not None:
        low = low.where(low > 0)

    # VIKTIGT (upptäckt 2026-07-29, HYP-014, ticker "HEC" - ANDRA gången
    # samma kategori bugg hittas, se BKGMD ovan): ett dag-mot-foregaende-
    # dag-filter (aven med ffill over redan maskade granndagar) har ett
    # eget grundfel - det flaggar BADE ingangen i en trasig platan OCH
    # ateratergangen ur den, eftersom en retur pa -99.98% (frisk niva
    # aterstalld efter en falsk topp) ser statistiskt identisk ut med en
    # retur pa -99.98% (fallande IN i en falsk botten). HEC:s riktiga
    # aterhamtning till ~9 efter en 60 000-svit flaggades felaktigt som
    # "trasig" av just det skalet.
    #
    # Losning: jamfor varje dags pris mot ett LOKALT MEDIANPRIS (ett
    # fonster centrerat kring dagen, alltsa med bade historik OCH framtid
    # inom fonstret) istallet for bara foregaende dag. Detta ar INTE
    # look-ahead i backtestmening (ingen handelssignal anvander detta -
    # det ar bara ett stad-steg pa radata innan NAGON signal beraknas) -
    # en tillfallig felaktig topp/botten paverkar bara ett fatal dagar av
    # ett brett fonster och flaggas darfor korrekt som avvikande, medan en
    # AKTA varaktig prisnivaforandring (t.ex. IDTYD:s riktiga 35x-uppgang
    # pa verklig volym, som INTE ska rensas bort) sa smaningom dominerar
    # sitt eget lokala fonster och slutar flaggas efter overgangsdagarna.
    MEDIAN_WINDOW = 21
    OUTLIER_RATIO_HIGH = 10.0   # >10x det lokala medianpriset
    OUTLIER_RATIO_LOW = 0.10    # <10% av det lokala medianpriset

    local_median = close.rolling(MEDIAN_WINDOW, center=True, min_periods=5).median()
    ratio_to_median = close / local_median
    bad = (ratio_to_median > OUTLIER_RATIO_HIGH) | (ratio_to_median < OUTLIER_RATIO_LOW)
    bad = bad & close.notna() & local_median.notna()
    close = close.mask(bad)
    if high is not None:
        high = high.mask(bad)
    if low is not None:
        low = low.mask(bad)

    # Kvarvarande enskilda hopp (t.ex. i utkanten av serien, dar det
    # centrerade medianfonstret saknar tillrackligt med data at ena
    # hallet for en tillforlitlig lokal median) fangas fortfarande av ett
    # enklare dag-mot-dag-filter som andra lager.
    for _pass in range(5):
        prior_valid = close.shift(1).ffill()
        ratio = close / prior_valid
        bad2 = ((ratio - 1) < MIN_DAILY_RETURN) | ((ratio - 1) > MAX_DAILY_RETURN)
        bad2 = bad2 & close.notna()
        if not bad2.values.any():
            break
        close = close.mask(bad2)
        if high is not None:
            high = high.mask(bad2)
        if low is not None:
            low = low.mask(bad2)

    results = [close]
    if high is not None:
        results.append(high)
    if low is not None:
        results.append(low)
    return tuple(results) if len(results) > 1 else results[0]


if __name__ == "__main__":
    # Sanity-check med SYNTETISK data. Langre serier (40 dagar) an de
    # trasiga sviterna sjalva (5 dagar) - annars blir MEDIAN_WINDOW=21
    # inte "lokalt" langre relativt seriens totala langd, vilket gav
    # missvisande testresultat i en tidigare, for kort version av detta
    # testet (10 rader).
    n = 40
    dates = pd.date_range("2020-01-01", periods=n)

    a = np.full(n, 10.0); a[2] = 0.0                                   # en trasig nollrad
    b = np.full(n, 5.0); b[3] = 700.0                                  # en orimlig spike
    c = np.concatenate([np.full(3, 1.0), np.full(n - 3, 500.0)])       # BKGMD-monstret: hopp + dodfruset platan resten av serien
    d = np.full(n, 9.0); d[3:8] = [60000, 67800, 60000, 68400, 61000]  # HEC-monstret: 5-dagars trasig svit, aterhamtar sig till ~9
    e = np.full(n, 9.0); e[10:] = np.linspace(9, 300, n - 10)          # AKTA varaktig prisnivaforandring (som IDTYD) - ska INTE rensas bort

    df = pd.DataFrame({"A": a, "B": b, "C": c, "D": d, "E": e}, index=dates)

    vol = pd.DataFrame({
        "A": [100] * n,
        "B": [100] * n,
        "C": [100, 100, 100] + [0] * (n - 3),                         # noll volym under hela den felaktiga platan
        "D": [500000] * 3 + [1000, 100, 100, 100, 800] + [500000] * (n - 8),  # kraftigt men INTE noll under sviten
        "E": [500000] * n,                                             # normal volym hela tiden - en riktig, handlad omvardering
    }, index=dates)

    print("Fore (rad 0-9 av 40):")
    print(df.head(10))
    cleaned = clean_price_matrix(df, volume=vol)
    print("\nEfter (rad 0-9 av 40):")
    print(cleaned.head(10))
    print(f"\nD (HEC-monstret): antal NaN i den trasiga femdagarssviten (index 3-7): {cleaned['D'].iloc[3:8].isna().sum()} av 5 (vantat: 5)")
    print(f"D: sista tva vardena (index 8-9, aterhamtat ~9) fortfarande giltiga: {cleaned['D'].iloc[8:10].notna().sum()} av 2 (vantat: 2)")
    print(f"E (AKTA prisnivaforandring): antal NaN totalt: {cleaned['E'].isna().sum()} (vantat: 0 eller nastan 0 - far INTE rensas bort)")
    print(f"E: sista vardet (ska vara ~300, den nya riktiga nivan): {cleaned['E'].iloc[-1]}")
