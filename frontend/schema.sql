-- D1 数据库 schema
CREATE TABLE IF NOT EXISTS analyses (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'pending',
  filename TEXT,
  result TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_analyses_status ON analyses(status);
CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at);
