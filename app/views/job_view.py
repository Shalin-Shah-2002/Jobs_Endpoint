from app.models.job import Job
from app.schemas.dto import JobDTO, JobListDTO


class JobView:
    @staticmethod
    def to_dto(job: Job) -> JobDTO:
        return JobDTO.model_validate(job)

    @staticmethod
    def to_dto_list(payload: JobListDTO) -> JobListDTO:
        return payload
