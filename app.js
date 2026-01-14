/* global L, Chart */
"use strict";

/* =====================
   CONFIG + STATE
===================== */

const CONFIG = {
  center: [51.1, 10.4],
  zoom: 6,
  maxZoom: 10,
  tileUrl: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
  tileAttribution: "&copy; OpenStreetMap contributors"
};

const STATE = {
  map: null,
  layer: null,
  chart: null,

  geo: null,
  diseaseIndex: null,

  diseaseId: null,
  diseaseLabel: "",
  metric: "incidence_7d",

  latest: null,
  timeseries: null
};

const $ = (id) => document.getElementById(id);

/* =====================
   HELPERS
===================== */

function clamp(v, min, max) {
  return v < min ? min : (v > max ? max : v);
}

function formatNumber(n, digits = 1) {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("de-DE", {
    maximumFractionDigits: digits
  }).format(n);
}

function normalizeDistrictKey(raw) {
  if (!raw) return "";
  let s = String(raw).replace(/\D/g, "");
  if (s.length > 5) s = s.slice(0, 5);
  return s.padStart(5, "0");
}

function getDistrictKey(feature) {
  if (feature.__key5) return feature.__key5;

  const p = feature.properties || {};
  const raw =
    p.ars ?? p.ARS ??
    p.rs  ?? p.RS  ??
    p.ags ?? p.AGS ??
    p.krs ?? p.KRS ?? "";

  feature.__key5 = normalizeDistrictKey(raw);
  return feature.__key5;
}

function getDistrictName(feature) {
  const p = feature.properties || {};
  return p.gen ?? p.GEN ?? p.name ?? p.NAME ?? "Unknown";
}

function colorRamp(t) {
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170);
  return `rgb(${v},${v},255)`;
}

async function loadJson(path) {
  const url = new URL(path, window.location.href);
  const res = await fetch(url, { cache: "no-store" });

  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`Failed to load ${url} (${res.status}): ${text.slice(0, 120)}`);
  }
  return res.json();
}

/* =====================
   DATA ACCESS
===================== */

function latestForKey(key5) {
  return STATE.latest?.values?.[key5] ?? null;
}

function metricValueForKey(key5) {
  const v = latestForKey(key5);
  const x = v?.[STATE.metric];
  return Number.isFinite(x) ? x : null;
}

/* =====================
   MAP STYLING
===================== */

function styleFeature(feature) {
  const key = getDistrictKey(feature);
  const value = metricValueForKey(key);

  const meta = STATE.latest.metric_meta[STATE.metric];
  let t = 0;

  if (value !== null && meta.max > meta.min) {
    t = (value - meta.min) / (meta.max - meta.min);
  }

  return {
    weight: 1,
    color: "#999",
    fillOpacity: value === null ? 0.15 : 0.75,
    fillColor: value === null ? "#eee" : colorRamp(t)
  };
}

