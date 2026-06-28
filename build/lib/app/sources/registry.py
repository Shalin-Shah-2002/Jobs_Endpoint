from app.config import Settings
from app.sources.base import SourceAdapter
from app.sources.disabled import DisabledSource
from app.sources.mock import MockSource


def build_source_registry(settings: Settings) -> dict[str, SourceAdapter]:
    registry: dict[str, SourceAdapter] = {}

    if settings.enable_mock_source:
        registry["mock"] = MockSource()

    registry["indeed"] = DisabledSource(
        name="indeed",
        docs_url="https://docs.indeed.com/",
        reason=(
            "Indeed access is disabled until official partner/API credentials "
            "or written permission are configured. Direct HTML scraping is not enabled."
        ),
    )
    registry["wellfound"] = DisabledSource(
        name="wellfound",
        docs_url="https://wellfound.com/terms",
        reason=(
            "Wellfound access is disabled until permission is confirmed. "
            "This service will not bypass login, CAPTCHA, robots, or terms restrictions."
        ),
    )

    return registry

