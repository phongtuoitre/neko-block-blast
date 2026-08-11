from sqlalchemy import inspect, text

from server.database import engine


TABLE_NAME = "match_players"
COLUMN_NAME = "no_moves"


def table_exists(connection) -> bool:
    return TABLE_NAME in inspect(connection).get_table_names()


def column_exists(connection) -> bool:
    columns = inspect(connection).get_columns(TABLE_NAME)
    return any(column["name"] == COLUMN_NAME for column in columns)


def run_migration(db_engine=None) -> bool:
    db_engine = db_engine or engine
    with db_engine.begin() as connection:
        if not table_exists(connection):
            raise RuntimeError(f"Table {TABLE_NAME} does not exist")
        if column_exists(connection):
            return False

        dialect = connection.dialect.name
        if dialect == "sqlite":
            statement = text(
                f"ALTER TABLE {TABLE_NAME} "
                f"ADD COLUMN {COLUMN_NAME} BOOLEAN NOT NULL DEFAULT 0"
            )
        elif dialect == "postgresql":
            statement = text(
                f"ALTER TABLE {TABLE_NAME} "
                f"ADD COLUMN IF NOT EXISTS {COLUMN_NAME} "
                "BOOLEAN NOT NULL DEFAULT FALSE"
            )
        else:
            statement = text(
                f"ALTER TABLE {TABLE_NAME} "
                f"ADD COLUMN {COLUMN_NAME} BOOLEAN NOT NULL DEFAULT FALSE"
            )
        connection.execute(statement)
        return True


if __name__ == "__main__":
    changed = run_migration()
    if changed:
        print(f"Added {TABLE_NAME}.{COLUMN_NAME}")
    else:
        print(f"{TABLE_NAME}.{COLUMN_NAME} already exists")
