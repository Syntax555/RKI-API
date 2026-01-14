/* global L, Chart */
"use strict";

/* =============================
   CONFIG + STATE
============================= */

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
  resolution: "landkreis",
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

/* =============================
   HELPERS
============================= */

function clamp(n, lo, hi) {
  return n < lo ? lo : (n > hi ? hi : n);
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

function getDistrictName(feature) {
  const p = feature?.properties || {};
  return p.gen ?? p.GEN ?? p.name ?? "Unknown";
}

function getDistrictKey(feature) {
  const p = feature?.properties || {};
  return normalizeDistrictKey(
    p.ars ?? p.ARS ?? p.rs ?? p.RS ?? p.ags ?? p.AGS ?? ""
  );
}

function getBundeslandKey(feature) {
  const lk = getDistrictKey(feature);
  return lk ? `STATE:${lk.slice(0, 2)}` : "";
}

function mapKeyForFeature(feature) {
  return STATE.resolution === "bundesland"
    ? getBundeslandKey(feature)
    : getDistrictKey(feature);
}

function colorRamp(t) {
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170);
  return `rgb(${v},${v},255)`;
}

/* =============================
   DATA ACCESS
============================= */

async function loadJson(path) {
  const url = new URL(path, window.location.href);
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to load ${path}`);
  return r.json();
}

function latestForKey(key) {
  return STATE.latest?.values?.[key] ?? null;
}

function metricValueForKey(key) {
  const v = latestForKey(key);
  if (!v) return null;
  const x = v[STATE.metric];
  return Number.isFinite(x) ? x : null;
}

/* =============================
   LEGEND
============================= */

function buildLegend() {
  const el = $("legend");
  if (!el) return;
  el.innerHTML = "";

  const meta = STATE.latest.metric_meta[STATE.metric];
  for (let i = 0; i < 5; i++) {
    const q = i / 4;
    const value = meta.min + q * (meta.max - meta.min);

    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = colorRamp(q);

    const lab = document.createElement("span");
    lab.textContent = formatNumber(value, 1);

    el.append(sw, lab);
  }
}

/* =============================
   MAP STYLING
============================= */

function styleFeature(feature) {
  const key = mapKeyForFeature(feature);
  const v = metricValueForKey(key);

  const meta = STATE.latest.metric_meta[STATE.metric];
  let t = 0;
  if (v !== null && meta.max > meta.min) {
    t = (v - meta.min) / (meta.max - meta.min);
  }

  return {
    weight: 1,
    color: "#999",
    fillOpacity: v === null ? 0.15 : 0.75,
    fillColor: v === null ? "#eee" : colorRamp(t)
  };
}

function tooltipHtml(feature) {
  const name = getDistrictName(feature);
  const key = mapKeyForFeature(feature);
  const v = latestForKey(key);

  return `
    <strong>${name}</strong><br/>
    Disease: <b>${STATE.diseaseLabel}</b><br/>
    Resolution: <b>${STATE.resolution}</b><br/>
    Incidence: <b>${formatNumber(v?.incidence_7d)}</b><br/>
    Cases (7d): <b>${formatNumber(v?.cases_7d, 0)}</b>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipHtml(feature), { sticky: true });
}

/* =============================
   CHART
============================= */

function initChart() {
  STATE.chart = new Chart($("chart"), {
    type: "line",
    data: { labels: [], datasets: [{ data: [] }] },
    options: { responsive: true }
  });
}

/* =============================
   HEADER LABELS
============================= */

function updateHeader() {
  $("diseaseLabel").textContent =
    `Disease: ${STATE.diseaseLabel} • Resolution: ${STATE.resolution}`;
  $("updatedAt").textContent =
    STATE.latest?.updated_at ? `Updated: ${STATE.latest.updated_at}` : "";
}

/* =============================
   DISEASE LOADING
============================= */

async function loadDisease(id) {
  const d = STATE.diseaseIndex.diseases.find(x => x.id === id);
  if (!d) return;

  STATE.diseaseId = id;
  STATE.diseaseLabel = d.label;
  STATE.resolution = d.resolution;

  const base = `data/diseases/${id}`;
  [STATE.latest, STATE.timeseries] = await Promise.all([
    loadJson(`${base}/latest.json`),
    loadJson(`${base}/timeseries.json`)
  ]);

  updateHeader();
  STATE.layer.setStyle(styleFeature);
  buildLegend();
}

/* =============================
   MAIN
============================= */

async function main() {
  STATE.map = L.map("map").setView(CONFIG.center, CONFIG.zoom);
  L.tileLayer(CONFIG.tileUrl, { attribution: CONFIG.tileAttribution }).addTo(STATE.map);

  const [index, geo] = await Promise.all([
    loadJson("data/diseases/index.json"),
    loadJson("data/landkreise.geojson")
  ]);

  STATE.diseaseIndex = index;
  STATE.geo = geo;

  STATE.layer = L.geoJSON(geo, {
    style: styleFeature,
    onEachFeature
  }).addTo(STATE.map);

  initChart();

  const sel = $("disease");
  index.diseases.forEach(d => {
    const o = document.createElement("option");
    o.value = d.id;
    o.textContent = d.label;
    sel.appendChild(o);
  });

  sel.addEventListener("change", e => loadDisease(e.target.value));

  await loadDisease(STATE.diseaseId);
}

main().catch(err => {
  console.error(err);
  alert("Failed to load data");
});
