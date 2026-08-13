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


def mask_unrecovered_price_breaks(close: pd.DataFrame) -> pd.DataFrame:
    """
    Upptäckt 2026-08-09/10 (HYP-049, tickern SSN): clean_price_matrix()s
    iterativa dag-till-dag-filter ovan är konstruerat för KORTLIVADE
    trasiga svitar - varje pass fångar exakt EN ytterligare dag (den dag
    vars närmast föregående dag just maskades i FÖRRA passet, se
    "prior_valid = close.shift(1).ffill()" ovan), så det kan som mest
    maska 5 på varandra följande trasiga dagar (dess hårdkodade
    passantal, `for _pass in range(5)`) innan det ger upp och släpper
    igenom resten av en LÄNGRE trasig svit som "giltig" data.

    SSN:s rådata hoppade ~54600x den 2017-11-17 (open/high/low/close/
    adjusted_close SAMTIDIGT, med verkligt-utseende volym på 100-300k/
    dag) och ÅTERHÄMTADE SIG ALDRIG under resten av dess registrerade
    historik (till 2020-10-08, filens sista dag) - ett leverantörs-
    datafel/tickerkollision, samma kategori som ESSA (se
    flag_implausible_liquidity ovan), men UTAN att varje enskild dags
    dollarvolym tillförlitligt överstiger den funktionens
    marknadsvärde-tröskel (SSN:s dagliga dollarvolym pendlar kring 1-2x
    max_market_cap i den nya regimen, inte konsekvent långt över), OCH
    med en egen "kallstart"-fördröjning (den funktionens rullande
    fönster kräver `window` SAMMANHÄNGANDE giltiga dagar innan den
    någonsin kan flagga - se dess docstring) som tillsammans med
    clean_price_matrix()s 5-dagars-gräns släppte igenom de första ~24
    handelsdagarna av den trasiga regimen som "giltiga" - inklusive
    exakt den dag en HYP-049-kvartalsombalansering råkade hålla namnet,
    vilket gav en ensam +$16 miljoner (från ett $45k-konto) fiktiv
    daglig värdering rätt in i backtestens resultat.

    Detta är en MEDVETET SEPARAT, ADDITIV kontroll - ändrar INTE
    clean_price_matrix()s eller flag_implausible_liquidity()s befintliga
    beteende eller default-anrop (så ingen redan låst hypotes påverkas
    retroaktivt om dess kod skulle köras om) - anropande kod måste
    explicit välja in den. Använder EXAKT samma ekonomiska-orimlighets-
    trösklar som redan etablerade i MIN_DAILY_RETURN/MAX_DAILY_RETURN
    ovan (ingen ny, godtyckligt vald gräns) - frågan är inte "är detta
    steg för stort" (det svarar clean_price_matrix redan på), utan
    "löste sig detta steg NÅGONSIN inom seriens återstående historik,
    eller är det permanent".

    Går igenom varje tickers giltiga (icke-NaN) prisvärden i
    tidsordning. När ett steg från den senast ACCEPTERADE referensen
    implicerar en avkastning utanför [MIN_DAILY_RETURN, MAX_DAILY_RETURN]
    (samma tröskel som clean_price_matrix), sök FRAMÅT i seriens
    återstående värden efter första punkten som ÅTER ligger innanför
    den bandbredden relativt SAMMA referens. Om en sådan punkt hittas:
    maska allt DÄREMELLAN (den trasiga svitens hela längd, oavsett hur
    lång den är - ingen 5-pass-gräns), och fortsätt från
    återhämtningspunkten som ny referens. Om ingen sådan punkt någonsin
    hittas: maska allt från brottpunkten till seriens slut (permanent -
    ingen verklig small-/micro-cap-aktie gör ett MAX_DAILY_RETURN-
    brytande hopp och stannar där för gott utan att det är ett datafel,
    se SSN ovan).

    En ÄKTA, VARAKTIG prisnivå-förändring (som IDTYD, se ovan) sker per
    definition INTE som ETT enda steg utanför [MIN_DAILY_RETURN,
    MAX_DAILY_RETURN] (annars hade clean_price_matrix redan maskat
    ÖVERGÅNGSDAGEN som en trasig engångsspik, med samma motivering som
    redan gäller där) - så denna funktion påverkar inte det fallet,
    verifierat mot samma "E"-testfall som redan finns i __main__ nedan.
    """
    close = close.copy()
    lo, hi = 1.0 + MIN_DAILY_RETURN, 1.0 + MAX_DAILY_RETURN

    for col in close.columns:
        s = close[col]
        valid_mask = s.notna()
        if valid_mask.sum() < 2:
            continue
        idxs = s.index[valid_mask]
        vals = s.loc[idxs].to_numpy(dtype=float)

        to_mask_positions = []
        ref = vals[0]
        i = 1
        n = len(vals)
        while i < n:
            if ref == 0 or np.isnan(ref):
                ref = vals[i]
                i += 1
                continue
            ratio = vals[i] / ref
            if lo <= ratio <= hi:
                ref = vals[i]
                i += 1
                continue

            # Brott: sök framåt efter första återhämtning mot SAMMA referens.
            recovered_at = None
            for j in range(i, n):
                r2 = vals[j] / ref
                if lo <= r2 <= hi:
                    recovered_at = j
                    break

            end = recovered_at if recovered_at is not None else n
            to_mask_positions.extend(range(i, end))
            if recovered_at is not None:
                ref = vals[recovered_at]
                i = recovered_at + 1
            else:
                break  # aldrig återhämtad - resten redan maskad via range(i, n)

        if to_mask_positions:
            mask_dates = idxs[to_mask_positions]
            close.loc[mask_dates, col] = np.nan

    return close


