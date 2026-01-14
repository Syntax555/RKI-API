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
  resolution: "landkreis", // "landkreis" | "bundesland"
  metric: "incidence_7d",

  diseaseIndex: null,
  latest: null,
  timeseries: null,
  geo: null,

  map: null,
  layer: null,
  chart: null
};

const $ = (id) => document.getElementById(id);

function clamp(n, lo, hi) {
  return n < lo ? lo : (n > hi ? hi : n);
}

function formatNumber(n, digits = 1) {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(n);
}

function normalizeDistrictKey(raw) {
  if (raw === null || raw === undefined) return "";
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
  const raw = p.ars ?? p.ARS ?? p.rs ?? p.RS ?? p.ags ?? p.AGS ?? p.krs ?? p.KRS ?? "";
  return normalizeDistrictKey(raw);
}

function getBundeslandKeyFromFeature(feature) {
  const lk = getDistrictKey(feature);
  return lk ? `STATE:${lk.slice(0, 2)}` : "";
}

function mapKeyForFeature(feature) {
  return (STATE.resolution === "bundesland")
    ? getBundeslandKeyFromFeature(feature)
    : getDistrictKey(feature);
}

function colorRamp(t) {
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170); // 245..75
  return `rgb(${v},${v},255)`;
}

async function loadJson(relPath) {
  const url = new URL(relPath, window.location.href);
  const r = await fetch(url, { cache: "no-store" });

  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`Failed to load ${url} (${r.status}). Body: ${body.slice(0, 160)}`);
  }

  const text = await r.text();
  if (!text || text.trim().length < 2) throw new Error(`Empty response from ${url}`);

  return JSON.parse(text);
}

function latestForKey(key) {
  return STATE.latest?.values?.[key] ?? null;
}

function metricValueForKey(key) {
  const v = latestForKey(key);
  if (!v) return null;
  const x = v[STATE.metric];
  return (typeof x === "number" && Number.isFinite(x)) ? x : null;
}

function computeMetaMinMax(values, metric) {
  let min = Infinity, max = -Infinity;
  for (const k in values) {
    const x = values[k]?.[metric];
    if (typeof x === "number" && Number.isFinite(x)) {
      if (x < min) min = x;
      if (x > max) max = x;
    }
  }
  if (!Number.isFinite(min) || !Number.isFinite(max) || min === max) return { min: 0, max: 1 };
  return { min, max };
}

