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
  diseaseId: "covid",
  diseaseLabel: "",
  metric: "incidence_7d",
  latest: null,
  timeseries: null,
  geo: null,
  layer: null,
  chart: null,
  map: null,
  diseaseIndex: null
};

const $ = (id) => document.getElementById(id);

function clamp(n, lo, hi) { return n < lo ? lo : (n > hi ? hi : n); }

function formatNumber(n, digits = 1) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(n);
}

function normalizeDistrictKey(raw) {
  if (raw === null || raw === undefined) return "";
  let s = String(raw).replace(/\D/g, "");
  if (!s) return "";
  if (s.length > 5) s = s.slice(0, 5);
  if (s.length < 5) s = s.padStart(5, "0");
  return s;
}

function getDistrictName(feature) {
  const p = feature?.properties || {};
  return p.gen ?? p.GEN ?? p.name ?? p.NAME ?? "Unknown";
}

function getDistrictKeyFromFeature(feature) {
  const p = feature?.properties || {};
  const raw = p.ars ?? p.ARS ?? p.rs ?? p.RS ?? p.ags ?? p.AGS ?? p.krs ?? p.KRS ?? "";
  return normalizeDistrictKey(raw);
}

function districtToStateKey(lk5) {
  // Bundesland id = first two digits of 5-digit Kreis key
  if (!lk5 || lk5.length < 2) return "";
  return `STATE:${lk5.slice(0, 2)}`;
}

function colorRamp(t) {
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170);
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
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return { min: 0, max: 1 };
  return { min, max };
}

async function loadJson(relPath) {
  const url = new URL(relPath, window.location.href);
  const r = await fetch(url, { cache: "no-store" });

  if (!r.ok) {
    const t = await r.text().catch(() => "");
    throw new Error(`Failed to load ${url} (${r.status}). Body: ${t.slice(0, 160)}`);
  }

  const text = await r.text();
  if (!text || text.trim().length < 2) throw new Error(`Empty response from ${url}`);
  return JSON.parse(text);
}

/**
 * For the current dataset:
 * - if resolution === "bundesland": use STATE:XX key
 * - else: use Landkreis 5-digit key
 */
function dataKeyForDistrict(lk5) {
  const res = STATE.latest?.resolution || "landkreis";
  return res === "bundesland" ? districtToStateKey(lk5) : lk5;
}

function latestForDistrict(lk5) {
  const k = dataKeyForDistrict(lk5);
  return STATE.latest?.values?.[k] ?? null;
}

function metricValueForDistrict(lk5) {
  const v = latestForDistrict(lk5);
  if (!v) return null;
  const x = v[STATE.metric];
  return (typeof x === "number" && Number.isFinite(x)) ? x : null;
}

