from app.sources.mock import MockSource, _default_sample_jobs
from app.sources.wellfound import WellfoundSource


def make_test_registry(settings):
    reg: dict = {}
    reg["mock"] = MockSource(jobs=_default_sample_jobs())
    reg["wellfound"] = WellfoundSource()
    return reg
