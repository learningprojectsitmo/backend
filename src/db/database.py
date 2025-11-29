from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from db.models import Base
from core.config import settings

engine = create_engine(settings.DATABASE_URL, echo=True)
Base.metadata.create_all(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
