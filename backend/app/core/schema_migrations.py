from sqlalchemy import Engine, inspect, text


def upgrade_schema(engine: Engine) -> None:
    inspector = inspect(engine)
    if "projects" not in inspector.get_table_names():
        return
    if "sort_order" in {
        column["name"] for column in inspector.get_columns("projects")
    }:
        return

    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE projects ADD COLUMN "
            "sort_order INTEGER NOT NULL DEFAULT 0"
        ))
        project_ids = connection.execute(text(
            "SELECT id FROM projects ORDER BY created_at DESC, id DESC"
        )).scalars()
        for sort_order, project_id in enumerate(project_ids):
            connection.execute(
                text(
                    "UPDATE projects SET sort_order = :sort_order "
                    "WHERE id = :project_id"
                ),
                {"sort_order": sort_order, "project_id": project_id},
            )
