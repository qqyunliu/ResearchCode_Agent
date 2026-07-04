import argparse
from pathlib import Path

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models import (
    Base,
    CodeEntity,
    CodeFile,
    CodeRelation,
    Project,
    ScanIssue,
)
from app.schemas.project import ProjectCreate
from app.services.index_service import IndexService
from app.services.project_service import ProjectService
from app.utils.path_utils import normalize_project_root


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Register and index a local research-code project."
    )
    argument_parser.add_argument("project_root", type=Path)
    argument_parser.add_argument("--name", default="Manual Scan Demo")
    args = argument_parser.parse_args()

    root_path = str(normalize_project_root(str(args.project_root)))
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        project = session.scalar(
            select(Project).where(Project.root_path == root_path)
        )
        if project is None:
            project = ProjectService(session).create(
                ProjectCreate(name=args.name, root_path=root_path)
            )
            print(f"Created project: {project.id}")
        else:
            print(f"Using existing project: {project.id}")

        summary = IndexService(session).scan_project(project.id)
        print(summary.model_dump_json(indent=2))
        print(f"Database: {get_settings().database_url}")
        print("Persisted rows:")
        for label, model in (
            ("code_files", CodeFile),
            ("code_entities", CodeEntity),
            ("code_relations", CodeRelation),
            ("scan_issues", ScanIssue),
        ):
            row_count = session.scalar(
                select(func.count()).select_from(model).where(
                    model.project_id == project.id
                )
            )
            print(f"  {label}: {row_count}")


if __name__ == "__main__":
    main()
