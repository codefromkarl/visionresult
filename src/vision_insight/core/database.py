"""Database models and connection using SQLAlchemy + SQLite."""

import json
import logging
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

logger = logging.getLogger(__name__)

# Database path — SQLite is the only supported backend.
# PostgreSQL was considered but adds operational complexity for a single-node
# analysis agent.  If multi-node is needed in the future, add a second engine
# factory rather than branching inside get_engine().
DB_PATH = Path("data/vision_insight.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    """Persistent storage for analysis reports."""

    __tablename__ = "analyses"

    id = Column(String(16), primary_key=True)
    status = Column(String(16), nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.now)
    completed_at = Column(DateTime, nullable=True)
    processing_time_ms = Column(Integer, default=0)

    # Image info
    image_filename = Column(String(256), nullable=True)
    image_width = Column(Integer, nullable=True)
    image_height = Column(Integer, nullable=True)
    image_format = Column(String(16), nullable=True)
    image_file_size = Column(Integer, nullable=True)

    # Analysis results (JSON)
    scene_type = Column(String(32), nullable=True)
    scene_description = Column(Text, nullable=True)
    location_guess = Column(String(256), nullable=True)
    location_confidence = Column(Float, nullable=True)
    time_guess = Column(String(128), nullable=True)

    # Full data (JSON blobs)
    ocr_results_json = Column(Text, default="[]")
    entities_json = Column(Text, default="{}")
    conclusions_json = Column(Text, default="[]")
    search_results_json = Column(Text, default="[]")

    # Report
    report_markdown = Column(Text, default="")

    # Pipeline trace (JSON)
    pipeline_trace_json = Column(Text, nullable=True)

    def to_dict(self) -> dict:
        """Convert to API-compatible dict."""
        return {
            "id": self.id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "processing_time_ms": self.processing_time_ms,
            "image": {
                "filename": self.image_filename,
                "width": self.image_width,
                "height": self.image_height,
                "format": self.image_format,
                "file_size": self.image_file_size,
            },
            "scene": {
                "type": self.scene_type,
                "description": self.scene_description,
            },
            "location": {
                "guess": self.location_guess,
                "confidence": self.location_confidence,
            },
            "time_guess": self.time_guess,
            "ocr_results": json.loads(str(self.ocr_results_json or "[]")),
            "entities": json.loads(str(self.entities_json or "{}")),
            "conclusions": json.loads(str(self.conclusions_json or "[]")),
            "report_markdown": self.report_markdown,
        }


# Database engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        # SQLite uses StaticPool to allow concurrent reads from the same
        # connection; check_same_thread=False is required for FastAPI's
        # async context which may call the engine from different threads.
        _engine = create_engine(
            DATABASE_URL,
            echo=False,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(_engine)
        logger.info("Database initialized: %s", DB_PATH)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
        )
    return _SessionLocal()


@contextmanager
def get_session_ctx() -> Generator[Session, None, None]:
    """Context manager for database sessions.

    Automatically handles session lifecycle:
    - Yields a session
    - Rolls back on exception
    - Always closes the session
    - Does NOT auto-commit (callers must commit explicitly when needed)

    Usage:
        with get_session_ctx() as session:
            session.merge(record)
            session.commit()
    """
    session = get_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def save_analysis(record: AnalysisRecord) -> None:
    """Save or update an analysis record."""
    with get_session_ctx() as session:
        session.merge(record)
        session.commit()


def get_analysis(analysis_id: str) -> AnalysisRecord | None:
    """Get an analysis record by ID."""
    with get_session_ctx() as session:
        return session.query(AnalysisRecord).filter_by(id=analysis_id).first()


def list_analyses(limit: int = 20, offset: int = 0) -> list[AnalysisRecord]:
    """List recent analyses."""
    with get_session_ctx() as session:
        return (
            session.query(AnalysisRecord)
            .order_by(AnalysisRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )


def delete_analysis(analysis_id: str) -> bool:
    """Delete an analysis record."""
    with get_session_ctx() as session:
        record = session.query(AnalysisRecord).filter_by(id=analysis_id).first()
        if record:
            session.delete(record)
            session.commit()
            return True
        return False


def _sanitize_like_pattern(value: str) -> str:
    """Escape special characters for SQL LIKE pattern.

    Escapes backslash, percent, and underscore so they are treated as
    literal characters rather than wildcards.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_analyses(
    keyword: str | None = None,
    scene_type: str | None = None,
    location: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[AnalysisRecord]:
    """Search analyses by keyword, scene type, or location.

    Uses parameterized queries to prevent SQL injection.
    """
    with get_session_ctx() as session:
        query = session.query(AnalysisRecord)

        if keyword:
            search_pattern = f"%{_sanitize_like_pattern(keyword)}%"
            query = query.filter(
                AnalysisRecord.report_markdown.ilike(search_pattern)
                | AnalysisRecord.scene_description.ilike(search_pattern)
                | AnalysisRecord.image_filename.ilike(search_pattern)
            )
        if scene_type:
            # Validate scene_type against allowed values
            allowed_scene_types = {
                "indoor",
                "outdoor",
                "street",
                "restaurant",
                "office",
                "home",
                "transport",
                "event",
                "nature",
                "unknown",
            }
            if scene_type not in allowed_scene_types:
                logger.warning("Invalid scene_type filter: %s", scene_type)
                return []
            query = query.filter(AnalysisRecord.scene_type == scene_type)
        if location:
            location_pattern = f"%{_sanitize_like_pattern(location)}%"
            query = query.filter(AnalysisRecord.location_guess.ilike(location_pattern))

        return query.order_by(AnalysisRecord.created_at.desc()).offset(offset).limit(limit).all()


def cleanup_old_analyses(days: int = 30) -> int:
    """Delete analyses older than specified days.

    Args:
        days: Number of days to keep records. Older records will be deleted.

    Returns:
        Number of deleted records.
    """
    from datetime import timedelta

    with get_session_ctx() as session:
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted = session.query(AnalysisRecord).filter(
            AnalysisRecord.created_at < cutoff_date
        ).delete()
        session.commit()
        if deleted > 0:
            logger.info("Cleaned up %d old analysis records", deleted)
        return deleted


def get_database_stats() -> dict:
    """Get database statistics.

    Returns:
        Dictionary with database statistics.
    """
    with get_session_ctx() as session:
        total = session.query(AnalysisRecord).count()
        completed = session.query(AnalysisRecord).filter_by(status="completed").count()
        failed = session.query(AnalysisRecord).filter_by(status="failed").count()
        pending = session.query(AnalysisRecord).filter(
            AnalysisRecord.status.in_(["pending", "processing"])
        ).count()

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
        }
