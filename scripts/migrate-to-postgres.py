#!/usr/bin/env python3
"""Database migration script: SQLite to PostgreSQL.

Usage:
    python scripts/migrate-to-postgres.py --sqlite-path data/vision_insight.db --pg-url postgresql+asyncpg://user:pass@localhost:5432/vision_insight
"""

import argparse
import asyncio
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Migrate data from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default="data/vision_insight.db",
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--pg-url",
        type=str,
        required=True,
        help="PostgreSQL connection URL (postgresql+asyncpg://user:pass@host:port/db)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of records to insert per batch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be migrated without actually doing it",
    )
    return parser.parse_args()


def get_sqlite_records(db_path: str) -> list[dict]:
    """Read all records from SQLite database."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    
    cursor = conn.execute("""
        SELECT id, status, created_at, processing_time_ms,
               image_width, image_height, image_format, image_file_size,
               scene_type, scene_description, location_guess, location_confidence,
               ocr_results_json, entities_json, conclusions_json,
               search_results_json, report_markdown, image_path,
               pipeline_trace_json
        FROM analysis_records
        ORDER BY created_at
    """)
    
    records = []
    for row in cursor.fetchall():
        record = dict(row)
        # Convert string datetime to Python datetime
        if record["created_at"] and isinstance(record["created_at"], str):
            record["created_at"] = datetime.fromisoformat(record["created_at"])
        records.append(record)
    
    conn.close()
    return records


async def create_pg_tables(engine: sa.engine.Engine) -> None:
    """Create tables in PostgreSQL if they don't exist."""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS analysis_records (
        id VARCHAR(50) PRIMARY KEY,
        status VARCHAR(20) NOT NULL DEFAULT 'pending',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        processing_time_ms INTEGER,
        image_width INTEGER,
        image_height INTEGER,
        image_format VARCHAR(20),
        image_file_size INTEGER,
        scene_type VARCHAR(50),
        scene_description TEXT,
        location_guess VARCHAR(500),
        location_confidence FLOAT,
        ocr_results_json TEXT DEFAULT '[]',
        entities_json TEXT DEFAULT '{}',
        conclusions_json TEXT DEFAULT '[]',
        search_results_json TEXT DEFAULT '[]',
        report_markdown TEXT,
        image_path VARCHAR(500),
        pipeline_trace_json TEXT
    );
    
    CREATE INDEX IF NOT EXISTS idx_analysis_records_created_at ON analysis_records(created_at);
    CREATE INDEX IF NOT EXISTS idx_analysis_records_status ON analysis_records(status);
    CREATE INDEX IF NOT EXISTS idx_analysis_records_scene_type ON analysis_records(scene_type);
    """
    
    async with engine.begin() as conn:
        await conn.execute(sa.text(create_table_sql))


async def insert_pg_records(
    engine: sa.engine.Engine, records: list[dict], batch_size: int
) -> int:
    """Insert records into PostgreSQL in batches."""
    insert_sql = """
    INSERT INTO analysis_records (
        id, status, created_at, processing_time_ms,
        image_width, image_height, image_format, image_file_size,
        scene_type, scene_description, location_guess, location_confidence,
        ocr_results_json, entities_json, conclusions_json,
        search_results_json, report_markdown, image_path,
        pipeline_trace_json
    ) VALUES (
        :id, :status, :created_at, :processing_time_ms,
        :image_width, :image_height, :image_format, :image_file_size,
        :scene_type, :scene_description, :location_guess, :location_confidence,
        :ocr_results_json, :entities_json, :conclusions_json,
        :search_results_json, :report_markdown, :image_path,
        :pipeline_trace_json
    )
    ON CONFLICT (id) DO UPDATE SET
        status = EXCLUDED.status,
        processing_time_ms = EXCLUDED.processing_time_ms,
        scene_type = EXCLUDED.scene_type,
        scene_description = EXCLUDED.scene_description,
        location_guess = EXCLUDED.location_guess,
        location_confidence = EXCLUDED.location_confidence,
        ocr_results_json = EXCLUDED.ocr_results_json,
        entities_json = EXCLUDED.entities_json,
        conclusions_json = EXCLUDED.conclusions_json,
        search_results_json = EXCLUDED.search_results_json,
        report_markdown = EXCLUDED.report_markdown,
        pipeline_trace_json = EXCLUDED.pipeline_trace_json
    """
    
    inserted = 0
    async with engine.begin() as conn:
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            for record in batch:
                # Set default values for None
                record.setdefault("ocr_results_json", "[]")
                record.setdefault("entities_json", "{}")
                record.setdefault("conclusions_json", "[]")
                record.setdefault("search_results_json", "[]")
                
                await conn.execute(sa.text(insert_sql), record))
            inserted += len(batch)
            print(f"  Inserted {inserted}/{len(records)} records...")
    
    return inserted


async def main() -> None:
    """Main migration function."""
    args = parse_args()
    
    # Check SQLite database exists
    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        print(f"❌ SQLite database not found: {sqlite_path}")
        sys.exit(1)
    
    print(f"📦 Reading records from SQLite: {sqlite_path}")
    records = get_sqlite_records(str(sqlite_path))
    print(f"   Found {len(records)} records")
    
    if not records:
        print("✅ No records to migrate")
        return
    
    if args.dry_run:
        print("\n🔍 Dry run - would migrate:")
        for i, record in enumerate(records[:5]):
            print(f"   {i+1}. {record['id']} - {record['status']} - {record['created_at']}")
        if len(records) > 5:
            print(f"   ... and {len(records) - 5} more records")
        return
    
    print(f"\n🔌 Connecting to PostgreSQL: {args.pg_url.split('@')[1]}")
    engine = create_async_engine(args.pg_url, echo=False)
    
    try:
        # Test connection
        async with engine.connect() as conn:
            await conn.execute(sa.text("SELECT 1"))
        print("   ✅ Connection successful")
        
        # Create tables
        print("\n📋 Creating tables...")
        await create_pg_tables(engine)
        print("   ✅ Tables ready")
        
        # Insert records
        print(f"\n📥 Inserting {len(records)} records...")
        inserted = await insert_pg_records(engine, records, args.batch_size)
        print(f"   ✅ Successfully inserted {inserted} records")
        
        # Verify
        async with engine.connect() as conn:
            result = await conn.execute(sa.text("SELECT COUNT(*) FROM analysis_records"))
            count = result.scalar()
            print(f"\n📊 Verification: {count} records in PostgreSQL")
        
        print("\n✅ Migration completed successfully!")
        print("\nNext steps:")
        print("1. Update VIA_DATABASE_URL in .env to point to PostgreSQL")
        print("2. Restart the application")
        
    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        sys.exit(1)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
