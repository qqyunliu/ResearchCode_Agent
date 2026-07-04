from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.schemas.project import ProjectCreate, ProjectRead
from app.schemas.scan import ScanSummary
from app.schemas.stats import ProjectStats
from app.services.index_service import IndexService
from app.services.project_service import ProjectService

router = APIRouter()


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(
    data: ProjectCreate,
    session: Session = Depends(get_session),
) -> ProjectRead:
    project = ProjectService(session).create(data)
    return ProjectRead.model_validate(project)


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
