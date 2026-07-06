from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import CodeEntity, Project
from app.retrieval.vector_store import QdrantVectorStore
from app.schemas.project import ProjectCreate
from app.utils.path_utils import normalize_project_root


class ProjectService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, data: ProjectCreate) -> Project:
        root_path = str(normalize_project_root(data.root_path))
        existing_project = self.session.scalar(
            select(Project).where(Project.root_path == root_path)
        )
        if existing_project is not None:
            raise self._duplicate_root_error(root_path)

        self.session.execute(
            update(Project).values(sort_order=Project.sort_order + 1)
        )
        project = Project(
            name=data.name,
            root_path=root_path,
            status="created",
            sort_order=0,
        )
        self.session.add(project)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise self._duplicate_root_error(root_path) from None

        self.session.refresh(project)
        return project

    def list_projects(self) -> list[Project]:
        return list(self.session.scalars(
            select(Project).order_by(Project.sort_order, Project.id)
        ))

    def reorder(self, project_ids: list[int]) -> list[Project]:
        projects = list(self.session.scalars(select(Project)))
        database_ids = {project.id for project in projects}
        if (
            len(project_ids) != len(set(project_ids))
            or set(project_ids) != database_ids
        ):
            raise DomainError(
                code="PROJECT_ORDER_CONFLICT",
                message="Project order no longer matches the registered projects.",
                status_code=409,
            )
        projects_by_id = {project.id: project for project in projects}
        for position, project_id in enumerate(project_ids):
            projects_by_id[project_id].sort_order = position
        self.session.commit()
        return [projects_by_id[project_id] for project_id in project_ids]

    def delete(
        self,
        project_id: int,
        vector_store: QdrantVectorStore,
    ) -> None:
        project = self.session.get(Project, project_id)
        if project is None:
            raise DomainError(
                code="PROJECT_NOT_FOUND",
                message=f"Project {project_id} does not exist.",
                status_code=404,
            )
        try:
            vector_store.delete_project_collection(project_id)
        except Exception:
            raise DomainError(
                code="VECTOR_STORE_DELETE_FAILED",
                message="Unable to delete the project's vector index.",
                status_code=502,
            ) from None
        self.session.delete(project)
        self.session.commit()

    def get_entity(
        self,
        project_id: int,
        entity_id: int,
    ) -> CodeEntity:
        entity = self.session.scalar(
            select(CodeEntity).where(
                CodeEntity.id == entity_id,
                CodeEntity.project_id == project_id,
            )
        )
        if entity is None:
            raise DomainError(
                code="ENTITY_NOT_FOUND",
                message=(
                    f"Entity {entity_id} does not exist in "
                    f"project {project_id}."
                ),
                status_code=404,
            )
        return entity

    @staticmethod
    def _duplicate_root_error(root_path: str) -> DomainError:
        return DomainError(
            code="PROJECT_ROOT_EXISTS",
            message=f"A project already uses this root path: {root_path}",
            status_code=409,
        )
