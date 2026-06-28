from app.schemas.dto import HealthDTO


class HealthView:
    @staticmethod
    def to_dto(dto: HealthDTO) -> HealthDTO:
        return dto
