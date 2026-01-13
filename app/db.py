import sqlite3
from contextlib import contextmanager
from app.settings import settings

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS signals (
  disease TEXT NOT NULL,
  region_id TEXT NOT NULL,      -- hier: Bundesland-AGS (2-stellig, z.B. "01")
  week TEXT NOT NULL,           -- ISO-week key: "2026-W01"
  value REAL NOT NULL,
  metric TEXT NOT NULL,         -- z.B. "cases" oder "incidence_per_100k"
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (disease, region_id, week, metric)
);

CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_disease_week ON signals(disease, week);
CREATE INDEX IF NOT EXISTS idx_signals_region ON signals(region_id);
"""

@contextmanager
def conn():
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()

def init_db():
    with conn() as c:
        c.executescript(SCHEMA_SQL)