function buildLegend() {
  const el = $("legend");
  if (!el) return;
  el.innerHTML = "";

  const values = STATE.latest?.values || {};
  const meta = STATE.latest?.metric_meta?.[STATE.metric] || computeMetaMinMax(values, STATE.metric);

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
  const key = mapKeyForFeature(feature);
  const v = metricValueForKey(key);

  const values = STATE.latest?.values || {};
  const meta = STATE.latest?.metric_meta?.[STATE.metric] || computeMetaMinMax(values, STATE.metric);

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
  const district = getDistrictName(feature);
  const mapKey = mapKeyForFeature(feature);
  const v = latestForKey(mapKey);

  const inc = v?.incidence_7d ?? null;
  const cases = v?.cases_7d ?? null;
  const trend = v?.trend_pct ?? null;

  const resInfo = (STATE.resolution === "bundesland")
    ? `Bundesland key: <span style="color:#666">${mapKey}</span>`
    : `Landkreis key: <span style="color:#666">${mapKey}</span>`;

  return `
    <div style="font-weight:600;margin-bottom:4px;">${district}</div>
    <div style="font-size:12px;color:#444;">
      Disease: <b>${STATE.diseaseLabel || STATE.diseaseId}</b><br/>
      Resolution: <b>${STATE.resolution}</b> (${resInfo})<br/>
      Incidence: <b>${formatNumber(inc, 1)}</b><br/>
      Cases (7d): <b>${formatNumber(cases, 0)}</b><br/>
      Trend: <b>${formatNumber(trend, 1)}%</b>
    </div>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipHtml(feature), { sticky: true });
  layer.on("click", () => {
    const district = getDistrictName(feature);
    const key = mapKeyForFeature(feature);
    showPanel(district, key);
  });
}

function initChart() {
  const canvas = $("chart");
  if (!canvas) return;

  STATE.chart = new Chart(canvas, {
    type: "line",
    data: {
      labels: [],
      datasets: [{
        label: "Incidence",
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

function showPanel(title, key) {
  $("panelTitle").textContent = title;

  const updated = STATE.latest?.updated_at ?? "unknown";
  const v = latestForKey(key);

  if (!v) {
    $("panelSubtitle").textContent = `No data. Updated: ${updated} • Key: ${key || "—"}`;
    if (STATE.chart) {
      STATE.chart.data.labels = [];
      STATE.chart.data.datasets[0].data = [];
      STATE.chart.update();
    }
    return;
  }

  $("panelSubtitle").textContent =
    `${STATE.diseaseLabel || STATE.diseaseId} • Updated: ${updated} • Key: ${key} • ` +
    `Inc: ${formatNumber(v.incidence_7d, 1)} • Cases: ${formatNumber(v.cases_7d, 0)} • Trend: ${formatNumber(v.trend_pct, 1)}%`;

  // chart
  const series = STATE.timeseries?.series?.[key];
  if (!series || !STATE.chart) return;

  STATE.chart.data.labels = series.map(pt => pt.date);
  STATE.chart.data.datasets[0].data = series.map(pt => pt.incidence_7d);
  STATE.chart.data.datasets[0].label =
    `${STATE.diseaseLabel || STATE.diseaseId} • ${STATE.metric}`;
  STATE.chart.update();
}

function updateHeader() {
  $("diseaseLabel").textContent =
    `Disease: ${STATE.diseaseLabel || STATE.diseaseId} • Resolution: ${STATE.resolution}`;
  $("updatedAt").textContent =
    STATE.latest?.updated_at ? ` • Updated: ${STATE.latest.updated_at}` : "";
}

async function loadDisease(diseaseId) {
  const d = STATE.diseaseIndex?.diseases?.find(x => x.id === diseaseId);
  if (!d) throw new Error(`Unknown diseaseId: ${diseaseId}`);

  STATE.diseaseId = diseaseId;
  STATE.diseaseLabel = d.label || diseaseId;

  const base = `data/diseases/${diseaseId}`;
  const [latest, timeseries] = await Promise.all([
    loadJson(`${base}/latest.json`),
    loadJson(`${base}/timeseries.json`)
  ]);

  STATE.latest = latest;
  STATE.timeseries = timeseries;
  STATE.resolution = latest?.resolution || d.resolution || "landkreis";

  // ensure meta exists
  if (!STATE.latest.metric_meta) STATE.latest.metric_meta = {};
  for (const m of ["incidence_7d", "cases_7d", "trend_pct"]) {
    if (!STATE.latest.metric_meta[m]) {
      STATE.latest.metric_meta[m] = computeMetaMinMax(STATE.latest.values || {}, m);
    }
  }

  updateHeader();
  if (STATE.layer) STATE.layer.setStyle(styleFeature);
  buildLegend();

  // reset panel prompt
  $("panelTitle").textContent = "Click a district";
  $("panelSubtitle").textContent = "";
  if (STATE.chart) {
    STATE.chart.data.labels = [];
    STATE.chart.data.datasets[0].data = [];
    STATE.chart.update();
  }
}

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

  STATE.layer = L.geoJSON(geo, { style: styleFeature, onEachFeature }).addTo(STATE.map);
  try { STATE.map.fitBounds(STATE.layer.getBounds(), { padding: [10, 10] }); } catch (_) {}

  initChart();

  // disease dropdown
  const diseaseSel = $("disease");
  diseaseSel.innerHTML = "";
  for (const d of index.diseases || []) {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = d.label || d.id;
    diseaseSel.appendChild(opt);
  }

  // metric dropdown
  const metricSel = $("metric");
  metricSel.value = STATE.metric;
  metricSel.addEventListener("change", (e) => {
    STATE.metric = e.target.value;
    if (STATE.layer) STATE.layer.setStyle(styleFeature);
    buildLegend();
  });

  const fromHash = (window.location.hash || "").replace("#", "").trim();
  const initial = fromHash || STATE.diseaseId;
  diseaseSel.value = initial;

  await loadDisease(initial);

  diseaseSel.addEventListener("change", async (e) => {
    const id = e.target.value;
    window.location.hash = id;
    await loadDisease(id);
  });
}

main().catch((err) => {
  console.error(err);
  alert(
    "Failed to load map data.\n\nOpen DevTools → Console to see details.\n\n" +
    String(err)
  );
});
