"""
local_pool_filler.py - Local pool filler for visa-kit project.

Bypasses Railway IP ban by running the full rmsp-pp -> EGRUL -> NPD ->
binary search pipeline from your local machine, then inserting verified
candidates directly into Postgres via DATABASE_URL.

Usage:
    # Pilot run with 3 candidates
    python local_pool_filler.py --target 3 --region 77 --kladr 7700000000000

    # Production run
    python local_pool_filler.py --target 20 --region 77 --kladr 7700000000000

    # Dry run (no DB writes)
    python local_pool_filler.py --target 3 --region 77 --kladr 7700000000000 --dry-run

Estimated time: ~7 minutes per verified candidate (binary search dominated).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Awaitable, Callable, List, Optional, Set

import httpx
import psycopg2
import psycopg2.extras


# =============================================================================
# Logging setup
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("local_pool")


# =============================================================================
# DATABASE_URL - hardcoded for convenience (Railway external proxy URL)
# =============================================================================

DATABASE_URL = (
    "postgresql://postgres:uxGVZsShKKnbOZuHyiFpEaufEAnKjYXI"
    "@switchyard.proxy.rlwy.net:34408/railway"
)


# =============================================================================
# RMSP CLIENT (copied from backend/app/services/inn_generator/rmsp_client.py)
# =============================================================================

RMSP_BASE_URL = "https://rmsp-pp.nalog.ru"
RMSP_SEARCH_HTML = f"{RMSP_BASE_URL}/search.html"
RMSP_SEARCH_PROC = f"{RMSP_BASE_URL}/search-proc.json"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/147.0.0.0 Safari/537.36"
)

RMSP_TIMEOUT = httpx.Timeout(60.0, connect=30.0)
SESSION_INIT_RETRIES = 2
SESSION_INIT_RETRY_DELAY = 8.0


class RmspError(Exception):
    pass


@dataclass
class RmspCandidate:
    inn: str
    full_name: str
    nptype: str
    category: int
    region_code: str
    ogrn: Optional[str] = None
    dt_create: Optional[str] = None
    dt_support_begin: Optional[str] = None
    dt_support_period: Optional[str] = None
    raw: dict = field(default_factory=dict)

    @property
    def is_self_employed(self) -> bool:
        return (
            self.nptype == "SZ"
            and self.category == 4
            and not self.ogrn
        )


class RmspClient:
    def __init__(self, timeout=RMSP_TIMEOUT, user_agent=DEFAULT_USER_AGENT):
        self._timeout = timeout
        self._user_agent = user_agent
        self._client: Optional[httpx.AsyncClient] = None
        self._session_kladr: Optional[str] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _ensure_session_for_kladr(self, kladr_code: str) -> None:
        if self._client is None:
            raise RmspError("RmspClient not initialized")
        if self._session_kladr == kladr_code:
            return

        params = {"sk": "SZ", "kladr": kladr_code}
        last_error = None
        delay = SESSION_INIT_RETRY_DELAY

        for attempt in range(SESSION_INIT_RETRIES + 1):
            log.info(f"[rmsp] GET search.html sk=SZ kladr={kladr_code} "
                     f"(attempt {attempt + 1}/{SESSION_INIT_RETRIES + 1})")
            try:
                response = await self._client.get(RMSP_SEARCH_HTML, params=params)
                response.raise_for_status()
                self._session_kladr = kladr_code
                return
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as e:
                last_error = e
                log.warning(f"[rmsp] session init failed: {type(e).__name__}: {e}")
                if attempt < SESSION_INIT_RETRIES:
                    await asyncio.sleep(delay)
                    delay *= 2
            except httpx.HTTPError as e:
                raise RmspError(f"Failed to init rmsp session: {e}") from e

        raise RmspError(f"Failed to init rmsp session after retries: {last_error}")

    async def search_self_employed(
        self, kladr_code: str, page: int = 1, page_size: int = 100,
        strict_region_filter: bool = True,
    ) -> List[RmspCandidate]:
        if self._client is None:
            raise RmspError("RmspClient not initialized")
        if not kladr_code or len(kladr_code) != 13 or not kladr_code.isdigit():
            raise RmspError(f"kladr_code must be 13 digits, got: {kladr_code!r}")

        await self._ensure_session_for_kladr(kladr_code)

        url_params = {"m": "SupportExt", "sk": "SZ", "kladr": kladr_code}
        form_data = {
            "page": str(page), "pageSize": str(page_size),
            "query": "", "sc": "", "sk": "", "rp": "", "_v": "",
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Origin": RMSP_BASE_URL,
            "Referer": f"{RMSP_SEARCH_HTML}?sk=SZ&kladr={kladr_code}",
            "X-Requested-With": "XMLHttpRequest",
        }

        log.info(f"[rmsp] POST search-proc kladr={kladr_code}, page={page}")
        try:
            response = await self._client.post(
                RMSP_SEARCH_PROC, params=url_params, data=form_data, headers=headers,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            raise RmspError(f"rmsp HTTP error: {e}") from e
        except ValueError as e:
            raise RmspError(f"rmsp returned non-JSON: {e}") from e

        rows = data.get("data", [])
        log.info(f"[rmsp] page {page}: got {len(rows)} rows from server")

        candidates = []
        seen = set()
        expected_region = kladr_code[:2]
        wrong_region = 0
        not_sz = 0

        for row in rows:
            inn = row.get("subject_inn")
            if not inn or inn in seen:
                continue
            cand = RmspCandidate(
                inn=inn,
                full_name=row.get("subject_name", "").strip(),
                nptype=row.get("subject_nptype", ""),
                category=row.get("subject_category", 0),
                region_code=row.get("subject_region", ""),
                ogrn=row.get("subject_ogrn"),
                dt_create=row.get("dt_create"),
                dt_support_begin=row.get("dt_support_begin"),
                dt_support_period=row.get("dt_support_period"),
                raw=row,
            )
            if not cand.is_self_employed:
                not_sz += 1
                continue
            if strict_region_filter and cand.region_code != expected_region:
                wrong_region += 1
                continue
            candidates.append(cand)
            seen.add(inn)

        log.info(f"[rmsp] filtered: {wrong_region} wrong region, {not_sz} not SZ. "
                 f"Got {len(candidates)} candidates from region {expected_region}")
        return candidates

    async def search_multiple_pages(
        self, kladr_code: str, max_candidates: int = 50, page_size: int = 100,
        max_pages: int = 10, delay_between_pages: float = 0.5,
    ) -> List[RmspCandidate]:
        all_candidates = []
        seen = set()
        empty_pages = 0

        for page in range(1, max_pages + 1):
            page_results = await self.search_self_employed(
                kladr_code=kladr_code, page=page, page_size=page_size,
            )
            new_count = 0
            for c in page_results:
                if c.inn not in seen:
                    all_candidates.append(c)
                    seen.add(c.inn)
                    new_count += 1
            log.info(f"[rmsp] page {page}: +{new_count} new "
                     f"(total: {len(all_candidates)}/{max_candidates})")

            if len(all_candidates) >= max_candidates:
                break
            if new_count == 0:
                empty_pages += 1
                if empty_pages >= 3:
                    log.info(f"[rmsp] {empty_pages} empty pages, stopping")
                    break
            else:
                empty_pages = 0
            if page < max_pages:
                await asyncio.sleep(delay_between_pages)

        return all_candidates[:max_candidates]


# =============================================================================
# EGRUL CHECKER (copied from backend/app/services/inn_generator/egrul_check.py)
# =============================================================================

EGRUL_BASE_URL = "https://egrul.nalog.ru"
EGRUL_SEARCH_URL = f"{EGRUL_BASE_URL}/"
EGRUL_RESULT_URL = f"{EGRUL_BASE_URL}/search-result"
EGRUL_TIMEOUT = httpx.Timeout(30.0, connect=15.0)


class EgrulError(Exception):
    pass


class EgrulCaptchaRequired(EgrulError):
    pass


class EgrulChecker:
    def __init__(self, timeout=EGRUL_TIMEOUT, user_agent=DEFAULT_USER_AGENT,
                 throttle_seconds: float = 1.5):
        self._timeout = timeout
        self._user_agent = user_agent
        self._throttle = throttle_seconds
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def is_in_egrul(self, inn: str) -> bool:
        if self._client is None:
            raise EgrulError("EgrulChecker not initialized")
        if not inn or len(inn) not in (10, 12) or not inn.isdigit():
            raise EgrulError(f"INN must be 10 or 12 digits: {inn!r}")

        if self._throttle > 0:
            await asyncio.sleep(self._throttle)

        # Step 1: get token
        payload = {
            "vyp3CaptchaToken": "", "page": "", "query": inn,
            "region": "", "PreventChromeAutocomplete": "",
        }
        try:
            r1 = await self._client.post(EGRUL_SEARCH_URL, data=payload)
        except httpx.HTTPError as e:
            raise EgrulError(f"egrul step1 ({type(e).__name__}): {e}") from e

        if r1.status_code == 400:
            # Pack 28 EGRUL temp-ban after burst: returns 400 for ~30-60 sec.
            # We treat 400 same as captcha — pause and let caller retry next candidate
            raise EgrulCaptchaRequired(f"EGRUL soft-ban (400) for {inn}")

        if r1.status_code != 200:
            raise EgrulError(f"egrul step1 status {r1.status_code}")
        try:
            data1 = r1.json()
        except ValueError as e:
            raise EgrulError(f"egrul step1 non-JSON: {e}") from e

        if data1.get("captchaRequired"):
            raise EgrulCaptchaRequired(f"CAPTCHA required for {inn}")
        token = data1.get("t")
        if not token:
            raise EgrulError(f"egrul step1 no token: {data1!r}")

        # Step 2: result
        try:
            r2 = await self._client.get(f"{EGRUL_RESULT_URL}/{token}")
        except httpx.HTTPError as e:
            raise EgrulError(f"egrul step2 ({type(e).__name__}): {e}") from e

        if r2.status_code != 200:
            raise EgrulError(f"egrul step2 status {r2.status_code}")
        try:
            data2 = r2.json()
        except ValueError as e:
            raise EgrulError(f"egrul step2 non-JSON: {e}") from e

        rows = data2.get("rows", [])
        total_found = 0
        for row in rows:
            try:
                cnt = int(row.get("cnt", "0") or "0")
                tot = int(row.get("tot", "0") or "0")
            except (TypeError, ValueError):
                cnt = tot = 0
            total_found += max(cnt, tot)

        return total_found > 0


# =============================================================================
# NPD STATUS CHECKER (copied from backend/app/services/inn_generator/npd_status.py)
# =============================================================================

NPD_BASE_URL = "https://statusnpd.nalog.ru"
NPD_CHECK_ENDPOINT = f"{NPD_BASE_URL}/api/v1/tracker/taxpayer_status"
NPD_TIMEOUT = httpx.Timeout(70.0, connect=10.0)
MIN_REQUEST_INTERVAL_SECONDS = 31.0


class NpdStatusError(Exception):
    pass


@dataclass
class NpdStatusResult:
    inn: str
    is_active: bool
    request_date: date
    registration_date: Optional[date] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    second_name: Optional[str] = None
    message: Optional[str] = None
    raw: Optional[dict] = None

    @property
    def full_name(self) -> str:
        parts = [
            (self.last_name or "").strip(),
            (self.first_name or "").strip(),
            (self.second_name or "").strip(),
        ]
        return " ".join(p for p in parts if p)


class NpdStatusChecker:
    _last_request_time: float = 0.0
    _rate_limit_lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, timeout=NPD_TIMEOUT, user_agent=DEFAULT_USER_AGENT,
                 respect_rate_limit: bool = True):
        self._timeout = timeout
        self._user_agent = user_agent
        self._respect_rate_limit = respect_rate_limit
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=self._timeout, follow_redirects=True,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _wait_for_rate_limit(self) -> None:
        if not self._respect_rate_limit:
            return
        async with self._rate_limit_lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            elapsed = now - NpdStatusChecker._last_request_time
            wait_seconds = MIN_REQUEST_INTERVAL_SECONDS - elapsed
            if wait_seconds > 0:
                log.info(f"[npd] rate limit: waiting {wait_seconds:.1f}s")
                await asyncio.sleep(wait_seconds)
            NpdStatusChecker._last_request_time = loop.time()

    async def check(self, inn: str, request_date: Optional[date] = None) -> NpdStatusResult:
        if self._client is None:
            raise NpdStatusError("NpdStatusChecker not initialized")
        if not inn or len(inn) != 12 or not inn.isdigit():
            raise NpdStatusError(f"INN must be 12 digits: {inn!r}")
        if request_date is None:
            request_date = date.today()

        await self._wait_for_rate_limit()

        body = {"inn": inn, "requestDate": request_date.isoformat()}
        log.info(f"[npd] check inn={inn}, date={body['requestDate']}")

        try:
            response = await self._client.post(NPD_CHECK_ENDPOINT, json=body)
        except httpx.HTTPError as e:
            err_type = type(e).__name__
            err_msg = str(e) or repr(e)
            raise NpdStatusError(f"npd HTTP error ({err_type}): {err_msg}") from e

        if response.status_code == 422:
            try:
                err_body = response.json()
            except Exception:
                err_body = {"raw_text": response.text}
            raise NpdStatusError(f"FNS 422 for INN {inn}: {err_body}")

        if response.status_code != 200:
            raise NpdStatusError(
                f"npd unexpected status {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
        except ValueError as e:
            raise NpdStatusError(f"npd non-JSON: {e}") from e

        is_active = bool(data.get("status", False))
        reg_date_str = data.get("registrationDate")
        registration_date = None
        if reg_date_str:
            try:
                registration_date = date.fromisoformat(reg_date_str)
            except ValueError:
                log.warning(f"[npd] bad registrationDate: {reg_date_str!r}")

        return NpdStatusResult(
            inn=inn,
            is_active=is_active,
            request_date=request_date,
            registration_date=registration_date,
            first_name=data.get("firstName"),
            last_name=data.get("lastName"),
            second_name=data.get("secondName"),
            message=data.get("message"),
            raw=data,
        )


# =============================================================================
# BINARY SEARCH (copied from backend/app/services/inn_generator/npd_date_finder.py)
# =============================================================================

NPD_LAW_START = date(2019, 1, 1)
ESTIMATED_TOTAL_STEPS = 14

ProgressCallback = Callable[[int, int, date, date, date], Awaitable[None]]


async def binary_search_registration_date(
    checker: NpdStatusChecker, inn: str, *,
    upper_bound: Optional[date] = None,
    lower_bound: Optional[date] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Optional[date]:
    if upper_bound is None:
        upper_bound = date.today()
    if lower_bound is None:
        lower_bound = NPD_LAW_START

    if lower_bound >= upper_bound:
        raise ValueError(f"lower {lower_bound} must be before upper {upper_bound}")

    log.info(f"[binsearch] inn={inn} range=[{lower_bound} ... {upper_bound}]")

    step = 0

    # Sanity 1: upper bound check
    step += 1
    if on_progress:
        await on_progress(step, ESTIMATED_TOTAL_STEPS, lower_bound, upper_bound, upper_bound)
    upper_check = await checker.check(inn, request_date=upper_bound)
    if not upper_check.is_active:
        log.warning(f"[binsearch] inn={inn} not active on {upper_bound} - aborting")
        return None
    log.info(f"[binsearch] inn={inn} active on {upper_bound}, name='{upper_check.full_name}'")

    # Sanity 2: lower bound check
    step += 1
    if on_progress:
        await on_progress(step, ESTIMATED_TOTAL_STEPS, lower_bound, upper_bound, lower_bound)
    try:
        lower_check = await checker.check(inn, request_date=lower_bound)
        if lower_check.is_active:
            log.info(f"[binsearch] inn={inn} already active on {lower_bound}")
            return lower_bound
    except NpdStatusError as e:
        log.warning(f"[binsearch] 422 on lower {lower_bound}: {e}")

    # Binary search
    left = lower_bound
    right = upper_bound

    while (right - left).days > 1:
        step += 1
        mid = left + (right - left) // 2
        if on_progress:
            await on_progress(step, ESTIMATED_TOTAL_STEPS, left, right, mid)

        log.info(f"[binsearch] inn={inn} step={step} [{left}...{right}]={(right-left).days}d, mid={mid}")

        try:
            result = await checker.check(inn, request_date=mid)
        except NpdStatusError as e:
            if "422" in str(e):
                log.info(f"[binsearch] 422 on {mid} -> left := mid")
                left = mid
                continue
            else:
                raise

        if result.is_active:
            right = mid
            log.info(f"[binsearch] active on {mid} -> right := mid")
        else:
            left = mid
            log.info(f"[binsearch] not active on {mid} -> left := mid")

    log.info(f"[binsearch] inn={inn} CONVERGED to {right} after {step} requests")
    return right


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def get_db_conn():
    """Create psycopg2 connection."""
    return psycopg2.connect(DATABASE_URL)


def get_existing_inns(conn) -> Set[str]:
    """Fetch all INNs already in npd_candidate to avoid duplicates."""
    with conn.cursor() as cur:
        cur.execute("SELECT inn FROM npd_candidate")
        return {row[0] for row in cur.fetchall()}


def insert_verified_candidate(
    conn, *,
    inn: str, region_code: str, full_name: str,
    rmsp_pp_support_date: Optional[str], registration_date: Optional[date],
    egrul_found: bool = False, npd_active: bool = True,
    dry_run: bool = False,
) -> bool:
    """
    Insert a verified candidate. Returns True if inserted, False if conflict.
    Uses ON CONFLICT (inn) DO NOTHING for idempotency.
    """
    if dry_run:
        log.info(f"[db] DRY RUN: would insert inn={inn} region={region_code} "
                 f"reg_date={registration_date}")
        return True

    now = datetime.utcnow()
    sql = """
        INSERT INTO npd_candidate (
            inn, region_code, full_name,
            rmsp_pp_support_date,
            status, egrul_found, egrul_checked_at,
            npd_active, npd_checked_at,
            registration_date, fetched_at, verified_at
        ) VALUES (
            %s, %s, %s,
            %s,
            'verified', %s, %s,
            %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (inn) DO NOTHING
        RETURNING inn
    """
    rmsp_date = None
    if rmsp_pp_support_date:
        try:
            rmsp_date = date.fromisoformat(rmsp_pp_support_date)
        except (ValueError, TypeError):
            rmsp_date = None

    with conn.cursor() as cur:
        cur.execute(sql, (
            inn, region_code, full_name,
            rmsp_date,
            egrul_found, now,
            npd_active, now,
            registration_date, now, now,
        ))
        inserted = cur.fetchone() is not None
    conn.commit()
    return inserted


# =============================================================================
# MAIN PIPELINE
# =============================================================================

async def fill_pool(
    target: int, region_code: str, kladr_code: str, dry_run: bool = False,
) -> dict:
    """
    Main pipeline: fetch candidates from rmsp-pp, verify each through
    EGRUL + NPD + binary search, insert verified into npd_candidate.

    Returns stats dict.
    """
    stats = {
        "rmsp_fetched": 0,
        "already_in_db": 0,
        "egrul_rejected": 0,
        "egrul_errors": 0,
        "npd_rejected": 0,
        "npd_errors": 0,
        "binsearch_failed": 0,
        "verified_inserted": 0,
        "elapsed_seconds": 0.0,
    }
    t0 = time.time()

    # 1. Connect to DB and get existing INNs
    log.info(f"[main] connecting to DB...")
    conn = get_db_conn()
    try:
        existing_inns = get_existing_inns(conn)
        log.info(f"[main] existing npd_candidate INNs in DB: {len(existing_inns)}")

        # 2. Fetch candidates from rmsp-pp
        log.info(f"[main] fetching candidates from rmsp-pp for kladr={kladr_code}...")
        async with RmspClient() as rmsp:
            # Fetch generously - we'll filter and stop early.
            # Moscow has 40-75% open IP rate, plus ~10% NPD inactive,
            # so we need ~5-10x the target to find verified candidates.
            fetch_count = max(target * 30, 200)
            rmsp_candidates = await rmsp.search_multiple_pages(
                kladr_code=kladr_code,
                max_candidates=fetch_count,
                page_size=100,
            )
        stats["rmsp_fetched"] = len(rmsp_candidates)
        log.info(f"[main] rmsp returned {len(rmsp_candidates)} candidates")

        # 3. Dedup vs DB
        new_candidates = [c for c in rmsp_candidates if c.inn not in existing_inns]
        stats["already_in_db"] = len(rmsp_candidates) - len(new_candidates)
        log.info(f"[main] after dedup: {len(new_candidates)} new candidates "
                 f"({stats['already_in_db']} already in DB)")

        if not new_candidates:
            log.warning("[main] no new candidates to process - exiting")
            return stats

        # 4. Verify each through EGRUL -> NPD -> binary search
        async with EgrulChecker() as egrul, NpdStatusChecker() as npd:
            for idx, cand in enumerate(new_candidates):
                if stats["verified_inserted"] >= target:
                    log.info(f"[main] reached target {target}, stopping")
                    break

                log.info("=" * 70)
                log.info(f"[main] candidate {idx + 1}/{len(new_candidates)}: "
                         f"inn={cand.inn} name='{cand.full_name}'")
                log.info(f"[main] verified so far: {stats['verified_inserted']}/{target}")

                # 4a. EGRUL
                try:
                    in_egrul = await egrul.is_in_egrul(cand.inn)
                except EgrulCaptchaRequired:
                    log.warning(f"[main] EGRUL soft-ban/captcha for {cand.inn} - sleeping 90s")
                    await asyncio.sleep(90)
                    try:
                        in_egrul = await egrul.is_in_egrul(cand.inn)
                    except (EgrulCaptchaRequired, EgrulError) as e:
                        log.warning(f"[main] EGRUL still blocked: {e} - skipping candidate")
                        stats["egrul_errors"] += 1
                        continue
                except EgrulError as e:
                    log.warning(f"[main] EGRUL error for {cand.inn}: {e}")
                    stats["egrul_errors"] += 1
                    continue

                if in_egrul:
                    log.info(f"[main] {cand.inn} is in EGRUL (open IP) - REJECTED")
                    stats["egrul_rejected"] += 1
                    continue
                log.info(f"[main] {cand.inn} NOT in EGRUL - clean physical person")

                # 4b. Binary search (which itself includes the upper-bound check
                # equivalent to "is currently active")
                try:
                    reg_date = await binary_search_registration_date(npd, cand.inn)
                except NpdStatusError as e:
                    log.warning(f"[main] NPD error for {cand.inn}: {e}")
                    stats["npd_errors"] += 1
                    continue

                if reg_date is None:
                    log.info(f"[main] {cand.inn} not active in NPD - REJECTED")
                    stats["npd_rejected"] += 1
                    continue

                log.info(f"[main] {cand.inn} VERIFIED with reg_date={reg_date}")

                # 4c. Insert into DB
                inserted = insert_verified_candidate(
                    conn,
                    inn=cand.inn,
                    region_code=region_code,
                    full_name=cand.full_name,
                    rmsp_pp_support_date=cand.dt_support_begin,
                    registration_date=reg_date,
                    egrul_found=False,
                    npd_active=True,
                    dry_run=dry_run,
                )
                if inserted:
                    stats["verified_inserted"] += 1
                    log.info(f"[main] INSERTED into npd_candidate "
                             f"({stats['verified_inserted']}/{target})")
                else:
                    log.info(f"[main] {cand.inn} conflict on insert (race?)")

    finally:
        conn.close()

    stats["elapsed_seconds"] = time.time() - t0
    return stats


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Local pool filler for visa-kit npd_candidate table",
    )
    parser.add_argument("--target", type=int, default=3,
                        help="Target number of verified candidates (default: 3)")
    parser.add_argument("--region", type=str, default="77",
                        help="Region code (2 digits, default: 77 = Moscow)")
    parser.add_argument("--kladr", type=str, default="7700000000000",
                        help="13-digit KLADR code (default: 7700000000000 = Moscow)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Skip DB writes - just simulate")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable DEBUG logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate
    if len(args.region) != 2 or not args.region.isdigit():
        print(f"ERROR: --region must be 2 digits, got: {args.region!r}")
        sys.exit(2)
    if len(args.kladr) != 13 or not args.kladr.isdigit():
        print(f"ERROR: --kladr must be 13 digits, got: {args.kladr!r}")
        sys.exit(2)
    if not args.kladr.startswith(args.region):
        print(f"WARNING: --kladr {args.kladr} doesn't start with --region {args.region}")

    log.info("=" * 70)
    log.info(f"LOCAL POOL FILLER - target={args.target}, region={args.region}, "
             f"kladr={args.kladr}, dry_run={args.dry_run}")
    log.info("=" * 70)
    log.info(f"Estimated time: ~7 minutes per verified candidate "
             f"(~{args.target * 7} min total)")
    log.info("Press Ctrl+C to abort - already-inserted INNs stay in DB")
    log.info("")

    try:
        stats = asyncio.run(fill_pool(
            target=args.target,
            region_code=args.region,
            kladr_code=args.kladr,
            dry_run=args.dry_run,
        ))
    except KeyboardInterrupt:
        log.warning("Interrupted by user")
        sys.exit(130)

    log.info("=" * 70)
    log.info("FINAL STATS:")
    for k, v in stats.items():
        log.info(f"  {k}: {v}")
    log.info("=" * 70)
    log.info(f"Verified inserted: {stats['verified_inserted']}/{args.target}")
    log.info(f"Total time: {stats['elapsed_seconds']:.1f} sec "
             f"({stats['elapsed_seconds'] / 60:.1f} min)")


if __name__ == "__main__":
    main()
