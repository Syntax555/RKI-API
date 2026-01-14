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
  resolution: "landkreis", // "landkreis" | "bundesland"
  ageGroup: null,          // optional from dataset
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
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(n);
}

function metricLabel(metric) {
  if (metric === "incidence_7d") return "7-day incidence / 100k";
  if (metric === "cases_7d") return "7-day cases";
  if (metric === "trend_pct") return "Trend vs. previous week (%)";
  return metric;
}

function metricDigits(metric) {
  if (metric === "cases_7d") return 0;
  return 1;
}

function metricSuffix(metric) {
  return metric === "trend_pct" ? "%" : "";
}

function resolutionPretty(res) {
  return res === "bundesland" ? "Bundesland-level" : "Landkreis-level";
}

function normalizeDistrictKey(raw) {
  if (!raw) return "";
  let s = String(raw).replace(/\D/g, "");
  if (!s) return "";
  if (s.length > 5) s = s.slice(0, 5);
  return s.padStart(5, "0");
}

function getDistrictName(feature) {
  const p = feature?.properties || {};
  return p.gen ?? p.GEN ?? p.name ?? p.NAME ?? "Unknown";
}

function getDistrictKey(feature) {
  const p = feature?.properties || {};
  return normalizeDistrictKey(p.ars ?? p.ARS ?? p.rs ?? p.RS ?? p.ags ?? p.AGS ?? "");
}

function getBundeslandKeyFromDistrictKey(lk5) {
  if (!lk5 || lk5.length < 2) return "";
  return `STATE:${lk5.slice(0, 2)}`;
}

function getBundeslandKey(feature) {
  const lk = getDistrictKey(feature);
  return getBundeslandKeyFromDistrictKey(lk);
}

/** Key used to look up data in JSON (district or state key) */
function dataKeyForFeature(feature) {
  return STATE.resolution === "bundesland" ? getBundeslandKey(feature) : getDistrictKey(feature);
}

/** Key used for panel/chart (same logic, but we also return display hints) */
function panelKeyForFeature(feature) {
  const lk = getDistrictKey(feature);
  if (STATE.resolution === "bundesland") {
    return { key: getBundeslandKeyFromDistrictKey(lk), districtKey: lk };
  }
  return { key: lk, districtKey: lk };
}

function colorRamp(t) {
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170); // light -> darker blue
  return `rgb(${v},${v},255)`;
}

/* =============================
   DATA ACCESS
============================= */

async function loadJson(path) {
  const url = new URL(path, window.location.href);
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`Failed to load ${path} (${r.status}). ${body.slice(0, 120)}`);
  }
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
  if (!el || !STATE.latest?.metric_meta?.[STATE.metric]) return;

  el.innerHTML = "";

  const meta = STATE.latest.metric_meta[STATE.metric];
  const stops = 5;

  for (let i = 0; i < stops; i++) {
    const q = i / (stops - 1);
    const value = meta.min + q * (meta.max - meta.min);

    const wrap = document.createElement("span");
    wrap.style.display = "inline-flex";
    wrap.style.alignItems = "center";
    wrap.style.gap = "6px";

    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = colorRamp(q);

    const lab = document.createElement("span");
    lab.textContent = `${formatNumber(value, metricDigits(STATE.metric))}${metricSuffix(STATE.metric)}`;

    wrap.appendChild(sw);
    wrap.appendChild(lab);
    el.appendChild(wrap);
  }
}

/* =============================
   MAP STYLING + TOOLTIP
============================= */

