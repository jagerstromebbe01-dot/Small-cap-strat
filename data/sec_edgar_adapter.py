"""
SEC EDGAR-adapter - gratis, offentlig källa för utestående aktier per
bolag och tidpunkt. Används tillsammans med EODHD:s prisdata
(eodhd_adapter.py) för att räkna ut börsvärde = utestående aktier × pris,
eftersom EODHD:s nuvarande plan saknar Fundamentals/Screener-access
(bekräftat 403 Forbidden, se data/test_eodhd_delisted_depth.py-sessionen
2026-07-27).

Fördel jämfört med EODHD fundamentals (om den hade funkat): detta ger
börsvärde VID RÄTT HISTORISK TIDPUNKT (varje kvartalsrapport har ett
eget aktieantal), inte bara senast kända värde - löser alltså samma
begränsning som redan flaggades i /research/strategy_specs/HYP-008-spec.md
punkt 1.

Ingen API-nyckel behövs. SEC kräver en beskrivande User-Agent-header
(kontaktuppgift) - satt nedan. Rate limit: SEC ber om max ~10 anrop/sek,
denna modul håller sig långt under det.

VIKTIGT (ärlighet om skalbarhet, 2026-07-27): denna modul är byggd och
verifierad mot fyra kända bolag (AAPL, RadioShack, Eastman Kodak,
Patriot Coal). Att automatiskt matcha ALLA ~32 000 EODHD-tickers mot
SEC:s bolagsnamn i skala är ett separat, större jobb (namnmatchning är
tvetydig - flera dotterbolag kan ha snarlika namn, se
find_cik_candidates() nedan som medvetet returnerar flera kandidater
istället för att gissa) och har INTE byggts än - se README/rapport i
chatten för var gränsen drogs.
"""

import json
import re
import time
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent
CACHE_DIR = DATA_DIR / "cache"
CIK_LOOKUP_CACHE = CACHE_DIR / "sec_cik_lookup.txt"
CIK_LOOKUP_URL = "https://www.sec.gov/Archives/edgar/cik-lookup-data.txt"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

USER_AGENT = "smallcap-edge-lab research echo.officialproject@gmail.com"
REQUEST_DELAY = 0.15  # sekunder mellan anrop - långt under SEC:s ~10/sek-gräns

_SUFFIX_RE = re.compile(
    r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LLC|LP|PLC|THE)\b\.?"
)


