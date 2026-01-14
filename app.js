/* global L, Chart */

const STATE = {
  metric: "incidence_7d",
  latest: null,
  timeseries: null,
  geo: null,
  layer: null,
  chart: null
};

function clamp(n, lo, hi) { return Math.max(lo, Math.min(hi, n)); }

function colorRamp(t) {
  // Simple single-hue ramp without external libs
  // t in [0,1] -> light to dark
  const x = clamp(t, 0, 1);
  const v = Math.round(245 - x * 170); // 245..75
  return `rgb(${v}, ${v}, 255)`;        // bluish
}

function getDistrictId(feature) {
  // BKG VG250 typically uses "ars" (often lowercase in GeoJSON)
  // We normalize.
  const p = feature.properties || {};
  return String(p.ars ?? p.ARS ?? p.rs ?? p.RS ?? p.ags ?? p.AGS ?? "").trim();
}

function formatNumber(n) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("de-DE", { maximumFractionDigits: 1 }).format(n);
}

function metricValueForId(id) {
  const v = STATE.latest?.values?.[id];
  if (!v) return null;
  return v[STATE.metric] ?? null;
}

function buildLegend() {
  const el = document.getElementById("legend");
  el.innerHTML = "";

  // Use quantiles from latest values for a stable legend.
  const vals = Object.values(STATE.latest.values)
    .map(o => o[STATE.metric])
    .filter(x => typeof x === "number" && isFinite(x))
    .sort((a,b) => a-b);

  if (vals.length === 0) {
    el.textContent = "No data";
    return;
  }

  const stops = 5;
  for (let i = 0; i < stops; i++) {
    const q = i / (stops - 1);
    const idx = Math.floor(q * (vals.length - 1));
    const val = vals[idx];
    const sw = document.createElement("span");
    sw.className = "swatch";
    sw.style.background = colorRamp(q);

    const lab = document.createElement("span");
    lab.textContent = `${formatNumber(val)}`;

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
  const id = getDistrictId(feature);
  const v = metricValueForId(id);

  // Normalize v to 0..1 using min/max of current metric in latest.json
  const mm = STATE.latest.metric_meta?.[STATE.metric];
  let t = 0;
  if (v !== null && mm && mm.max > mm.min) {
    t = (v - mm.min) / (mm.max - mm.min);
  }

  return {
    weight: 1,
    color: "#999",
    fillOpacity: v === null ? 0.15 : 0.75,
    fillColor: v === null ? "#eee" : colorRamp(t)
  };
}

function tooltipText(feature) {
  const p = feature.properties || {};
  const name = p.gen ?? p.GEN ?? p.name ?? p.NAME ?? "Unknown";
  const id = getDistrictId(feature);

  const v = STATE.latest?.values?.[id];
  const inc = v?.incidence_7d;
  const cases = v?.cases_7d;
  const trend = v?.trend_pct;

  return `
    <div style="font-weight:600;margin-bottom:4px;">${name}</div>
    <div style="font-size:12px;color:#444;">
      7-day incidence (0–14): <b>${formatNumber(inc)}</b><br/>
      7-day cases (0–14): <b>${formatNumber(cases)}</b><br/>
      Trend vs prev week: <b>${formatNumber(trend)}%</b><br/>
      ID: <span style="color:#666">${id || "—"}</span>
    </div>
  `;
}

function onEachFeature(feature, layer) {
  layer.bindTooltip(() => tooltipText(feature), { sticky: true });

  layer.on("click", () => {
    const p = feature.properties || {};
    const name = p.gen ?? p.GEN ?? p.name ?? p.NAME ?? "Unknown";
    const id = getDistrictId(feature);
    showPanel(name, id);
  });
}

function refreshLayerStyles() {
  STATE.layer?.setStyle(styleFeature);
  buildLegend();
}

async function loadJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`Failed to load ${url}: ${r.status}`);
  return r.json();
}

function initChart() {
  const ctx = document.getElementById("chart");
  STATE.chart = new Chart(ctx, {
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
  document.getElementById("panelTitle").textContent = name;
  const updated = STATE.latest?.updated_at ?? "unknown date";

  const v = STATE.latest?.values?.[id];
  if (!v) {
    document.getElementById("panelSubtitle").textContent = `No data. Updated: ${updated}`;
    STATE.chart.data.labels = [];
    STATE.chart.data.datasets[0].data = [];
    STATE.chart.update();
    return;
  }

  document.getElementById("panelSubtitle").textContent =
    `Updated: ${updated} • 7d incidence: ${formatNumber(v.incidence_7d)} • 7d cases: ${formatNumber(v.cases_7d)} • Trend: ${formatNumber(v.trend_pct)}%`;

  const series = STATE.timeseries?.series?.[id];
  if (!series) {
    STATE.chart.data.labels = [];
    STATE.chart.data.datasets[0].data = [];
    STATE.chart.update();
    return;
  }

  STATE.chart.data.labels = series.map(pt => pt.date);
  STATE.chart.data.datasets[0].data = series.map(pt => pt.incidence_7d);
  STATE.chart.update();
}

async function main() {
  const map = L.map("map", { zoomSnap: 0.25 }).setView([51.1, 10.4], 6);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 10,
    attribution: '&copy; OpenStreetMap contributors'
  }).addTo(map);

  // Load latest values + timeseries + boundaries
  const [latest, timeseries, geo] = await Promise.all([
    loadJson("data/latest.json"),
    loadJson("data/timeseries.json"),
    loadJson("data/landkreise.geojson")
  ]);

  STATE.latest = latest;
  STATE.timeseries = timeseries;
  STATE.geo = geo;

  const updatedAt = document.getElementById("updatedAt");
  updatedAt.textContent = latest.updated_at ? `Updated: ${latest.updated_at}` : "";

  // Create layer
  STATE.layer = L.geoJSON(geo, {
    style: styleFeature,
    onEachFeature
  }).addTo(map);

  initChart();
  buildLegend();

  // Metric dropdown
  document.getElementById("metric").addEventListener("change", (e) => {
    STATE.metric = e.target.value;
    refreshLayerStyles();
  });

  // Fit Germany bounds
  try {
    map.fitBounds(STATE.layer.getBounds(), { padding: [10, 10] });
  } catch (_) {}
}

main().catch(err => {
  console.error(err);
  alert("Failed to load data. Check console for details.");
});