function styleFeature(feature) {
  const key = dataKeyForFeature(feature);
  const v = metricValueForKey(key);

  const meta = STATE.latest?.metric_meta?.[STATE.metric];
  let t = 0;
  if (v !== null && meta && meta.max > meta.min) {
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
  const { key } = panelKeyForFeature(feature);
  const v = latestForKey(key);

  const inc = v?.incidence_7d ?? null;
  const cases = v?.cases_7d ?? null;
  const trend = v?.trend_pct ?? null;

  return `
    <div style="font-weight:600;margin-bottom:4px;">${name}</div>
    <div style="font-size:12px;color:#444;line-height:1.35;">
      Disease: <b>${STATE.diseaseLabel || STATE.diseaseId}</b><br/>
      Resolution: <b>${resolutionPretty(STATE.resolution)}</b>${STATE.ageGroup ? ` • Age: <b>${STATE.ageGroup}</b>` : ""}<br/>
      Incidence: <b>${formatNumber(inc, 1)}</b><br/>
      Cases (7d): <b>${formatNumber(cases, 0)}</b><br/>
      Trend: <b>${formatNumber(trend, 1)}%</b><br/>
      Key used: <span style="color:#666">${key || "—"}</span>
    </div>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipHtml(feature), { sticky: true });

  layer.on("click", () => {
    const name = getDistrictName(feature);
    const { key } = panelKeyForFeature(feature);
    showPanel(name, key);
  });
}

/* =============================
   PANEL + CHART
============================= */

function initChart() {
  const canvas = $("chart");
  if (!canvas) return;

  STATE.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "",
        data: [],
        pointRadius: 0,
        borderWidth: 2,
        tension: 0.25
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { display: true } },
      scales: { y: { beginAtZero: true } }
    }
  });
}

function setChart(series) {
  if (!STATE.chart) return;

  const labels = (series || []).map(p => p.date);
  const data = (series || []).map(p => {
    // prefer incidence for chart (keeps comparable across datasets)
    const x = p.incidence_7d;
    return Number.isFinite(x) ? x : null;
  });

  STATE.chart.data.labels = labels;
  STATE.chart.data.datasets[0].data = data;
  STATE.chart.data.datasets[0].label = `${STATE.diseaseLabel} — incidence`;
  STATE.chart.update();
}

function showPanel(name, dataKey) {
  const title = $("panelTitle");
  const sub = $("panelSubtitle");

  if (title) title.textContent = name;

  const updated = STATE.latest?.updated_at ?? "unknown";
  const v = latestForKey(dataKey);

  if (!v) {
    if (sub) sub.textContent = `No data for this area. Updated: ${updated} • Key: ${dataKey || "—"}`;
    setChart([]);
    return;
  }

  const inc = v.incidence_7d ?? null;
  const cases = v.cases_7d ?? null;
  const trend = v.trend_pct ?? null;

  if (sub) {
    sub.textContent =
      `${STATE.diseaseLabel} • ${resolutionPretty(STATE.resolution)} • Updated: ${updated} • ` +
      `Inc: ${formatNumber(inc, 1)} • Cases: ${formatNumber(cases, 0)} • Trend: ${formatNumber(trend, 1)}% • Key: ${dataKey}`;
  }

  const series = STATE.timeseries?.series?.[dataKey];
  setChart(series || []);
}

/* =============================
   HEADER / CONTROLS
============================= */

function updateHeader() {
  const diseaseLabel = $("diseaseLabel");
  const updatedAt = $("updatedAt");

  const extra = `${resolutionPretty(STATE.resolution)}${STATE.ageGroup ? ` • Age: ${STATE.ageGroup}` : ""}`;
  if (diseaseLabel) diseaseLabel.textContent = `Disease: ${STATE.diseaseLabel || STATE.diseaseId} • ${extra}`;

  if (updatedAt) updatedAt.textContent = STATE.latest?.updated_at ? `Updated: ${STATE.latest.updated_at}` : "";
}

function refreshMap() {
  if (STATE.layer) STATE.layer.setStyle(styleFeature);
  buildLegend();
}

/* =============================
   DISEASE LOADING
============================= */

async function loadDisease(id) {
  const d = STATE.diseaseIndex?.diseases?.find(x => x.id === id);
  if (!d) throw new Error(`Unknown disease id: ${id}`);

  STATE.diseaseId = id;
  STATE.diseaseLabel = d.label || id;
  STATE.resolution = d.resolution || "landkreis";

  const base = `data/diseases/${id}`;
  const [latest, timeseries] = await Promise.all([
    loadJson(`${base}/latest.json`),
    loadJson(`${base}/timeseries.json`)
  ]);

  STATE.latest = latest;
  STATE.timeseries = timeseries;

  // optional extras from dataset files
  STATE.ageGroup = latest?.age_group || timeseries?.age_group || d.age_group || null;

  // safety: ensure metric_meta exists
  if (!STATE.latest.metric_meta) STATE.latest.metric_meta = {};
  if (!STATE.latest.metric_meta.incidence_7d) STATE.latest.metric_meta.incidence_7d = { min: 0, max: 1 };
  if (!STATE.latest.metric_meta.cases_7d) STATE.latest.metric_meta.cases_7d = { min: 0, max: 1 };
  if (!STATE.latest.metric_meta.trend_pct) STATE.latest.metric_meta.trend_pct = { min: 0, max: 1 };

  updateHeader();
  refreshMap();

  // reset panel
  const panelTitle = $("panelTitle");
  const panelSubtitle = $("panelSubtitle");
  if (panelTitle) panelTitle.textContent = "Click a district";
  if (panelSubtitle) panelSubtitle.textContent = "";
  setChart([]);
}

/* =============================
   MAIN
============================= */

async function main() {
  STATE.map = L.map("map", { zoomSnap: 0.25 }).setView(CONFIG.center, CONFIG.zoom);

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

  // create geo layer once
  STATE.layer = L.geoJSON(geo, { style: styleFeature, onEachFeature }).addTo(STATE.map);
  try { STATE.map.fitBounds(STATE.layer.getBounds(), { padding: [10, 10] }); } catch (_) {}

  initChart();

  // build disease dropdown
  const diseaseSel = $("disease");
  if (diseaseSel) {
    diseaseSel.innerHTML = "";
    for (const d of index.diseases || []) {
      const opt = document.createElement("option");
      opt.value = d.id;
      opt.textContent = d.label || d.id;
      diseaseSel.appendChild(opt);
    }

    // optional: allow URL hash #influenza
    const fromHash = (window.location.hash || "").replace("#", "").trim();
    const initial = fromHash || STATE.diseaseId;
    diseaseSel.value = initial;

    diseaseSel.addEventListener("change", async (e) => {
      const id = e.target.value;
      window.location.hash = id;
      await loadDisease(id);
    });

    await loadDisease(initial);
  } else {
    await loadDisease(STATE.diseaseId);
  }

  // metric dropdown (THIS WAS MISSING)
  const metricSel = $("metric");
  if (metricSel) {
    metricSel.value = STATE.metric;
    metricSel.addEventListener("change", (e) => {
      STATE.metric = e.target.value;
      refreshMap();
    });
  }
}

main().catch((err) => {
  console.error(err);
  alert(
    "Failed to load map data.\n\nOpen DevTools → Console for details.\n\n" +
    String(err)
  );
});
