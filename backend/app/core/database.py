import os
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://geouser:geopass@localhost:5432/geoduediligence")

# Base model for SQLAlchemy ORM
Base = declarative_base()

class DatabaseManager:
    _instance: Optional["DatabaseManager"] = None
    
    def __init__(self):
        self.is_connected = False
        self.engine = None
        self.SessionLocal = None
        self._init_connection()

    def _init_connection(self):
        try:
            # Short timeout so server starts instantly even without active local Postgres
            self.engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
                connect_args={"connect_timeout": 3} if "postgresql" in DATABASE_URL else {}
            )
            # Test quick connection
            with self.engine.connect() as conn:
                self.is_connected = True
            self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        except Exception:
            # Fallback to standalone mode (in-memory JSON index)
            self.is_connected = False
            self.engine = None
            self.SessionLocal = None

    def get_session(self):
        if self.is_connected and self.SessionLocal:
            db = self.SessionLocal()
            try:
                yield db
            finally:
                db.close()
        else:
            yield None

# Singleton DB Manager
db_manager = DatabaseManager()
