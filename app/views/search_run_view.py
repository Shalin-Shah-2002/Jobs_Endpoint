import json

from app.models.search_run import SearchRun
from app.schemas.dto import SearchRunOutput, SourceErrorDTO


class SearchRunView:
    @staticmethod
    def to_dto(run: SearchRun) -> SearchRunOutput:
        return SearchRunOutput(
            id=run.id,
            q=run.q,
            location=run.location,
            remote=run.remote,
            sources=json.loads(run.sources_json),
            limit=run.limit,
            status=run.status,
            requested_at=run.requested_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
            total_jobs=run.total_jobs,
            error_count=run.error_count,
            errors=[SourceErrorDTO(**e) for e in json.loads(run.errors_json)],
        )
