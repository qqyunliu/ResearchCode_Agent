import json
from collections.abc import Iterable
from typing import Protocol

from app.retrieval.types import CodeChunk


class ChunkableEntity(Protocol):
    id: int
    entity_key: str
    entity_type: str
    name: str
    qualified_name: str
    file_path: str
    start_line: int
    end_line: int
    content: str
    metadata_json: str


class CodeChunkBuilder:
    def __init__(self, max_content_chars: int = 4000) -> None:
        if max_content_chars < 1:
            raise ValueError(
                "max_content_chars must be greater than zero"
            )
        self.max_content_chars = max_content_chars

    def build(self, entity: ChunkableEntity) -> CodeChunk:
        metadata = json.loads(entity.metadata_json)
        if not isinstance(metadata, dict):
            raise ValueError("entity metadata_json must contain an object")
        content = entity.content[: self.max_content_chars]
        metadata_text = json.dumps(
            metadata,
            ensure_ascii=False,
            sort_keys=True,
        )
        searchable_text = "\n".join(
            [
                f"Type: {entity.entity_type}",
                f"Name: {entity.name}",
                f"Qualified name: {entity.qualified_name}",
                f"File: {entity.file_path}",
                f"Metadata: {metadata_text}",
                "Code:",
                content,
            ]
        )
        return CodeChunk(
            chunk_id=f"entity:{entity.id}",
            entity_id=entity.id,
            entity_key=entity.entity_key,
            entity_type=entity.entity_type,
            name=entity.name,
            qualified_name=entity.qualified_name,
            file_path=entity.file_path,
            start_line=entity.start_line,
            end_line=entity.end_line,
            content=content,
            metadata=metadata,
            searchable_text=searchable_text,
        )

    def build_many(
        self,
        entities: Iterable[ChunkableEntity],
    ) -> list[CodeChunk]:
        return [self.build(entity) for entity in entities]
