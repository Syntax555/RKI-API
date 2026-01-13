import sqlite3
from contextlib import contextmanager
from app.settings import settings

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

-- normalized signal table
CREATE TABLE IF NOT EXISTS signals (
  signal TEXT NOT NULL,         -- e.g. COVID_7DAY
  metric TEXT NOT NULL,         -- e.g. incidence_7d_per_100k, cases_7d
  region_id TEXT NOT NULL,      -- AGS for county (5 digits), e.g. "05315"
  date TEXT NOT NULL,           -- ISO date, e.g. "2026-01-14"
  value REAL NOT NULL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (signal, metric, region_id, date)
);

-- simple cache (geojson, metadata)
CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_signals_signal_date ON signals(signal, date);
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