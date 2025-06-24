from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context
import os
import sys

# 🔧 Projektstruktur einbinden
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 🛠️ App-Einstellungen und DB-Basis importieren
from app.config.settings import settings
from app.database import Base

# Lade die Modelle, damit Alembic sie erkennt
import app.models.chat_message
# Entferne den fehlerhaften Import:
# from app.models.postgres_logger import PostgresLog

# Alembic-Konfiguration laden
config = context.config
fileConfig(config.config_file_name)

# Setze die synchronisierte DB-URL, indem "+asyncpg" entfernt wird
sync_db_url = settings.database_url.replace("+asyncpg", "")
config.set_main_option("sqlalchemy.url", sync_db_url)

# Ziel-Metadata für Autogenerate
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    context.configure(
        url=sync_db_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    connectable = create_engine(sync_db_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
