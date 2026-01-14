/* app.js
   Simple + optimized GitHub Pages map:
   - Leaflet choropleth by Landkreis
   - Loads: data/latest.json, data/timeseries.json, data/landkreise.geojson
   - Metric selector: incidence_7d, cases_7d, trend_pct
   - Hover tooltip, click panel + Chart.js time series
*/

/* global L, Chart */

"use strict";

const CONFIG = {
  center: [51.1, 10.4],
  zoom: 6,
  tileUrl: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  tileAttribution: "&copy; OpenStreetMap contributors",
  maxZoom: 10
};

const STATE = {
  metric: "incidence_7d",
  latest: null,
  timeseries: null,
  geo: null,
  layer: null,
  chart: null,
  map: null
};

/* -----------------------------
   Helpers
------------------------------ */

const $ = (id) => document.getElementById(id);

function clamp(n, lo, hi) {
  return n < lo ? lo : (n > hi ? hi : n);
}

function formatNumber(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(n);
}

function getDistrictName(feature) {
  const p = feature?.properties || {};
  return p.gen ?? p.GEN ?? p.name ?? p.NAME ?? "Unknown";
}

function getDistrictId(feature) {
  // BKG VG250 WFS often has "ars" for Landkreis
  const p = feature?.properties || {};
  const id = p.ars ?? p.ARS ?? p.rs ?? p.RS ?? p.ags ?? p.AGS ?? "";
  return String(id).trim();
}

function colorRamp(t) {
  // Very light -> darker blue; fast + no deps
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170); // 245..75
  return `rgb(${v},${v},255)`;
}

function computeMetaMinMax(latestValues, metric) {
  let min = Infinity, max = -Infinity;
  for (const k in latestValues) {
    const v = latestValues[k]?.[metric];
    if (typeof v === "number" && Number.isFinite(v)) {
      if (v < min) min = v;
      if (v > max) max = v;
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) {
    return { min: 0, max: 1 };
  }
  return { min, max };
}

/**
 * Robust JSON loader for GitHub Pages.
 * - Resolves relative paths against current page URL (important for /REPO/ pages)
 * - Fetches text first so we can debug truncation / HTML / empties
 */
async function loadJson(relPath) {
  const url = new URL(relPath, window.location.href);
  const r = await fetch(url, { cache: "no-store" });

  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`Failed to load ${url} (${r.status}). Body: ${t.slice(0, 160)}`);
  }

  const text = await r.text();
  if (!text || text.trim().length < 2) {
    throw new Error(`Empty response from ${url}`);
  }

  try {
    return JSON.parse(text);
  } catch (e) {
    throw new Error(`Bad JSON from ${url}. First 160 chars: ${text.slice(0, 160)}`);
  }
}

/* -----------------------------
   Data access
------------------------------ */

function latestForId(id) {
  return STATE.latest?.values?.[id] ?? null;
}

function metricValueForId(id) {
  const v = latestForId(id);
  if (!v) return null;
  const x = v[STATE.metric];
  return (typeof x === "number" && Number.isFinite(x)) ? x : null;
}

/* -----------------------------
   Legend
------------------------------ */

function buildLegend() {
  const el = $("legend");
  if (!el) return;

  el.innerHTML = "";

  const latestValues = STATE.latest?.values || {};
  const meta = STATE.latest?.metric_meta?.[STATE.metric] || computeMetaMinMax(latestValues, STATE.metric);

  // 5 swatches labeled by metric values at those stops
  const stops = 5;
  for (let i = 0; i < stops; i++) {
    const q = i / (stops - 1);
    const value = meta.min + q * (meta.max - meta.min);

    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = colorRamp(q);

    const lab = document.createElement("span");
    // trend is %; others are numeric
    const digits = (STATE.metric === "cases_7d") ? 0 : 1;
    lab.textContent = `${formatNumber(value, digits)}${STATE.metric === "trend_pct" ? "%" : ""}`;

    const wrap = document.createElement("span");
    wrap.style.display = "inline-flex";
    wrap.style.gap = "6px";
    wrap.style.alignItems = "center";
    wrap.appendChild(sw);
    wrap.appendChild(lab);

    el.appendChild(wrap);
  }
}

function refreshLayerStyles() {
  if (STATE.layer) STATE.layer.setStyle(styleFeature);
  buildLegend();
}

/* -----------------------------
   Leaflet styling + tooltip
------------------------------ */

function styleFeature(feature) {
  const id = getDistrictId(feature);
  const v = metricValueForId(id);

  const latestValues = STATE.latest?.values || {};
  const meta = STATE.latest?.metric_meta?.[STATE.metric] || computeMetaMinMax(latestValues, STATE.metric);

  let t = 0;
  if (v !== null && meta.max > meta.min) t = (v - meta.min) / (meta.max - meta.min);

  return {
    weight: 1,
    color: "#999",
    fillOpacity: v === null ? 0.15 : 0.75,
    fillColor: v === null ? "#eee" : colorRamp(t)
  };
}

