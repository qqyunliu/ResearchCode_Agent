from sqlalchemy import create_engine, text

from app.core.schema_migrations import upgrade_schema


def test_upgrade_schema_adds_and_backfills_project_order(tmp_path) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE projects ("
            "id INTEGER PRIMARY KEY, name VARCHAR NOT NULL, "
            "root_path VARCHAR NOT NULL, status VARCHAR NOT NULL, "
            "last_scan_at DATETIME, created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO projects VALUES "
            "(1, 'Older', '/old', 'created', NULL, "
            "'2026-01-01', '2026-01-01'), "
            "(2, 'Newer', '/new', 'created', NULL, "
            "'2026-02-01', '2026-02-01')"
        ))

    upgrade_schema(engine)
    upgrade_schema(engine)

    with engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT id, name, sort_order FROM projects ORDER BY sort_order"
        )).all()
    assert rows == [(2, "Newer", 0), (1, "Older", 1)]
