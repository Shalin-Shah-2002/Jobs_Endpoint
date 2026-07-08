from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

from app.sources.base import JobCandidate, SourceInfo, SourceSearchResult
from app.schemas.dto import SourceErrorDTO

logger = logging.getLogger(__name__)

_WELLFOUND_BASE = "https://wellfound.com"
_SEARCH_URL = f"{_WELLFOUND_BASE}/jobs"


class WellfoundSource:
    name = "wellfound"
    enabled = True
    info = SourceInfo(
        name="wellfound",
        enabled=True,
        status="ready",
        reason="Scraping Wellfound public job listings via Next.js data.",
    )

    def search(
        self,
        *,
        q: str,
        location: str | None = None,
        remote: bool | None = None,
        limit: int = 25,
    ) -> SourceSearchResult:
        errors: list[SourceErrorDTO] = []
        try:
            return self._search(q=q, location=location, remote=remote, limit=limit)
        except cffi_requests.TimeoutException:
            errors.append(
                SourceErrorDTO(
                    source=self.name,
                    code="wellfound_timeout",
                    message="Wellfound request timed out.",
                    retryable=True,
                )
            )
        except cffi_requests.HTTPStatusError as e:
            errors.append(
                SourceErrorDTO(
                    source=self.name,
                    code="wellfound_http_error",
                    message=f"Wellfound returned HTTP {e.response.status_code}.",
                    retryable=e.response.status_code >= 500,
                )
            )
        except Exception as e:
            logger.exception("Wellfound scrape failed")
            errors.append(
                SourceErrorDTO(
                    source=self.name,
                    code="wellfound_error",
                    message=f"Wellfound scrape error: {e}",
                    retryable=True,
                )
            )
        return SourceSearchResult(errors=errors)

    def _search(
        self,
        *,
        q: str,
        location: str | None,
        remote: bool | None,
        limit: int,
    ) -> SourceSearchResult:
        params = {}
        if q:
            params["q"] = q
        if location:
            params["location"] = location
        if remote:
            params["remote"] = "true"

        resp = cffi_requests.get(
            _SEARCH_URL,
            params=params,
            impersonate="chrome131",
            timeout=20,
        )

        if resp.status_code != 200:
            return SourceSearchResult(
                errors=[
                    SourceErrorDTO(
                        source=self.name,
                        code="wellfound_http_error",
                        message=f"Wellfound returned HTTP {resp.status_code}.",
                        retryable=resp.status_code >= 500,
                    )
                ]
            )

        soup = BeautifulSoup(resp.text, "lxml")
        candidates = self._parse_next_data(soup, limit=limit)
        return SourceSearchResult(jobs=candidates)

    def _parse_next_data(
        self, soup: BeautifulSoup, *, limit: int
    ) -> list[JobCandidate]:
        script = soup.find("script", id="__NEXT_DATA__")
        if not script or not script.string:
            return []

        try:
            data = json.loads(script.string)
        except json.JSONDecodeError:
            return []

        apollo_state = (
            data.get("props", {})
            .get("pageProps", {})
            .get("apolloState", {})
            .get("data", {})
        )
        if not apollo_state:
            return []

        candidates: list[JobCandidate] = []
        for key, entity in apollo_state.items():
            if not isinstance(entity, dict):
                continue
            if entity.get("__typename") != "JobListing":
                continue
            if len(candidates) >= limit:
                break

            candidate = self._parse_job_listing(entity, apollo_state)
            if candidate:
                candidates.append(candidate)

        return candidates

    def _parse_job_listing(
        self, entity: dict, apollo_state: dict
    ) -> JobCandidate | None:
        try:
            slug = entity.get("slug") or ""
            source_job_id = str(entity.get("id", "")) or None

            title = entity.get("title")
            if not title:
                return None

            startup_ref = entity.get("startup", {})
            if isinstance(startup_ref, dict):
                startup_id = startup_ref.get("__ref", "")
                startup = apollo_state.get(startup_id, {})
                company = startup.get("name") or startup.get("company_name") or "Unknown"
            else:
                company = "Unknown"

            location_names = entity.get("locationNames") or []
            location = location_names[0] if location_names else None

            remote_type = "remote" if entity.get("remote") else None

            comp = entity.get("compensation") or ""
            salary = str(comp) if comp else None

            equity = None
            if comp and isinstance(comp, str):
                equity_match = re.search(r"(\d+\.?\d*%)\s*[-–]\s*(\d+\.?\d*%)", comp)
                if equity_match:
                    equity = f"{equity_match.group(1)} - {equity_match.group(2)}"

            live_at = entity.get("liveStartAt")
            posted_at = None
            if live_at:
                try:
                    posted_at = datetime.fromtimestamp(int(live_at), tz=timezone.utc)
                except (ValueError, TypeError):
                    pass

            if source_job_id and slug:
                source_url = f"{_WELLFOUND_BASE}/jobs/{source_job_id}-{slug}"
            elif source_job_id:
                source_url = f"{_WELLFOUND_BASE}/jobs/{source_job_id}"
            elif slug:
                source_url = f"{_WELLFOUND_BASE}/jobs/{slug}"
            else:
                source_url = _WELLFOUND_BASE

            summary = None
            role = entity.get("primaryRole", {})
            if isinstance(role, dict) and role.get("slug"):
                summary = f"Role: {role['slug']}"
            if location_names:
                loc_str = " | ".join(location_names[:3])
                summary = f"{summary} | Location: {loc_str}" if summary else f"Location: {loc_str}"

            return JobCandidate(
                source=self.name,
                source_job_id=source_job_id,
                title=str(title),
                company=str(company),
                location=location,
                remote_type=remote_type,
                salary=salary,
                equity=equity,
                posted_at=posted_at,
                source_url=source_url,
                summary=summary,
            )
        except Exception:
            logger.exception(f"Failed to parse Wellfound job: {entity.get('title', '?')}")
            return None
