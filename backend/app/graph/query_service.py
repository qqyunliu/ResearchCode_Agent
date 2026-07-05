import json
from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.graph.types import GraphEdge, GraphNode, GraphResult
from app.models import CodeEntity, CodeRelation
from app.utils.api_normalizer import normalize_api_path

CHAIN_RELATION_TYPES = (
    "REQUESTS_API",
    "DEFINES_API",
    "CALLS_METHOD",
)


class GraphQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def traverse(
        self,
        project_id: int,
        entity_id: int,
        *,
        max_depth: int = 1,
        relation_types: tuple[str, ...] | None = None,
    ) -> GraphResult:
        if max_depth < 0 or max_depth > 2:
            raise ValueError("max_depth must be between 0 and 2")
        seed = self.session.scalar(
            select(CodeEntity).where(
                CodeEntity.id == entity_id,
                CodeEntity.project_id == project_id,
            )
        )
        if seed is None:
            raise DomainError(
                code="ENTITY_NOT_FOUND",
                message=(
                    f"Entity {entity_id} does not exist in "
                    f"project {project_id}."
                ),
                status_code=404,
            )

        entities = {seed.id: seed}
        depths = {seed.id: 0}
        edge_rows: dict[int, CodeRelation] = {}
        frontier = {seed.id}
        for depth in range(1, max_depth + 1):
            relations = self._adjacent_relations(
                project_id,
                frontier,
                relation_types,
            )
            neighbor_ids = {
                endpoint
                for relation in relations
                for endpoint in (relation.source_id, relation.target_id)
                if endpoint not in entities
            }
            neighbors = self.session.scalars(
                select(CodeEntity).where(
                    CodeEntity.project_id == project_id,
                    CodeEntity.id.in_(neighbor_ids),
                )
            ).all() if neighbor_ids else []
            neighbor_by_id = {entity.id: entity for entity in neighbors}

            valid_ids = set(entities) | set(neighbor_by_id)
            for relation in relations:
                if (
                    relation.source_id in valid_ids
                    and relation.target_id in valid_ids
                ):
                    edge_rows[relation.id] = relation
            for neighbor in neighbors:
                entities[neighbor.id] = neighbor
                depths[neighbor.id] = depth
            frontier = set(neighbor_by_id)
            if not frontier:
                break

        ordered_entities = sorted(
            entities.values(),
            key=lambda entity: (depths[entity.id], entity.id),
        )
        ordered_relations = sorted(
            edge_rows.values(),
            key=lambda relation: (
                relation.source_id,
                relation.target_id,
                relation.relation_type,
                relation.id,
            ),
        )
        return GraphResult(
            nodes=tuple(self._node(entity) for entity in ordered_entities),
            edges=tuple(self._edge(relation) for relation in ordered_relations),
        )

    def find_api_chain(
        self,
        project_id: int,
        method: str,
        api_path: str,
    ) -> GraphResult:
        normalized_method = method.strip().upper()
        normalized_path = normalize_api_path(api_path)
        api_rows = self.session.scalars(
            select(CodeEntity)
            .where(
                CodeEntity.project_id == project_id,
                CodeEntity.entity_type == "backend_api",
            )
            .order_by(CodeEntity.id)
        ).all()
        matches = [
            entity
            for entity in api_rows
            if self._api_key(entity)
            == (normalized_method, normalized_path)
        ]
        if not matches:
            raise DomainError(
                code="API_NOT_FOUND",
                message=(
                    f"{normalized_method} {api_path} was not found "
                    f"in project {project_id}."
                ),
                status_code=404,
            )
        return self._merge(
            self.traverse(
                project_id,
                entity.id,
                max_depth=2,
                relation_types=CHAIN_RELATION_TYPES,
            )
            for entity in matches
        )

    def expand_entities(
        self,
        project_id: int,
        entity_ids: Iterable[int],
        *,
        max_depth: int,
    ) -> GraphResult:
        return self._merge(
            self.traverse(
                project_id,
                entity_id,
                max_depth=max_depth,
                relation_types=CHAIN_RELATION_TYPES,
            )
            for entity_id in dict.fromkeys(entity_ids)
        )

    def _adjacent_relations(
        self,
        project_id: int,
        frontier: set[int],
        relation_types: tuple[str, ...] | None,
    ) -> list[CodeRelation]:
        statement = select(CodeRelation).where(
            CodeRelation.project_id == project_id,
            or_(
                CodeRelation.source_id.in_(frontier),
                CodeRelation.target_id.in_(frontier),
            ),
        )
        if relation_types is not None:
            statement = statement.where(
                CodeRelation.relation_type.in_(relation_types)
            )
        return list(self.session.scalars(statement).all())

    @classmethod
    def _node(cls, entity: CodeEntity) -> GraphNode:
        return GraphNode(
            entity_id=entity.id,
            label=entity.qualified_name,
            entity_type=entity.entity_type,
            qualified_name=entity.qualified_name,
            file_path=entity.file_path,
            start_line=entity.start_line,
            end_line=entity.end_line,
            content=entity.content,
            metadata=cls._metadata(entity.metadata_json),
        )

    @classmethod
    def _edge(cls, relation: CodeRelation) -> GraphEdge:
        return GraphEdge(
            relation_id=relation.id,
            source_id=relation.source_id,
            target_id=relation.target_id,
            relation_type=relation.relation_type,
            confidence=relation.confidence,
            metadata=cls._metadata(relation.metadata_json),
        )

    @staticmethod
    def _metadata(raw: str) -> dict[str, object]:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}

    @classmethod
    def _api_key(cls, entity: CodeEntity) -> tuple[str, str] | None:
        metadata = cls._metadata(entity.metadata_json)
        method = metadata.get("http_method")
        path = metadata.get("normalized_path")
        if not isinstance(method, str) or not isinstance(path, str):
            return None
        return method.upper(), path

    @staticmethod
    def _merge(results: Iterable[GraphResult]) -> GraphResult:
        nodes: dict[int, GraphNode] = {}
        edges: dict[int, GraphEdge] = {}
        for result in results:
            for node in result.nodes:
                nodes.setdefault(node.entity_id, node)
            edges.update((edge.relation_id, edge) for edge in result.edges)
        return GraphResult(
            nodes=tuple(nodes.values()),
            edges=tuple(
                sorted(
                    edges.values(),
                    key=lambda edge: (
                        edge.source_id,
                        edge.target_id,
                        edge.relation_type,
                        edge.relation_id,
                    ),
                )
            ),
        )
