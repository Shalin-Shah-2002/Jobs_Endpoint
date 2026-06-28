# Jobs Endpoint

A compliance-first FastAPI service for cached job search results. The app exposes
a normalized job-search API backed by the Wellfound public job index. Results
are stored in a local SQLAlchemy database and exposed via paginated, cursor-based
read endpoints.

## Sources

| Source    | Status        | Notes                                                          |
|-----------|---------------|----------------------------------------------------------------|
| wellfound | Live (public) | Scrapes `wellfound.com/jobs` via `curl_cffi` + `__NEXT_DATA__`. |
| mock      | Dev only      | Disabled by default; opt-in via `JOBS_ENABLE_MOCK_SOURCE=true`. |

## Out of Scope

- **Indeed** — Indeed.com is intentionally **not** part of this project. Their
  site uses DataDome bot protection that hard-blocks data-center and repeat
  scraping IPs. Bypassing their anti-bot controls would violate their Terms of
  Service. If Indeed support is needed in the future, the proper path is the
  [Indeed Publisher API](https://www.indeed.com/publisher), which requires an
  approved partnership.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

The API will be available at:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

## Example Search Run

```bash
curl -X POST http://127.0.0.1:8000/api/v1/search-runs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key" \
  -d '{"q":"python","location":"India","remote":true,"sources":["wellfound"],"limit":10}'
```

Then inspect cached jobs:

```bash
curl "http://127.0.0.1:8000/api/v1/jobs?q=python&limit=10"
```

## Endpoints

- `GET /health`
- `GET /api/v1/sources`
- `GET /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/search-runs`
- `GET /api/v1/search-runs/{run_id}`
- `GET /api/v1/search-runs/{run_id}/jobs`
- `POST /api/v1/alerts`
- `GET /api/v1/alerts`
- `GET /api/v1/alerts/{alert_id}`
- `PATCH /api/v1/alerts/{alert_id}`
- `DELETE /api/v1/alerts/{alert_id}`
- `GET /api/v1/alerts/{alert_id}/executions`
- `POST /api/v1/alerts/{alert_id}/run`
- `POST /api/v1/alerts/{alert_id}/test`

## Configuration

Environment variables use the `JOBS_` prefix:

- `JOBS_API_KEY`: API key for creating search runs and alerts.
- `JOBS_DATABASE_URL`: SQLAlchemy database URL.
- `JOBS_ENABLE_MOCK_SOURCE`: enable the local mock source.
- `JOBS_READ_RATE_LIMIT`: read requests per minute per client.
- `JOBS_WRITE_RATE_LIMIT`: search-run and alert mutation requests per minute per client.
- `JOBS_ALERT_CHECK_INTERVAL_SECONDS`: how often the scheduler checks for due alerts.
- `JOBS_NOTIFICATION_TIMEOUT_SECONDS`: Discord/Slack webhook HTTP timeout.

## Compliance Notes

This service does not bypass authentication, CAPTCHA, anti-bot controls, or
terms restrictions on any job board. The Wellfound adapter only reads public,
unauthenticated search results. The Indeed integration was removed because
DataDome-protected sites require scraping techniques that conflict with the
job site's Terms of Service.