function tooltipHtml(feature) {
  const key = getDistrictKey(feature);
  const v = latestForKey(key);

  return `
    <div style="font-weight:600;margin-bottom:4px;">
      ${getDistrictName(feature)}
    </div>
    <div style="font-size:12px;">
      Disease: <b>${STATE.diseaseLabel}</b><br/>
      Incidence (7d): <b>${formatNumber(v?.incidence_7d, 1)}</b><br/>
      Cases (7d): <b>${formatNumber(v?.cases_7d, 0)}</b><br/>
      Trend: <b>${formatNumber(v?.trend_pct, 1)}%</b>
    </div>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipHtml(feature), { sticky: true });
  layer.on("click", () => showPanel(feature));
}

/* =====================
   LEGEND
===================== */

function buildLegend() {
  const el = $("legend");
  if (!el) return;

  el.innerHTML = "";
  const meta = STATE.latest.metric_meta[STATE.metric];
  const stops = 5;

  for (let i = 0; i < stops; i++) {
    const q = i / (stops - 1);
    const value = meta.min + q * (meta.max - meta.min);

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.style.background = colorRamp(q);

    const label = document.createElement("span");
    const digits = STATE.metric === "cases_7d" ? 0 : 1;
    label.textContent =
      `${formatNumber(value, digits)}${STATE.metric === "trend_pct" ? "%" : ""}`;

    const wrap = document.createElement("span");
    wrap.style.display = "inline-flex";
    wrap.style.gap = "6px";
    wrap.appendChild(swatch);
    wrap.appendChild(label);

    el.appendChild(wrap);
  }
}

/* =====================
   PANEL + CHART
===================== */

function initChart() {
  const canvas = $("chart");
  if (!canvas) return;

  STATE.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "7-day incidence / 100k",
        data: [],
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.25
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true } },
      scales: {
        x: { ticks: { maxTicksLimit: 8 } },
        y: { beginAtZero: true }
      }
    }
  });
}

function showPanel(feature) {
  const name = getDistrictName(feature);
  const key = getDistrictKey(feature);
  const v = latestForKey(key);

  $("panelTitle").textContent = name;

  if (!v) {
    $("panelSubtitle").textContent = "No data for this district.";
    STATE.chart.data.labels = [];
    STATE.chart.data.datasets[0].data = [];
    STATE.chart.update();
    return;
  }

  $("panelSubtitle").textContent =
    `${STATE.diseaseLabel} • Updated: ${STATE.latest.updated_at}`;

  const series = STATE.timeseries.series[key];
  if (!series) return;

  STATE.chart.data.labels = series.map(p => p.date);
  STATE.chart.data.datasets[0].data = series.map(p => p.incidence_7d);
  STATE.chart.update();
}

/* =====================
   DISEASE LOADING
===================== */

async function loadDisease(diseaseId) {
  STATE.diseaseId = diseaseId;

  const d = STATE.diseaseIndex.diseases.find(x => x.id === diseaseId);
  STATE.diseaseLabel = d?.label || diseaseId;

  const base = `data/diseases/${diseaseId}`;
  [STATE.latest, STATE.timeseries] = await Promise.all([
    loadJson(`${base}/latest.json`),
    loadJson(`${base}/timeseries.json`)
  ]);

  $("diseaseLabel").textContent = `Disease: ${STATE.diseaseLabel}`;
  $("updatedAt").textContent = ` • Updated: ${STATE.latest.updated_at}`;

  STATE.layer.setStyle(styleFeature);
  buildLegend();
}

/* =====================
   MAIN
===================== */

async function main() {
  STATE.map = L.map("map").setView(CONFIG.center, CONFIG.zoom);

  L.tileLayer(CONFIG.tileUrl, {
    maxZoom: CONFIG.maxZoom,
    attribution: CONFIG.tileAttribution
  }).addTo(STATE.map);

  const [index, geo] = await Promise.all([
    loadJson("data/diseases/index.json"),
    loadJson("data/landkreise.geojson")
  ]);

  STATE.diseaseIndex = index;
  STATE.geo = geo;

  const diseaseSelect = $("disease");
  diseaseSelect.innerHTML = "";

  for (const d of index.diseases) {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = d.label;
    diseaseSelect.appendChild(opt);
  }

  STATE.layer = L.geoJSON(geo, {
    style: styleFeature,
    onEachFeature
  }).addTo(STATE.map);

  try {
    STATE.map.fitBounds(STATE.layer.getBounds(), { padding: [10, 10] });
  } catch (_) {}

  initChart();

  const metricSelect = $("metric");
  metricSelect.addEventListener("change", (e) => {
    STATE.metric = e.target.value;
    STATE.layer.setStyle(styleFeature);
    buildLegend();
  });

  const initialDisease = window.location.hash.replace("#", "") || index.diseases[0].id;
  diseaseSelect.value = initialDisease;
  await loadDisease(initialDisease);

  diseaseSelect.addEventListener("change", async (e) => {
    window.location.hash = e.target.value;
    await loadDisease(e.target.value);
  });
}

main().catch(err => {
  console.error(err);
  alert("Failed to load map data.\n\n" + err.message);
});
