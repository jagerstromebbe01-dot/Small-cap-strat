"""
Risk Factors-textlikhet (BATCH-004, HYP-093-096) - delad extraktions-
och likhetslogik. Kopiera INTE per hypotes, samma delad-modul-princip
som accrual_engine.py/crypto_data.py.

EXTRAKTIONSHEURISTIK - version 2, 2026-08-13 (v1 gav 87% miss vid en
fullskalig stickprovskörning, se filens historik i git för v1). v1
antog att den RIKTIGA sektionsrubriken alltid är versal medan TOC/
korsreferenser är Title Case (sant för testdokumentet GameStop) - ett
bredare stickprov (25 slumpmässiga bolag) visade att detta antagande
INTE håller generellt:
  - AACI_old (CIK 1844817): TOC:en är ÄVEN DEN versal ("ITEM 1A. RISK
    FACTORS 20 ITEM 1B...", med sidnummer) - v1 tog FÖRSTA versala
    träffen (TOC-raden), gav en näst intill tom sektion.
  - CLDB: den RIKTIGA rubriken är ALDRIG versal, bara Title Case, och
    med en ovanlig mellanslagsvariant ("Item 1A . Risk Factors",
    mellanslag FÖRE punkten) - v1:s versal-krav matchade noll gånger.

Slutsats: skiftläge är INTE en pålitlig signal - olika
arkiveringsleverantörer (Donnelley, Toppan, Workiva m.fl.) formaterar
olika. v2 söker case-INSENSITIVT (bredare nät) och avgör istället per
KANDIDAT om träffen är den riktiga rubriken via två oberoende
kontroller: (1) LÄNGDVALIDERING - avståndet till nästa Item 1B/Item
2-träff måste falla inom ett rimligt intervall (för kort = TOC/
korsreferens, orimligt långt = fel startpunkt som råkade hoppa förbi
den riktiga Item 1B-gränsen), (2) KORSREFERENS-VAKT - de ~70 tecknen
FÖRE träffen får inte innehålla fraser som typiskt inleder en
hänvisning till avsnittet ("see \"", "under the heading", "described
in", "discussed in", "elsewhere in", "captioned") snarare än att
STARTA det. Första kandidaten som klarar båda kontrollerna används.

VIKTIGT (disclosad begränsning, INTE dold): även v2 är en heuristik,
inte en perfekt parser - stickprovsverifierad mot 4+25 riktiga
dokument (se fetch_10k_text_similarity.py:s sanity-check-utskrift för
den löpande felfrekvensen på den FAKTISKA körningen). En kvarstående
felfrekvens över 0% är väntad och accepterad, INTE dold - se
HYP-093:s registerpost för tröskeln (>20% flaggas explicit).
"""

import html
import re

import numpy as np

# Case-INSENSITIVT (se v2-motivering ovan) - tillåter valfritt
# mellanslag/skiljetecken mellan "1A" och "Risk Factors" (täcker både
# "1A." och "1A ." och "1A -").
ITEM_1A_HEADER_RE = re.compile(r"item\s+1a[\.\s\-–—]*\s*risk\s+factors", re.IGNORECASE)
ITEM_1B_HEADER_RE = re.compile(r"item\s+1b[\.\s\-–—]", re.IGNORECASE)
ITEM_2_HEADER_RE = re.compile(r"item\s+2[\.\s\-–—]", re.IGNORECASE)

MIN_SECTION_LENGTH = 500
# 500_000 (höjt från ett initialt 250_000 efter stickprovsfynd 2026-08-13):
# DAWN (klinisk-fas biotech) hade en VERIFIERAT genuin, sammanhängande
# Risk Factors-sektion på 349 214 tecken (kontrollerat innehåll vid
# 100k/250k/320k tecken in - FDA/klinisk risk, patent/konkurrensrisk,
# aktiekursrisk hela vägen, ingen drift till orelaterat innehåll) -
# 250_000 var för snålt, inte en riktig orimlighetsgräns.
MAX_SECTION_LENGTH = 500_000
CROSS_REFERENCE_GUARD_RE = re.compile(
    r'(see\s+"|under\s+the\s+heading|described\s+in|discussed\s+in|elsewhere\s+in|captioned|titled|as\s+set\s+forth\s+in|referred\s+to\s+in)\s*$',
    re.IGNORECASE,
)

