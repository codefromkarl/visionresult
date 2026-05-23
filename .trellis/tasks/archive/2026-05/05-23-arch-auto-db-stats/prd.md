# PRD: Optimize get_database_stats to single query

## Category
perf

## Problem
`get_database_stats()` in `core/database.py` makes 4 separate COUNT queries:
```python
total = session.query(AnalysisRecord).count()
completed = session.query(AnalysisRecord).filter_by(status="completed").count()
failed = session.query(AnalysisRecord).filter_by(status="failed").count()
pending = session.query(AnalysisRecord).filter(...).count()
```

This is inefficient — a single GROUP BY query can retrieve all counts in one round trip.

## What to Change
Replace the 4 separate COUNT queries with a single aggregated query using `GROUP BY`:
```python
from sqlalchemy import func
results = session.query(AnalysisRecord.status, func.count()).group_by(AnalysisRecord.status).all()
```

Then map the results to the expected dict format.

## Acceptance Criteria
1. `get_database_stats()` returns the same dict format as before
2. Only 1 SQL query is executed instead of 4
3. Existing tests pass
4. No functional changes to other parts of the system

## Scope
Only modify: `src/vision_insight/core/database.py`

## Evidence
- File: `src/vision_insight/core/database.py` lines 288-305
- Current implementation makes 4 separate queries

## Statement
No functional changes — this is a performance optimization only.
