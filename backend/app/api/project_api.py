from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.dependencies import get_vector_store
from app.retrieval.vector_store import QdrantVectorStore
from app.models import Project
from app.schemas.project import (
    ProjectCreate,
    ProjectEntityRead,
    ProjectListItem,
    ProjectOrderUpdate,
    ProjectRead,
)
from app.schemas.scan import ScanSummary
from app.schemas.stats import ProjectStats
from app.schemas.frontend_diagnostics import FrontendRequestDiagnostics
from app.services.index_service import IndexService
from app.services.project_service import ProjectService

router = APIRouter()


def _list_item(project: Project) -> ProjectListItem:
    return ProjectListItem(
        id=project.id,
        name=project.name,
        root_path=project.root_path,
        status=project.status,
        created_at=project.created_at,
        last_scan_at=project.last_scan_at,
        sort_order=project.sort_order,
        path_accessible=Path(project.root_path).is_dir(),
    )


@router.get("", response_model=list[ProjectListItem])
def list_projects(
    session: Session = Depends(get_session),
) -> list[ProjectListItem]:
    return [_list_item(item) for item in ProjectService(session).list_projects()]


@router.put("/order", response_model=list[ProjectListItem])
def reorder_projects(
    data: ProjectOrderUpdate,
    session: Session = Depends(get_session),
) -> list[ProjectListItem]:
    projects = ProjectService(session).reorder(data.project_ids)
    return [_list_item(item) for item in projects]


@router.post(
    "",
    response_model=ProjectListItem,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreate,
    session: Session = Depends(get_session),
) -> ProjectListItem:
    project = ProjectService(session).create(data)
    return _list_item(project)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    session: Session = Depends(get_session),
    vector_store: QdrantVectorStore = Depends(get_vector_store),
) -> Response:
    ProjectService(session).delete(project_id, vector_store)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{project_id}/scan", response_model=ScanSummary)
def scan_project(
    project_id: int,
    session: Session = Depends(get_session),
) -> ScanSummary:
    return IndexService(session).scan_project(project_id)


@router.get("/{project_id}/stats", response_model=ProjectStats)
def project_stats(
    project_id: int,
    session: Session = Depends(get_session),
) -> ProjectStats:
    return IndexService(session).get_stats(project_id)


@router.get(
    "/{project_id}/frontend-request-diagnostics",
    response_model=FrontendRequestDiagnostics,
)
def frontend_request_diagnostics(
    project_id: int,
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
) -> FrontendRequestDiagnostics:
    return IndexService(session).get_frontend_request_diagnostics(
        project_id,
        limit=limit,
    )


@router.get(
    "/{project_id}/entities/{entity_id}",
    response_model=ProjectEntityRead,
)
def read_project_entity(
    project_id: int,
    entity_id: int,
    session: Session = Depends(get_session),
) -> ProjectEntityRead:
    entity = ProjectService(session).get_entity(project_id, entity_id)
    return ProjectEntityRead(
        entity_id=entity.id,
        entity_type=entity.entity_type,
        qualified_name=entity.qualified_name,
        file_path=entity.file_path,
        start_line=entity.start_line,
        end_line=entity.end_line,
        content=entity.content,
    )
