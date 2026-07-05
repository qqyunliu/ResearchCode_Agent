from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.errors import DomainError
from app.models import CodeEntity, Project
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

        project = Project(
            name=data.name,
            root_path=root_path,
            status="created",
        )
        self.session.add(project)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            raise self._duplicate_root_error(root_path) from None

        self.session.refresh(project)
        return project

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