/* Legend */
function buildLegend() {
  const el = $("legend");
  if (!el) return;
  el.innerHTML = "";

  const latestValues = STATE.latest?.values || {};
  const meta = STATE.latest?.metric_meta?.[STATE.metric] || computeMetaMinMax(latestValues, STATE.metric);

  const stops = 5;
  for (let i = 0; i < stops; i++) {
    const q = i / (stops - 1);
    const value = meta.min + q * (meta.max - meta.min);

    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = colorRamp(q);

    const lab = document.createElement("span");
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

function styleFeature(feature) {
  const lk5 = getDistrictKeyFromFeature(feature);
  const v = metricValueForDistrict(lk5);

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
  const lk5 = getDistrictKeyFromFeature(feature);
  const keyUsed = dataKeyForDistrict(lk5);

  const v = latestForDistrict(lk5);
  const inc = v?.incidence_7d ?? null;
  const cases = v?.cases_7d ?? null;
  const trend = v?.trend_pct ?? null;

  const res = STATE.latest?.resolution || "landkreis";
  const resLabel = res === "bundesland" ? "Bundesland" : "Landkreis";

  return `
    <div style="font-weight:600;margin-bottom:4px;">${name}</div>
    <div style="font-size:12px;color:#444;">
      Disease: <b>${STATE.diseaseLabel || STATE.diseaseId}</b><br/>
      Resolution: <b>${resLabel}</b><br/>
      Incidence (7d / week): <b>${formatNumber(inc, 1)}</b><br/>
      Cases (7d / week): <b>${formatNumber(cases, 0)}</b><br/>
      Trend vs prev week: <b>${formatNumber(trend, 1)}%</b><br/>
      Data key: <span style="color:#666">${keyUsed || "—"}</span>
    </div>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipHtml(feature), { sticky: true });
  layer.on("click", () => showPanel(getDistrictName(feature), getDistrictKeyFromFeature(feature)));
}

/* Chart */
function initChart() {
  const canvas = $("chart");
  if (!canvas) return;

  STATE.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Incidence (7d/week) / 100k",
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

function showPanel(name, lk5) {
  $("panelTitle").textContent = name;

  const updated = STATE.latest?.updated_at ?? "unknown";
  const v = latestForDistrict(lk5);

  const keyUsed = dataKeyForDistrict(lk5);
  const res = STATE.latest?.resolution || "landkreis";
  const resLabel = res === "bundesland" ? "Bundesland" : "Landkreis";

  if (!v) {
    $("panelSubtitle").textContent = `No data. Updated: ${updated} • ${resLabel} key: ${keyUsed || "—"}`;
    if (STATE.chart) {
      STATE.chart.data.labels = [];
      STATE.chart.data.datasets[0].data = [];
      STATE.chart.update();
    }
    return;
  }

  $("panelSubtitle").textContent =
    `${STATE.diseaseLabel || STATE.diseaseId} • Updated: ${updated} • ${resLabel} key: ${keyUsed} • ` +
    `Inc: ${formatNumber(v.incidence_7d, 1)} • Cases: ${formatNumber(v.cases_7d, 0)} • Trend: ${formatNumber(v.trend_pct, 1)}%`;

  // timeseries key depends on resolution too
  const seriesKey = keyUsed;
  const series = STATE.timeseries?.series?.[seriesKey];
  if (!series || !STATE.chart) return;

  STATE.chart.data.labels = series.map(pt => pt.date);
  STATE.chart.data.datasets[0].data = series.map(pt => pt.incidence_7d);
  STATE.chart.update();
}

function setHeaderLabels() {
  const updatedAt = $("updatedAt");
  const dLabel = $("diseaseLabel");

  if (dLabel) dLabel.textContent = `Disease: ${STATE.diseaseLabel || STATE.diseaseId}`;
  if (updatedAt) updatedAt.textContent = STATE.latest?.updated_at ? ` • Updated: ${STATE.latest.updated_at}` : "";
}

async function loadDisease(diseaseId) {
  STATE.diseaseId = diseaseId;

  const d = STATE.diseaseIndex?.diseases?.find(x => x.id === diseaseId);
  STATE.diseaseLabel = d?.label || diseaseId;

  const base = `data/diseases/${diseaseId}`;
  const [latest, timeseries] = await Promise.all([
    loadJson(`${base}/latest.json`),
    loadJson(`${base}/timeseries.json`)
  ]);

  STATE.latest = latest;
  STATE.timeseries = timeseries;

  if (!STATE.latest.metric_meta) STATE.latest.metric_meta = {};
  for (const m of ["incidence_7d", "cases_7d", "trend_pct"]) {
    if (!STATE.latest.metric_meta[m]) {
      STATE.latest.metric_meta[m] = computeMetaMinMax(STATE.latest.values || {}, m);
    }
  }

  setHeaderLabels();
  if (STATE.layer) STATE.layer.setStyle(styleFeature);
  buildLegend();
}

async function main() {
  STATE.map = L.map("map", { zoomSnap: 0.25 }).setView(CONFIG.center, CONFIG.zoom);

  L.tileLayer(CONFIG.tileUrl, {
    maxZoom: CONFIG.maxZoom,
    attribution: CONFIG.tileAttribution
  }).addTo(STATE.map);

  // Load geo once
  const [index, geo] = await Promise.all([
    loadJson("data/diseases/index.json"),
    loadJson("data/landkreise.geojson")
  ]);

  STATE.diseaseIndex = index;
  STATE.geo = geo;

  // Build disease dropdown
  const diseaseSel = $("disease");
  if (diseaseSel) {
    diseaseSel.innerHTML = "";
    for (const d of index.diseases || []) {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = d.label || d.id;
      diseaseSel.appendChild(opt);
    }
  }

  // Create layer once
  STATE.layer = L.geoJSON(geo, { style: styleFeature, onEachFeature }).addTo(STATE.map);
  try { STATE.map.fitBounds(STATE.layer.getBounds(), { padding: [10, 10] }); } catch (_) {}

  initChart();

  // Metric dropdown
  const metricSel = $("metric");
  if (metricSel) {
    metricSel.value = STATE.metric;
    metricSel.addEventListener("change", (e) => {
      STATE.metric = e.target.value;
      if (STATE.layer) STATE.layer.setStyle(styleFeature);
      buildLegend();
    });
  }

  // Default disease (or from URL hash)
  const fromHash = (window.location.hash || "").replace("#", "").trim();
  const initial = fromHash || STATE.diseaseId;
  if (diseaseSel) diseaseSel.value = initial;

  await loadDisease(initial);

  if (diseaseSel) {
    diseaseSel.addEventListener("change", async (e) => {
      const id = e.target.value;
      window.location.hash = id;
      await loadDisease(id);
    });
  }
}

main().catch((err) => {
  console.error(err);
  alert("Failed to load map data.\n\nOpen DevTools → Console to see details.\n\n" + String(err));
});
