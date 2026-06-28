from app.sources.wellfound import WellfoundSource


def test_url_includes_id_prefix_when_both_id_and_slug_present():
    source = WellfoundSource()
    entity = {"id": "4399840", "slug": "mobile-engineer-react-native-expo", "title": "Test"}
    apollo = {}
    result = source._parse_job_listing(entity, apollo)
    assert result is not None
    assert result.source_url == "https://wellfound.com/jobs/4399840-mobile-engineer-react-native-expo"


def test_url_falls_back_to_id_only_when_slug_missing():
    source = WellfoundSource()
    entity = {"id": "4399840", "title": "Test"}
    apollo = {}
    result = source._parse_job_listing(entity, apollo)
    assert result is not None
    assert result.source_url == "https://wellfound.com/jobs/4399840"


def test_url_falls_back_to_slug_only_when_id_missing():
    source = WellfoundSource()
    entity = {"slug": "mobile-engineer-react-native-expo", "title": "Test"}
    apollo = {}
    result = source._parse_job_listing(entity, apollo)
    assert result is not None
    assert result.source_url == "https://wellfound.com/jobs/mobile-engineer-react-native-expo"


def test_url_falls_back_to_base_when_both_missing():
    source = WellfoundSource()
    entity = {"title": "Test"}
    apollo = {}
    result = source._parse_job_listing(entity, apollo)
    assert result is not None
    assert result.source_url == "https://wellfound.com"


def test_url_does_not_add_trailing_dash_when_only_id_present():
    source = WellfoundSource()
    entity = {"id": "4399840", "title": "Test"}
    apollo = {}
    result = source._parse_job_listing(entity, apollo)
    assert result is not None
    assert result.source_url == "https://wellfound.com/jobs/4399840"
    assert not result.source_url.endswith("-")