ENGLISH_STOPWORDS = frozenset("""
a an and are as at be by for from has have if in into is it its of on or
our that the their there these this to was we were will with you your
not but can may might should would shall could
""".split())


def strip_html(raw_html: str) -> str:
    """html.unescape() FORE regex-taggstripp - se moduldocstringen for
    varfor ordningen ar kritisk (annars missas entitetskodade
    versionersioner av rubrikmonstret)."""
    text = html.unescape(raw_html)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_item_1a(raw_html: str, min_length: int = MIN_SECTION_LENGTH,
                     max_length: int = MAX_SECTION_LENGTH) -> str | None:
    """Returnerar Item 1A-textens innehåll, eller None om extraktionen
    misslyckas (för kort/för lång/ingen träff klarar vakterna - hellre
    exkludera en observation än att smyga in brus i signalen). Se
    moduldocstringens v2-avsnitt för den fullständiga motiveringen.

    Prövar VARJE case-insensitiv "Item 1A ... Risk Factors"-träff i
    dokumentordning. För varje kandidat: (1) avvisa om de ~70 tecknen
    FÖRE träffen matchar ett korsreferens-mönster ("see \"...", "under
    the heading...") - det är en MENING OM avsnittet, inte avsnittets
    egen start. (2) Beräkna slutet som nästa Item 1B/Item 2-träff
    DÄREFTER, avvisa om den resulterande sektionen är kortare än
    min_length (TOC/korsreferens - nästa rubrik står precis intill)
    ELLER längre än max_length (fel startpunkt som råkade hoppa förbi
    den riktiga Item 1B-gränsen, sektionen innehåller då sannolikt
    orelaterat innehåll däremellan). Första kandidaten som klarar båda
    vakterna returneras."""
    text = strip_html(raw_html)

    header_matches = list(ITEM_1A_HEADER_RE.finditer(text))
    if not header_matches:
        return None

    for m in header_matches:
        preceding = text[max(0, m.start() - 70):m.start()]
        if CROSS_REFERENCE_GUARD_RE.search(preceding):
            continue

        start = m.end()
        end_match = ITEM_1B_HEADER_RE.search(text, pos=start)
        if not end_match:
            end_match = ITEM_2_HEADER_RE.search(text, pos=start)
        end = end_match.start() if end_match else min(start + max_length, len(text))
        section = text[start:end].strip()
        if min_length <= len(section) <= max_length:
            return section
    return None


def _tokenize(text: str) -> list:
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return [w for w in words if w not in ENGLISH_STOPWORDS and len(w) > 1]


def jaccard_similarity(text_a: str, text_b: str) -> float | None:
    set_a, set_b = set(_tokenize(text_a)), set(_tokenize(text_b))
    if not set_a or not set_b:
        return None
    return len(set_a & set_b) / len(set_a | set_b)


def cosine_similarity_tfidf(text_a: str, text_b: str) -> float | None:
    """Enkel TF-IDF-cosine over ENDAST de tva dokumenten (samma princip
    som sklearn:s TfidfVectorizer, men ingen extern beroende kravs -
    IDF over ett tva-dokuments-korpus reduceras till en enkel
    forekomst-i-endera/badas-vikt, matematiskt ekvivalent for detta
    specifika tva-dokuments-jamforelsefall)."""
    tokens_a, tokens_b = _tokenize(text_a), _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return None
    vocab = sorted(set(tokens_a) | set(tokens_b))
    idx = {w: i for i, w in enumerate(vocab)}

    def _tf_vector(tokens):
        v = np.zeros(len(vocab))
        for w in tokens:
            v[idx[w]] += 1.0
        return v / max(len(tokens), 1)

    tf_a, tf_b = _tf_vector(tokens_a), _tf_vector(tokens_b)
    df = np.array([(tf_a[i] > 0) + (tf_b[i] > 0) for i in range(len(vocab))], dtype=float)
    idf = np.log(2.0 / df)  # 2 dokument totalt i denna parvisa jamforelse
    tfidf_a, tfidf_b = tf_a * idf, tf_b * idf

    norm_a, norm_b = np.linalg.norm(tfidf_a), np.linalg.norm(tfidf_b)
    if norm_a == 0 or norm_b == 0:
        return None
    return float(np.dot(tfidf_a, tfidf_b) / (norm_a * norm_b))