function tooltipHtml(feature) {
  const name = getDistrictName(feature);
  const id = getDistrictId(feature);

  const v = latestForId(id);
  const inc = v?.incidence_7d ?? null;
  const cases = v?.cases_7d ?? null;
  const trend = v?.trend_pct ?? null;

  return `
    <div style="font-weight:600;margin-bottom:4px;">${name}</div>
    <div style="font-size:12px;color:#444;">
      7-day incidence (0–14): <b>${formatNumber(inc, 1)}</b><br/>
      7-day cases (0–14): <b>${formatNumber(cases, 0)}</b><br/>
      Trend vs prev week: <b>${formatNumber(trend, 1)}%</b><br/>
      ID: <span style="color:#666">${id || "—"}</span>
    </div>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipHtml(feature), { sticky: true });

  layer.on("click", () => {
    const name = getDistrictName(feature);
    const id = getDistrictId(feature);
    showPanel(name, id);
  });
}

/* -----------------------------
   Chart
------------------------------ */

function initChart() {
  const canvas = $("chart");
  if (!canvas) return;

  STATE.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "7-day incidence / 100k (0–14)",
        data: [],
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.25
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: true },
        tooltip: { mode: "index", intersect: false }
      },
      scales: {
        x: { ticks: { maxTicksLimit: 8 } },
        y: { beginAtZero: true }
      }
    }
  });
}

function showPanel(name, id) {
  $("panelTitle").textContent = name;

  const updated = STATE.latest?.updated_at ?? "unknown";
  const v = latestForId(id);

  if (!v) {
    $("panelSubtitle").textContent = `No data for this district. Updated: ${updated}`;
    if (STATE.chart) {
      STATE.chart.data.labels = [];
      STATE.chart.data.datasets[0].data = [];
      STATE.chart.update();
    }
    return;
  }

  $("panelSubtitle").textContent =
    `Updated: ${updated} • 7d incidence: ${formatNumber(v.incidence_7d, 1)} • 7d cases: ${formatNumber(v.cases_7d, 0)} • Trend: ${formatNumber(v.trend_pct, 1)}%`;

  const series = STATE.timeseries?.series?.[id];
  if (!series || !STATE.chart) return;

  STATE.chart.data.labels = series.map(pt => pt.date);
  STATE.chart.data.datasets[0].data = series.map(pt => pt.incidence_7d);
  STATE.chart.update();
}

/* -----------------------------
   Main init
------------------------------ */

async function main() {
  // Map
  STATE.map = L.map("map", { zoomSnap: 0.25 }).setView(CONFIG.center, CONFIG.zoom);

  L.tileLayer(CONFIG.tileUrl, {
    maxZoom: CONFIG.maxZoom,
    attribution: CONFIG.tileAttribution
  }).addTo(STATE.map);

  // Load all data in parallel
  const [latest, timeseries, geo] = await Promise.all([
    loadJson("data/latest.json"),
    loadJson("data/timeseries.json"),
    loadJson("data/landkreise.geojson")
  ]);

  STATE.latest = latest;
  STATE.timeseries = timeseries;
  STATE.geo = geo;

  // Ensure metric_meta exists (older/latest.json might not include it)
  if (!STATE.latest.metric_meta) STATE.latest.metric_meta = {};
  for (const m of ["incidence_7d", "cases_7d", "trend_pct"]) {
    if (!STATE.latest.metric_meta[m]) {
      STATE.latest.metric_meta[m] = computeMetaMinMax(STATE.latest.values || {}, m);
    }
  }

  // Updated label
  const updatedAt = $("updatedAt");
  if (updatedAt) updatedAt.textContent = latest.updated_at ? `Updated: ${latest.updated_at}` : "";

  // Geo layer
  STATE.layer = L.geoJSON(geo, { style: styleFeature, onEachFeature }).addTo(STATE.map);

  // Fit to bounds (Germany)
  try {
    STATE.map.fitBounds(STATE.layer.getBounds(), { padding: [10, 10] });
  } catch (_) { /* ignore */ }

  initChart();
  buildLegend();

  // Metric selector
  const metricSel = $("metric");
  if (metricSel) {
    metricSel.value = STATE.metric;
    metricSel.addEventListener("change", (e) => {
      STATE.metric = e.target.value;
      refreshLayerStyles();
    });
  }
}

// Start
main().catch((err) => {
  console.error(err);
  alert(
    "Failed to load map data.\n\n" +
    "Open DevTools → Console to see which file failed.\n\n" +
    String(err)
  );
});