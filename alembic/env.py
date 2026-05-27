"""Alembic environment.

Reads DATABASE_URL from Settings, imports SQLModel metadata via
pynote_core.models so autogenerate sees every table.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# Import all model modules so SQLModel.metadata is populated.
import pynote_core.models  # noqa: F401
from alembic import context
from pynote_core.settings import get_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# DSN for Alembic. psycopg3 dialect works in sync mode too.
_settings = get_settings()
_sync_url = _settings.database_url
if _sync_url.startswith("postgresql://"):
    _sync_url = _sync_url.replace("postgresql://", "postgresql+psycopg://", 1)
config.set_main_option("sqlalchemy.url", _sync_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
