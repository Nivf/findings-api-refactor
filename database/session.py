import os

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

from database.models import Base

# Connection string belongs in environment/config, not source.
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./coding_exercise.db")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db_session():
    return SessionLocal()


def close_db_session():
    SessionLocal.remove()
