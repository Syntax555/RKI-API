from fastapi import FastAPI, Query, HTTPException
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db import init_db, conn
from app.ingest import run_full_ingest, get_cached_geojson

app = FastAPI(title="Baby Disease Blackbox", version="0.1.0")

scheduler = AsyncIOScheduler()

@app.on_event("startup")
async def startup():
    init_db()

    # 1) einmalig beim Start importieren
    await run_full_ingest()

    # 2) danach regelmäßig (z.B. täglich 06:30)
    scheduler.add_job(run_full_ingest, "cron", hour=6, minute=30)
    scheduler.start()

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/diseases")
def diseases():
    with conn() as c:
        rows = c.execute("SELECT DISTINCT disease FROM signals ORDER BY disease").fetchall()
    return [r["disease"] for r in rows]

@app.get("/regions")
async def regions():
    # GeoJSON Bundesländer (cached)
    geojson_text = await get_cached_geojson()
    return geojson_text  # FastAPI sendet string -> Frontend kann JSON.parse()

@app.get("/latest")
def latest(
    disease: str = Query(..., description="z.B. RSV, INFLUENZA, ARE_EST"),
    metric: str = Query("incidence_per_100k", description="incidence_per_100k oder cases"),
):
    with conn() as c:
        max_week = c.execute(
            "SELECT MAX(week) AS w FROM signals WHERE disease=? AND metric=?",
            (disease, metric),
        ).fetchone()["w"]

        if not max_week:
            raise HTTPException(404, "No data for this disease/metric yet")

        rows = c.execute(
            """
            SELECT region_id, value
            FROM signals
            WHERE disease=? AND metric=? AND week=?
            """,
            (disease, metric, max_week),
        ).fetchall()

    return {"disease": disease, "metric": metric, "week": max_week,
            "values": [{"region_id": r["region_id"], "value": r["value"]} for r in rows]}

@app.get("/timeseries")
def timeseries(
    disease: str,
    region: str,
    metric: str = "incidence_per_100k",
    limit: int = 52
):
    with conn() as c:
        rows = c.execute(
            """
            SELECT week, value
            FROM signals
            WHERE disease=? AND region_id=? AND metric=?
            ORDER BY week DESC
            LIMIT ?
            """,
            (disease, region, metric, limit),
        ).fetchall()

    return {
        "disease": disease,
        "region_id": region,
        "metric": metric,
        "points": [{"week": r["week"], "value": r["value"]} for r in reversed(rows)]
    }