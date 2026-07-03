from sqlalchemy import create_engine, inspect

from app.models.base import Base


def test_metadata_contains_all_week1_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "projects",
        "code_files",
        "code_entities",
        "code_relations",
        "scan_issues",
    }
