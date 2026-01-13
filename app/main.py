from fastapi import FastAPI, Query, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db import init_db, conn
from app.ingest import run_full_ingest, get_counties_geojson_cached

app = FastAPI(title="Baby Health Blackbox", version="1.0.0")
scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup():
    init_db()
    await run_full_ingest()

    # Run daily at 06:30 Berlin time
    scheduler.add_job(run_full_ingest, "cron", hour=6, minute=30)
    scheduler.start()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/regions/counties")
async def counties_geojson():
    # Return raw GeoJSON string (frontend does JSON.parse)
    return await get_counties_geojson_cached()

@app.get("/signals/latest")
def latest(
    signal: str = Query(..., description="e.g. COVID_7DAY"),
    metric: str = Query(..., description="e.g. incidence_7d_per_100k, cases_7d"),
):
    with conn() as c:
        max_date = c.execute(
            "SELECT MAX(date) AS d FROM signals WHERE signal=? AND metric=?",
            (signal, metric),
        ).fetchone()["d"]

        if not max_date:
            raise HTTPException(404, "No data for that signal/metric yet")

        rows = c.execute(
            """
            SELECT region_id, value
            FROM signals
            WHERE signal=? AND metric=? AND date=?
            """,
            (signal, metric, max_date),
        ).fetchall()

    return {
        "signal": signal,
        "metric": metric,
        "date": max_date,
        "values": [{"region_id": r["region_id"], "value": r["value"]} for r in rows],
    }

@app.get("/signals/timeseries")
def timeseries(
    signal: str,
    region: str,
    metric: str,
    limit: int = 120
):
    region = region.strip().zfill(5)

    with conn() as c:
        rows = c.execute(
            """
            SELECT date, value
            FROM signals
            WHERE signal=? AND metric=? AND region_id=?
            ORDER BY date DESC
            LIMIT ?
            """,
            (signal, metric, region, limit),
        ).fetchall()

    return {
        "signal": signal,
        "metric": metric,
        "region_id": region,
        "points": [{"date": r["date"], "value": r["value"]} for r in reversed(rows)],
    }