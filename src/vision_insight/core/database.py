"""Database models and connection using SQLAlchemy + SQLite."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)

# Database path
DB_PATH = Path("data/vision_insight.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
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
            "ocr_results": json.loads(self.ocr_results_json or "[]"),
            "entities": json.loads(self.entities_json or "{}"),
            "conclusions": json.loads(self.conclusions_json or "[]"),
            "report_markdown": self.report_markdown,
        }


# Database engine and session factory
_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(DATABASE_URL, echo=False)
        Base.metadata.create_all(_engine)
        logger.info("Database initialized: %s", DB_PATH)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def save_analysis(record: AnalysisRecord) -> None:
    """Save or update an analysis record."""
    session = get_session()
    try:
        session.merge(record)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_analysis(analysis_id: str) -> AnalysisRecord | None:
    """Get an analysis record by ID."""
    session = get_session()
    try:
        return session.query(AnalysisRecord).filter_by(id=analysis_id).first()
    finally:
        session.close()


def list_analyses(limit: int = 20, offset: int = 0) -> list[AnalysisRecord]:
    """List recent analyses."""
    session = get_session()
    try:
        return (
            session.query(AnalysisRecord)
            .order_by(AnalysisRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
    finally:
        session.close()


def delete_analysis(analysis_id: str) -> bool:
    """Delete an analysis record."""
    session = get_session()
    try:
        record = session.query(AnalysisRecord).filter_by(id=analysis_id).first()
        if record:
            session.delete(record)
            session.commit()
            return True
        return False
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def search_analyses(
    keyword: str = None,
    scene_type: str = None,
    location: str = None,
    limit: int = 20,
    offset: int = 0,
) -> list[AnalysisRecord]:
    """Search analyses by keyword, scene type, or location."""
    session = get_session()
    try:
        query = session.query(AnalysisRecord)

        if keyword:
            query = query.filter(
                AnalysisRecord.report_markdown.ilike(f"%{keyword}%") |
                AnalysisRecord.scene_description.ilike(f"%{keyword}%") |
                AnalysisRecord.image_filename.ilike(f"%{keyword}%")
            )
        if scene_type:
            query = query.filter(AnalysisRecord.scene_type == scene_type)
        if location:
            query = query.filter(AnalysisRecord.location_guess.ilike(f"%{location}%"))

        return query.order_by(AnalysisRecord.created_at.desc()).offset(offset).limit(limit).all()
    finally:
        session.close()
