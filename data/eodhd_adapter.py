"""
EODHD-adapter för small-cap-data. Ägs av Data Engineer-rollen, se
/agents/data_engineer/ROLE.md.

Läser EODHD_API_KEY från /data/.env (gitignorad, committas aldrig).
Nyckeln loggas eller skrivs ALDRIG ut i klartext någonstans i denna modul.

KÄND BEGRÄNSNING (small-cap-universum): market cap hämtas som senast
kända värde från fundamentals-endpointen, inte historiskt vid varje
handelsdag. Det är en förenkling i v1 - tillräckligt för en
pipeline-sanity-check, men bör granskas av Overfitting Detector/Risk
Manager innan resultat från en riktig backtest litas på, eftersom det
kan introducera en mild snedvridning i exakt VILKA bolag som räknas in
vid varje historisk tidpunkt.

MIN_CAP/MAX_CAP nedan speglar HYP-008:s låsta small_cap_definition
($100M-$2B, se /research/hypothesis_registry/HYP-008-v6-smallcap-replication.yaml).
Om en framtida hypotes låser ett annat intervall: skicka nya min_cap/
max_cap-argument till get_smallcap_universe(), ändra inte förvalen här
i tysthet - de speglar just HYP-008:s redan låsta kriterium.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

DATA_DIR = Path(__file__).resolve().parent
load_dotenv(DATA_DIR / ".env")

API_KEY = os.environ.get("EODHD_API_KEY", "").strip()
BASE_URL = "https://eodhd.com/api"

MIN_CAP = 100_000_000
MAX_CAP = 2_000_000_000

logger = logging.getLogger("eodhd_adapter")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


class EODHDError(Exception):
    pass


def _require_api_key():
    if not API_KEY:
        raise EODHDError(
            "EODHD_API_KEY saknas eller är tom i /data/.env. Öppna filen, "
            "klistra in nyckeln efter EODHD_API_KEY=, spara, försök igen."
        )


def _get(endpoint: str, params: dict, max_retries: int = 3, backoff: float = 2.0):
    _require_api_key()
    full_params = {**params, "api_token": API_KEY, "fmt": "json"}
    safe_params = {**params, "api_token": "***REDACTED***", "fmt": "json"}
    url = f"{BASE_URL}/{endpoint}"

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(url, params=full_params, timeout=30)
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning(
                f"Nätverksfel mot {endpoint} (försök {attempt}/{max_retries}, "
                f"params={safe_params}): {exc}"
            )
            time.sleep(backoff * attempt)
            continue

        if resp.status_code == 429:
            wait = backoff * attempt
            logger.warning(
                f"Rate limit (429) mot {endpoint}, väntar {wait:.0f}s "
                f"(försök {attempt}/{max_retries})"
            )
            time.sleep(wait)
            continue

        if resp.status_code != 200:
            logger.error(
                f"EODHD svarade {resp.status_code} för {endpoint} "
                f"(params={safe_params}): {resp.text[:300]}"
            )
            raise EODHDError(f"EODHD API-fel {resp.status_code} för {endpoint}")

        try:
            return resp.json()
        except ValueError as exc:
            logger.error(f"Kunde inte tolka JSON-svar från {endpoint}: {resp.text[:300]}")
            raise EODHDError(f"Ogiltigt JSON-svar från {endpoint}") from exc

    raise EODHDError(f"Gav upp mot {endpoint} efter {max_retries} försök: {last_exc}")


def get_us_tickers(include_delisted: bool = True) -> list:
    """
    Hämtar US common-stock-tickers via exchange-symbol-list.
    include_delisted=True lägger till &delisted=1 (enligt EODHD-supportens
    svar) för att inkludera avlistade bolag - kritiskt för att undvika
    survivorship bias i small-cap-universumet.
    """
    params = {"delisted": 1} if include_delisted else {}
    data = _get("exchange-symbol-list/US", params)

    if not isinstance(data, list):
        logger.error(f"Oväntat svarsformat från exchange-symbol-list/US: {type(data)}")
        raise EODHDError("Oväntat svarsformat från exchange-symbol-list/US")

    tickers = [row for row in data if row.get("Type") == "Common Stock"]
    logger.info(
        f"Hämtade {len(tickers)} US common-stock-tickers "
        f"(delisted={include_delisted}) av {len(data)} totalt"
    )
    return tickers


def get_fundamentals(ticker: str) -> Optional[dict]:
    """Hämtar fundamentaldata för en ticker, t.ex. för market cap."""
    data = _get(f"fundamentals/{ticker}.US", {})
    if not isinstance(data, dict) or not data:
        logger.warning(f"Tomt/ogiltigt fundamentals-svar för {ticker}")
        return None
    return data


def get_market_cap(ticker: str) -> Optional[float]:
    """
    Returnerar senast kända börsvärde i USD, eller None om det saknas.
    Se modulens docstring för begränsningen kring avlistade bolag.
    """
    fundamentals = get_fundamentals(ticker)
    if fundamentals is None:
        return None

    highlights = fundamentals.get("Highlights", {}) or {}
    cap = highlights.get("MarketCapitalization")
    if cap in (None, 0, "None", ""):
        logger.warning(f"Ingen market cap-data för {ticker}")
        return None

    try:
        return float(cap)
    except (TypeError, ValueError):
        logger.warning(f"Kunde inte tolka market cap för {ticker}: {cap!r}")
        return None


def get_smallcap_universe(
    min_cap: float = MIN_CAP,
    max_cap: float = MAX_CAP,
    include_delisted: bool = True,
    limit: Optional[int] = None,
    request_delay: float = 1.0,
) -> list:
    """
    Bygger small-cap-universumet: full tickerlista (inkl. avlistade),
    sedan fundamentals per ticker för att filtrera på market cap.

    limit: begränsa antal tickers som granskas (för test/sanity-check -
    en full körning mot hela US-listan är många hundra fundamentals-anrop
    och bör inte köras oplanerat pga rate limits/kostnad).
    """
    all_tickers = get_us_tickers(include_delisted=include_delisted)
    if limit:
        all_tickers = all_tickers[:limit]

    universe = []
    skipped = 0
    for row in all_tickers:
        code = row.get("Code")
        if not code:
            continue
        cap = get_market_cap(code)
        time.sleep(request_delay)
        if cap is None:
            skipped += 1
            continue
        if min_cap <= cap <= max_cap:
            universe.append({**row, "market_cap": cap})

    logger.info(
        f"Small-cap-universum: {len(universe)} bolag i intervallet "
        f"${min_cap:,.0f}-${max_cap:,.0f} (av {len(all_tickers)} granskade, "
        f"{skipped} saknade market cap-data)"
    )
    return universe


def get_daily_ohlcv(ticker: str, start: str, end: str) -> list:
    """
    Hämtar daglig OHLCV-historik för en ticker.

    Returnerar en lista av dict:ar med date/open/high/low/close/
    adjusted_close/volume, plus PLATSHÅLLARFÄLT för friktion
    (borrow_cost, borrow_available, bid_ask_spread) - riktig
    friktionsdata finns inte i v1, men schemat ska finnas från start
    (spec-dokumentet avsnitt 2, princip 3).
    """
    params = {"from": start, "to": end, "period": "d"}
    data = _get(f"eod/{ticker}.US", params)

    if not isinstance(data, list):
        logger.error(f"Oväntat svarsformat från eod/{ticker}.US: {type(data)}")
        raise EODHDError(f"Oväntat svarsformat från eod/{ticker}.US")

    if not data:
        logger.warning(f"Tomt OHLCV-svar för {ticker} ({start} till {end})")
        return []

    # EODHD returnerar ibland en lista med ETT objekt som bara innehåller
    # 'warning' (t.ex. prenumerationsbegränsning), inte riktiga OHLCV-rader.
    # Om vi inte fångar det explicit blir det tyst till en rad med bara
    # None-värden, vilket är exakt den typen av dold datalucka detta
    # system ska förhindra (se ROLE.md, regel 4).
    warning_rows = [r for r in data if "warning" in r and "date" not in r]
    if warning_rows:
        for w in warning_rows:
            logger.warning(f"EODHD-varning för {ticker}: {w['warning']}")
        real_rows = [r for r in data if "date" in r]
        if not real_rows:
            raise EODHDError(
                f"Inga riktiga OHLCV-rader för {ticker} ({start} till {end}) - "
                f"bara varning(ar) från EODHD: {[w['warning'] for w in warning_rows]}"
            )
        data = real_rows

    rows = [
        {
            "date": r.get("date"),
            "open": r.get("open"),
            "high": r.get("high"),
            "low": r.get("low"),
            "close": r.get("close"),
            "adjusted_close": r.get("adjusted_close"),
            "volume": r.get("volume"),
            "borrow_cost": None,
            "borrow_available": None,
            "bid_ask_spread": None,
        }
        for r in data
    ]
    logger.info(f"Hämtade {len(rows)} dagliga rader för {ticker} ({start} till {end})")
    return rows
