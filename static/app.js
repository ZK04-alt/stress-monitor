
const $ = (selector) => document.querySelector(selector);
const form = $("#projection-form");
const stateSelect = $("#state-select");
const yearInput = $("#year-input");
const loading = $("#loading-overlay");
let bootstrapData = null;

const fmt = (value, digits = 1) =>
  Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

function signed(value) {
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${fmt(value, 1)} pts vs 2024`;
}

function updateHorizon() {
  if (!bootstrapData) return;
  const years = Number(yearInput.value) - bootstrapData.latest_year;
  $("#horizon-label").textContent = `+${Math.max(1, years)} years`;
}

function renderModelTable(rows) {
  $("#model-table-body").innerHTML = rows.map(row => `
    <tr>
      <td>${row.target}</td>
      <td>${row.model}</td>
      <td>${fmt(row.mae, row.target === "SAIFI" ? 3 : 2)}</td>
      <td>${fmt(row.rmse, row.target === "SAIFI" ? 3 : 2)}</td>
      <td>${fmt(row.r2, 3)}</td>
    </tr>
  `).join("");
}

function readableFeature(name) {
  return name
    .replaceAll("_", " ")
    .replace(/\b(previous|state|year|month|service|territory)\b/g, match => match)
    .replace(/\b\w/g, c => c.toUpperCase());
}

function renderInputs(data) {
  const electricity = [...data.main_inputs.saidi.slice(0, 3), ...data.main_inputs.saifi.slice(0, 2)];
  const water = [...data.main_inputs.drought.slice(0, 3), ...data.main_inputs.compliance.slice(0, 2)];
  $("#electricity-inputs").innerHTML = electricity.map(item => `<li>${readableFeature(item)}</li>`).join("");
  $("#water-inputs").innerHTML = water.map(item => `<li>${readableFeature(item)}</li>`).join("");
}

function updateCard(prefix, metric) {
  setText(`${prefix}-score`, fmt(metric.score, 1));
  setText(`${prefix}-band`, metric.band.label);
  setText(`${prefix}-change`, signed(metric.change));
  setText(`${prefix}-range`, `${fmt(metric.range[0], 1)}–${fmt(metric.range[1], 1)}`);
  document.getElementById(`${prefix}-bar`).style.width = `${Math.max(0, Math.min(100, metric.score))}%`;
}

function renderProjection(data) {
  setText("result-state", data.state.name);
  setText("result-year", data.year);
  setText("scenario-horizon", `${String(data.years_ahead).padStart(2, "0")}Y`);
  updateCard("electricity", data.electricity);
  updateCard("water", data.water);

  setText("saidi-value", fmt(data.electricity.saidi, 1));
  setText("saifi-value", fmt(data.electricity.saifi, 3));
  setText("drought-value", fmt(data.water.drought, 1));
  setText("compliance-value", fmt(data.water.compliance, 3));
  setText("electricity-rank", `${data.rank.electricity} / ${data.rank.total}`);
  setText("water-rank", `${data.rank.water} / ${data.rank.total}`);

  [
    ["duration", data.electricity.duration_stress],
    ["frequency", data.electricity.frequency_stress],
    ["drought", data.water.drought_stress],
    ["compliance", data.water.compliance_stress],
  ].forEach(([name, value]) => {
    setText(`${name}-stress`, fmt(value, 1));
    document.getElementById(`${name}-fill`).style.width = `${Math.max(0, Math.min(100, value))}%`;
  });

  drawChart(data.series, data.latest_observed_year);
}

function svgElement(name, attrs = {}) {
  const el = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attrs).forEach(([key, value]) => el.setAttribute(key, value));
  return el;
}

function pathFrom(points, x, y) {
  const valid = points.filter(p => p.value !== null && p.value !== undefined);
  return valid.map((p, index) => `${index ? "L" : "M"} ${x(p.year)} ${y(p.value)}`).join(" ");
}

function areaPath(points, x, y, lowKey, highKey) {
  const valid = points.filter(p => p[lowKey] != null && p[highKey] != null);
  if (!valid.length) return "";
  const top = valid.map((p, i) => `${i ? "L" : "M"} ${x(p.year)} ${y(p[highKey])}`).join(" ");
  const bottom = valid.slice().reverse().map(p => `L ${x(p.year)} ${y(p[lowKey])}`).join(" ");
  return `${top} ${bottom} Z`;
}

function drawChart(series, latestYear) {
  const svg = $("#trend-chart");
  svg.innerHTML = "";
  const width = 920, height = 360;
  const pad = { left: 54, right: 20, top: 24, bottom: 42 };
  const years = series.map(d => d.year);
  const minYear = Math.max(Math.min(...years), latestYear - 10);
  const maxYear = Math.max(...years);
  const visible = series.filter(d => d.year >= minYear);
  const x = year => pad.left + ((year - minYear) / Math.max(1, maxYear - minYear)) * (width - pad.left - pad.right);
  const y = value => height - pad.bottom - (value / 100) * (height - pad.top - pad.bottom);

  [0, 25, 50, 75, 100].forEach(value => {
    svg.appendChild(svgElement("line", { x1: pad.left, y1: y(value), x2: width - pad.right, y2: y(value), class: "chart-grid" }));
    const label = svgElement("text", { x: pad.left - 12, y: y(value) + 4, "text-anchor": "end", class: "chart-axis-text" });
    label.textContent = value;
    svg.appendChild(label);
  });

  const tickStep = maxYear - minYear > 12 ? 2 : 1;
  for (let yr = minYear; yr <= maxYear; yr += tickStep) {
    const label = svgElement("text", { x: x(yr), y: height - 15, "text-anchor": "middle", class: "chart-axis-text" });
    label.textContent = yr;
    svg.appendChild(label);
  }

  const marker = svgElement("line", { x1: x(latestYear), y1: pad.top, x2: x(latestYear), y2: height - pad.bottom, class: "chart-marker-line" });
  svg.appendChild(marker);
  const markerLabel = svgElement("text", { x: x(latestYear) - 6, y: pad.top + 10, "text-anchor": "end", class: "chart-axis-text" });
  markerLabel.textContent = "observed cutoff";
  svg.appendChild(markerLabel);

  const projected = visible.filter(d => d.type === "projected");
  const observed = visible.filter(d => d.type === "observed");
  const lastObserved = observed[observed.length - 1];
  const projectedWithAnchor = lastObserved ? [lastObserved, ...projected] : projected;

  const electricityArea = areaPath(projected, x, y, "electricity_low", "electricity_high");
  const waterArea = areaPath(projected, x, y, "water_low", "water_high");
  if (electricityArea) svg.appendChild(svgElement("path", { d: electricityArea, class: "chart-range-electricity" }));
  if (waterArea) svg.appendChild(svgElement("path", { d: waterArea, class: "chart-range-water" }));

  [
    [observed.map(d => ({ year: d.year, value: d.electricity })), "chart-observed-electricity"],
    [observed.map(d => ({ year: d.year, value: d.water })), "chart-observed-water"],
    [projectedWithAnchor.map(d => ({ year: d.year, value: d.electricity })), "chart-projected-electricity"],
    [projectedWithAnchor.map(d => ({ year: d.year, value: d.water })), "chart-projected-water"],
  ].forEach(([points, className]) => {
    const d = pathFrom(points, x, y);
    if (d) svg.appendChild(svgElement("path", { d, class: className }));
  });

  visible.forEach(row => {
    [["electricity", "#FFD100"], ["water", "#5AA7AB"]].forEach(([key, colour]) => {
      if (row[key] == null) return;
      const circle = svgElement("circle", {
        cx: x(row.year), cy: y(row[key]), r: 4.5,
        fill: "#160F15", stroke: colour, "stroke-width": 1.8, class: "chart-point"
      });
      circle.addEventListener("mouseenter", event => showTooltip(event, row));
      circle.addEventListener("mouseleave", hideTooltip);
      svg.appendChild(circle);
    });
  });
}

function showTooltip(event, row) {
  const tooltip = $("#chart-tooltip");
  tooltip.hidden = false;
  tooltip.innerHTML = `
    <strong>${row.year} · ${row.type}</strong><br>
    Electricity: ${row.electricity == null ? "—" : fmt(row.electricity, 1)}<br>
    Water: ${row.water == null ? "—" : fmt(row.water, 1)}
  `;
  const wrap = $(".chart-wrap").getBoundingClientRect();
  tooltip.style.left = `${event.clientX - wrap.left + 12}px`;
  tooltip.style.top = `${event.clientY - wrap.top - 62}px`;
}
function hideTooltip() { $("#chart-tooltip").hidden = true; }

async function runProjection() {
  const state = stateSelect.value;
  const year = Number(yearInput.value);
  loading.hidden = false;
  try {
    const response = await fetch(`/api/project?state=${encodeURIComponent(state)}&year=${year}`);
    if (!response.ok) throw new Error((await response.json()).detail || "Projection failed.");
    renderProjection(await response.json());
  } catch (error) {
    alert(error.message);
  } finally {
    loading.hidden = true;
  }
}

async function init() {
  const response = await fetch("/api/bootstrap");
  if (!response.ok) throw new Error("Unable to load model registry.");
  bootstrapData = await response.json();

  stateSelect.innerHTML = bootstrapData.states.map(state =>
    `<option value="${state.abbreviation}" ${state.abbreviation === "CA" ? "selected" : ""}>${state.name} (${state.abbreviation})</option>`
  ).join("");

  yearInput.min = bootstrapData.min_year;
  yearInput.max = bootstrapData.max_year;
  yearInput.value = Math.min(2030, bootstrapData.max_year);
  setText("training-status", String(bootstrapData.training.status || "complete").toUpperCase());
  setText("latest-observation", bootstrapData.latest_year);
  $("#warning-text").textContent = bootstrapData.warning;
  renderModelTable(bootstrapData.diagnostics);
  renderInputs(bootstrapData);
  updateHorizon();
  await runProjection();
}

yearInput.addEventListener("input", updateHorizon);
form.addEventListener("submit", event => {
  event.preventDefault();
  runProjection();
});
window.addEventListener("DOMContentLoaded", () => init().catch(error => {
  document.body.innerHTML = `<main style="padding:40px;color:#F7F1F4"><h1>Model interface unavailable</h1><p>${error.message}</p></main>`;
}));
