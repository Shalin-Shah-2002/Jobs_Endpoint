from app.core.config import Settings
from app.sources.base import SourceAdapter
from app.sources.mock import MockSource
from app.sources.wellfound import WellfoundSource


def build_source_registry(settings: Settings) -> dict[str, SourceAdapter]:
    registry: dict[str, SourceAdapter] = {}

    if settings.enable_mock_source:
        registry["mock"] = MockSource()

    registry["wellfound"] = WellfoundSource()

    return registry
