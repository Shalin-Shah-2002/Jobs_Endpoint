from app.schemas.dto import SourceDTO


class SourceView:
    @staticmethod
    def to_dtos(items: list[SourceDTO]) -> list[SourceDTO]:
        return items
