from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


config = settings()
connect_args = {"check_same_thread": False, "timeout": 30} if config.database_url.startswith("sqlite") else {}
if config.database_url.startswith('postgresql'):
    connect_args.update({'connect_timeout': 5, 'application_name': 'tripparadox_synthetic_lab'})
engine = create_engine(config.database_url, connect_args=connect_args, pool_pre_ping=True, pool_recycle=1800)
if config.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    with SessionLocal() as session:
        yield session
