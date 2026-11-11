from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.core.config import settings
from app.db import _connect_args

BASELINE_REVISION = "20261109_0001"


def _alembic_config() -> Config:
    backend_root = Path(__file__).resolve().parents[1]
    return Config(str(backend_root / "alembic.ini"))


def main() -> None:
    engine = create_engine(settings.database_url, connect_args=_connect_args(settings.database_url, runtime=False))
    try:
        with engine.connect() as connection:
            postgres = connection.dialect.name == "postgresql"
            if postgres:
                connection.execute(text("SELECT pg_advisory_lock(20261111)"))
            try:
                tables = set(inspect(connection).get_table_names())
                config = _alembic_config()
                if "alembic_version" not in tables and "users" in tables:
                    command.stamp(config, BASELINE_REVISION)
                command.upgrade(config, "head")
            finally:
                if postgres:
                    connection.execute(text("SELECT pg_advisory_unlock(20261111)"))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