def _normalize(name: str) -> str:
    """Normaliserar ett bolagsnamn för matchning: versaler, tar bort
    vanliga bolagsformsuffix och skiljetecken, kollapsar mellanslag."""
    n = name.upper()
    n = re.sub(r"[.,]", "", n)
    n = _SUFFIX_RE.sub("", n)
    n = re.sub(r"[^A-Z0-9 ]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _download_cik_lookup() -> str:
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(CIK_LOOKUP_URL, headers=headers, timeout=120)
    resp.raise_for_status()
    return resp.text


def load_cik_lookup(force_refresh: bool = False) -> dict:
    """
    Laddar SEC:s fullständiga namn->CIK-lookup (>1 miljon rader, alla
    bolag som någonsin registrerat sig hos SEC - täcker alltså även
    sedan länge avlistade bolag). Cachas lokalt i data/cache/ eftersom
    filen är ~40MB och inte förändras ofta - laddas INTE om vid varje
    anrop, bara om cachen saknas eller force_refresh=True.

    Returnerar dict: normaliserat namn -> lista av (raw_name, cik).
    Flera bolag kan dela normaliserat namn (t.ex. dotterbolag) - därför
    en lista, inte ett enda värde. Anroparen avgör, gissar inte här.
    """
    CACHE_DIR.mkdir(exist_ok=True)
    if force_refresh or not CIK_LOOKUP_CACHE.exists():
        text = _download_cik_lookup()
        CIK_LOOKUP_CACHE.write_text(text, encoding="utf-8")
    else:
        text = CIK_LOOKUP_CACHE.read_text(encoding="utf-8")

    lookup: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        parts = line.rsplit(":", 2)
        if len(parts) < 2:
            continue
        raw_name = parts[0]
        cik_str = parts[1]
        if not cik_str.isdigit():
            continue
        key = _normalize(raw_name)
        if not key:
            continue
        lookup.setdefault(key, []).append((raw_name, cik_str.zfill(10)))
    return lookup


def find_cik_candidates(company_name: str, lookup: dict) -> list:
    """
    Söker efter CIK-kandidater för ett bolagsnamn. Returnerar EXAKTA
    normaliserade träffar om de finns, annars substrängs-kandidater.
    Returnerar ALLTID en lista - noll, en, eller flera träffar. Gissar
    ALDRIG genom att tyst returnera "den mest troliga" - anroparen (ett
    testskript eller en människa) avgör vid tvetydighet.
    """
    key = _normalize(company_name)
    if key in lookup:
        return lookup[key]

    candidates = []
    for k, entries in lookup.items():
        if key in k or k in key:
            candidates.extend(entries)
    return candidates


def get_shares_outstanding_history(cik: str) -> list:
    """
    Hämtar utestående aktier över tid för ett bolag (CIK, 10 siffror,
    zero-padded). Provar dei:EntityCommonStockSharesOutstanding först,
    faller tillbaka till us-gaap:CommonStockSharesOutstanding.

    Returnerar en lista av {"date": "YYYY-MM-DD", "shares": int},
    sorterad kronologiskt. Tom lista om inget hittas (loggas inte som
    fel här - anroparen avgör om det är oväntat för just det bolaget).
    """
    headers = {"User-Agent": USER_AGENT}
    url = COMPANYFACTS_URL.format(cik=cik)
    resp = requests.get(url, headers=headers, timeout=30)
    time.sleep(REQUEST_DELAY)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    data = resp.json()

    facts = data.get("facts", {})
    for namespace, tag in (("dei", "EntityCommonStockSharesOutstanding"),
                           ("us-gaap", "CommonStockSharesOutstanding")):
        entries = facts.get(namespace, {}).get(tag, {}).get("units", {}).get("shares")
        if entries:
            history = sorted(
                ({"date": e["end"], "shares": e["val"]} for e in entries if e.get("end") and e.get("val")),
                key=lambda x: x["date"],
            )
            if history:
                return history
    return []


def shares_outstanding_at(history: list, target_date: str):
    """
    Utestående aktier vid target_date, enligt SENASTE rapporterade
    värdet PÅ ELLER FÖRE target_date - aldrig ett senare värde
    (look-ahead-fritt). Returnerar None om inget värde finns så tidigt.
    """
    valid = [h for h in history if h["date"] <= target_date]
    if not valid:
        return None
    return valid[-1]  # history är sorterad kronologiskt


def resolve_cik(company_name: str, lookup: dict) -> dict:
    """
    Slår upp CIK för ett bolagsnamn med en rangordningsheuristik istället
    för att blint ta första kandidaten (se test_sec_edgar_market_cap.py
    2026-07-27 där "Patriot Coal Corp" hade två kandidater - fel entitet
    ("PATRIOT COAL CO LP") saknade helt aktiedata, medan rätt entitet
    ("PATRIOT COAL CORP") hade det).

    Logik:
    - Exakt normaliserad matchning, EN kandidat -> "confident", ingen
      extra SEC-fråga behövs för att avgöra.
    - Exakt normaliserad matchning, FLERA kandidater -> hämtar
      aktiehistorik för VARJE kandidat och väljer den som faktiskt HAR
      data. Om exakt en har data -> "resolved_by_data". Om noll eller
      fler än en har data -> "ambiguous", ingen gissning.
    - Ingen exakt matchning, bara substrängsträffar -> "ambiguous",
      väljer aldrig automatiskt.
    - Inga kandidater alls -> "no_candidates".

    Returnerar dict: {status, cik, raw_name, all_candidates, shares_history}
    - shares_history är ifylld när status är "confident" eller
      "resolved_by_data" (vi hämtade den ändå för att avgöra), annars None
      (ingen anledning att slösa SEC-anrop på ett ambiguöst fall som ändå
      ska granskas manuellt).
    """
    key = _normalize(company_name)
    exact = lookup.get(key, [])

    if len(exact) == 1:
        raw_name, cik = exact[0]
        history = get_shares_outstanding_history(cik)
        return {
            "status": "confident",
            "cik": cik,
            "raw_name": raw_name,
            "all_candidates": exact,
            "shares_history": history,
        }

    if len(exact) > 1:
        with_data = []
        for raw_name, cik in exact:
            history = get_shares_outstanding_history(cik)
            if history:
                with_data.append((raw_name, cik, history))
        if len(with_data) == 1:
            raw_name, cik, history = with_data[0]
            return {
                "status": "resolved_by_data",
                "cik": cik,
                "raw_name": raw_name,
                "all_candidates": exact,
                "shares_history": history,
            }
        return {
            "status": "ambiguous",
            "cik": None,
            "raw_name": None,
            "all_candidates": exact,
            "shares_history": None,
        }

    substring_candidates = find_cik_candidates(company_name, lookup)
    if substring_candidates:
        return {
            "status": "ambiguous",
            "cik": None,
            "raw_name": None,
            "all_candidates": substring_candidates,
            "shares_history": None,
        }

    return {
        "status": "no_candidates",
        "cik": None,
        "raw_name": None,
        "all_candidates": [],
        "shares_history": None,
    }


def market_cap_at_date(history: list, close_price: float, target_date: str):
    """
    Börsvärde = senast kända utestående aktier (på eller före
    target_date) × close_price (vid target_date, hämtad separat från
    EODHD). Returnerar None om ingen aktiedata finns så tidigt.
    """
    shares_entry = shares_outstanding_at(history, target_date)
    if shares_entry is None or close_price is None:
        return None
    return shares_entry["shares"] * close_price
