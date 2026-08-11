import os
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


test_db_dir = Path(tempfile.mkdtemp(prefix="neko-migration-test-"))
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{test_db_dir / 'test.db'}")

from server.migrations.add_match_player_no_moves import run_migration  # noqa: E402


def test_add_match_player_no_moves_migration_preserves_existing_rows():
    database_url = f"sqlite:///{test_db_dir / 'legacy.db'}"
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE match_players (
                    id INTEGER PRIMARY KEY,
                    match_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    team INTEGER NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    result VARCHAR(5),
                    UNIQUE (match_id, user_id)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO match_players
                    (id, match_id, user_id, team, score, result)
                VALUES
                    (1, 10, 20, 1, 500, 'win')
                """
            )
        )

    assert run_migration(engine) is True
    assert run_migration(engine) is False

    columns = {
        column["name"]: column for column in inspect(engine).get_columns("match_players")
    }
    assert "no_moves" in columns

    with engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT id, match_id, user_id, team, score, result, no_moves
                FROM match_players
                """
            )
        ).mappings().one()

    assert row["id"] == 1
    assert row["match_id"] == 10
    assert row["user_id"] == 20
    assert row["team"] == 1
    assert row["score"] == 500
    assert row["result"] == "win"
    assert row["no_moves"] in (False, 0)