def mask_implausible_adjusted_close_ratio(close: pd.DataFrame, close_adj: pd.DataFrame) -> pd.DataFrame:
    """
    Upptackt 2026-08-06 (HYP-042, tickern ABWND): en KONSTANT (inte
    enskild-dags) orimlig close_adj/close-kvot (~30 000x genom hela
    historiken) - ett trasigt justeringstal fran datakallan, inte en
    riktig split. clean_price_matrix() ovan fangar bara enskilda dagars
    orimliga AVKASTNINGAR; en konstant felskalning ger normal avkastning
    varje dag (kvoten ar ju konstant) och slinker darfor igenom
    obemarkt. Maskar close_adj till NaN dar kvoten > 100x eller < 0.01x
    (samma trosklar som redan anvands, hittills bara som kopierad
    inline-kod, i HYP-042 t.o.m. HYP-047) - centraliserad har 2026-08-08
    sa hela HYP-017/021/023/037-kedjan ocksa far fixen. Paverkar aldrig
    close, bara close_adj.
    """
    ratio = (close_adj / close).replace([np.inf, -np.inf], np.nan)
    implausible = (ratio > 100) | (ratio < 0.01)
    return close_adj.mask(implausible)


def flag_implausible_liquidity(close: pd.DataFrame, volume: pd.DataFrame,
                                max_market_cap: float, window: int = 20,
                                multiplier: float = 1.0) -> pd.DataFrame:
    """
    Upptackt 2026-07-29 (HYP-014, ticker "ESSA"): clean_price_matrix():s
    lokala-median-filter ar MEDVETET konstruerat för att INTE rensa bort
    en akta, varaktig prisnivaforandring pa riktig volym (se "E"/IDTYD-
    fallet ovan) - men det gor den blind for en annan sorts fel: en
    leverantors-datafel dar en small-cap-ticker borjar servera en HELT
    ANNAN akties pris+volym (troligen en tickerkollision mot en annan
    borsnoterad post), som sedan hander sig vara "stabil" i sitt eget
    lokala fonster precis som ett akta omvarderingsfall. ESSA gick fran
    ~$19 till ~$510 den 2023-12-15 och lag sedan KVAR dar i manader, med
    daglig dollarvolym pa $10-20 MILJARDER - for ett bolag klassificerat
    i $100M-$2B-bandet. Ingen prismonster-baserad detektor (lokal median
    eller annars) kan skilja detta fran ett akta 27x-uppsving pa riktig
    volym, eftersom bada ser statistiskt identiska ut i just
    pris/volym-terminologi.

    Losningen ligger inte i prismonstret utan i EKONOMISK RIMLIGHET:
    ett bolag kan inte, i genomsnitt over `window` handelsdagar, handla
    for mer dollar an HELA sitt antagna maximala marknadsvarde varje
    enda dag - det skulle innebara att mer an 100% av bolagets totala
    varde byter agare dagligen, sett over en manad, vilket ingen riktig
    aktie nagonsin gor (avgorande skillnad fran ett enskilt handelsdygn
    med hog omsattning kring en nyhet - HAR kravs det HALLA i sig over
    hela `window`-fonstret via rullande medelvarde).

    Returnerar en boolesk DataFrame (samma form som close), True dar den
    rullande `window`-dagars genomsnittliga dollarvolymen overstiger
    `multiplier * max_market_cap`. Anropande kod maskar close/high/low
    till NaN dar detta ar True (samma monster som no_trade-masken i
    clean_price_matrix ovan) - anvands separat, INTE inbakat i
    clean_price_matrix, eftersom det kraver en universum-specifik
    parameter (max_market_cap) som den funktionen inte kanner till.
    """
    dollar_volume = (close * volume).rolling(window).mean()
    return dollar_volume > (multiplier * max_market_cap)


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

    print("\n--- flag_implausible_liquidity: ESSA-monstret (leverantors-tickerkollision) ---")
    # F: identisk konstruktion som E (varaktig, "stabil" prisnivaforandring
    # pa riktig volym) - clean_price_matrix() ska INTE rensa bort den, av
    # samma skal som E - men till skillnad fran E:s IDTYD-forebild (ett
    # akta small-cap-bolag som steg 35x) har F:s nya nivas dollarvolym en
    # storleksordning som ar OMOJLIG for nagot bolag i $100M-$2B-bandet:
    # ~$500 * 30 miljoner aktier/dag = $15 md/dag, mot ett antaget max
    # marknadsvarde pa $2 md - bolaget skulle handla >7x sitt eget hela
    # varde varje dag, i genomsnitt over tre veckor. Det ar signaturen
    # pa en tickerkollision (ESSA), inte en akta omvardering (IDTYD).
    #
    # Egen, langre serie (80 dagar, overgang vid index 20) - bara for
    # detta testet. Behovs eftersom rolling(20)-fonstret kraver 20 RENA
    # (icke-NaN) observationer i rad for att ge ett varde alls; med den
    # kortare 40-dagarsserien ovan (anpassad for A-E) hinner fonstret
    # aldrig helt lamna de fa overgangsdagar clean_price_matrix maskar
    # innan serien tar slut, vilket gav ett missvisande testresultat i en
    # tidigare, for kort version av just detta testet - exakt samma
    # lardom som kommentaren om MEDIAN_WINDOW ovan.
    n2 = 80
    dates2 = pd.date_range("2020-01-01", periods=n2)
    e2 = np.full(n2, 9.0); e2[10:] = np.linspace(9, 300, n2 - 10)

    f_close = np.full(n2, 15.0)
    f_close[20:] = 510.0
    f_volume = np.full(n2, 50_000.0)
    f_volume[20:] = 30_000_000.0

    close_f = pd.DataFrame({"E": e2, "F": f_close}, index=dates2)
    volume_f = pd.DataFrame({"E": [500000] * n2, "F": f_volume}, index=dates2)

    cleaned_f = clean_price_matrix(close_f, volume=volume_f)
    # Nagra fa dagar precis vid overgangen kan maskas av det befintliga
    # dag-mot-dag-fallback-filtret (samma som for D/HEC) - det ar
    # korrekt och ofarligt har, eftersom flag_implausible_liquidity
    # nedan anda tar hand om HELA den nya (felaktiga) nivan sa fort det
    # rullande fonstret fyllts med rena observationer efter overgangen.
    print(f"F efter clean_price_matrix ENSAM: antal NaN nara overgangen (index 10-20) = "
          f"{int(cleaned_f['F'].iloc[10:20].isna().sum())} (forvantat > 0 men FA - inte hela sviten)")
    print(f"F: sista 10 vardena fortfarande giltiga (steady-state, som for E/IDTYD): "
          f"{int(cleaned_f['F'].iloc[-10:].notna().sum())} av 10")

    implausible = flag_implausible_liquidity(cleaned_f, volume_f, max_market_cap=2_000_000_000)
    print(f"F flaggad av flag_implausible_liquidity, sista 10 dagarna (fonstret fullt av den nya nivan): "
          f"{int(implausible['F'].iloc[-10:].sum())} av 10 (vantat: 10 - hela steady-state-perioden ska flaggas)")
    print(f"E flaggad av flag_implausible_liquidity (akta IDTYD-monster, normal volym): "
          f"{int(implausible['E'].sum())} av {n} dagar (vantat: 0 - ska INTE flaggas)")
    print("\n(Validerat separat mot RIKTIG ESSA-data 2026-07-29: clean_price_matrix maskar bara "
          "6 av 227 dagar i overgangsfonstret, medan flag_implausible_liquidity fangar 171 av 227 "
          "dagar - hela den felaktiga regimen fran ~6 veckor efter overgangen och framat, sa fort "
          "det rullande 20-dagarsfonstret fyllts med rena observationer fran den nya nivan.)")

    print("\n--- mask_unrecovered_price_breaks: SSN-monstret (permanent, aldrig aterhamtad regimforandring) ---")
    # G: SSN-monstret - ett brott >MAX_DAILY_RETURN som ALDRIG aterhamtar
    # sig till narheten av foregangsnivan under seriens aterstaende
    # historik (till skillnad fran D/HEC ovan, som aterhamtar sig efter
    # 5 dagar). Egen 60-dagars serie for tillrackligt "aterstaende
    # historik" efter brottet att bevisa att det verkligen aldrig
    # aterhamtar sig.
    n3 = 60
    dates3 = pd.date_range("2020-01-01", periods=n3)
    g = np.full(n3, 0.35)
    g[15:] = 19500.0 - np.arange(n3 - 15) * 10.0   # sjunker sakta men ALDRIG i narheten av 0.35 igen
    d3 = np.full(n3, 9.0); d3[20:25] = [60000, 67800, 60000, 68400, 61000]  # samma HEC-monster, i denna langre serie
    e3 = np.full(n3, 9.0); e3[15:] = np.linspace(9, 300, n3 - 15)           # akta varaktig forandring, ska INTE rensas

    df3 = pd.DataFrame({"G": g, "D": d3, "E": e3}, index=dates3)
    fixed3 = mask_unrecovered_price_breaks(df3)

    print(f"G (SSN-monstret): antal NaN fran brottpunkten (index 15) och framat: "
          f"{int(fixed3['G'].iloc[15:].isna().sum())} av {n3 - 15} (vantat: {n3 - 15} - HELA resten ska maskas, "
          f"ingen aterhamtning sker nagonsin)")
    print(f"G: vardena FORE brottet fortfarande giltiga: {int(fixed3['G'].iloc[:15].notna().sum())} av 15 (vantat: 15)")
    print(f"D (HEC-monstret, aterhamtar sig): antal NaN i den trasiga femdagarssviten (index 20-24): "
          f"{int(fixed3['D'].iloc[20:25].isna().sum())} av 5 (vantat: 5 - maskas AVEN utan clean_price_matrix forst, "
          f"denna funktion loser samma fall pa egen hand)")
    print(f"D: vardena EFTER aterhamtningen (index 25+) fortfarande giltiga: "
          f"{int(fixed3['D'].iloc[25:].notna().sum())} av {n3 - 25} (vantat: {n3 - 25})")
    print(f"E (AKTA varaktig prisnivaforandring, INTE ett enda steg over MAX_DAILY_RETURN): "
          f"antal NaN totalt = {int(fixed3['E'].isna().sum())} (vantat: 0 - far INTE rensas bort, "
          f"samma princip som E-testet ovan)")
