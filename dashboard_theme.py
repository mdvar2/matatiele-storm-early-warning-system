"""Visual theme for the research dashboard: sky background, cards, icons and status chips.

Presentation only. Nothing here reads files, calls a service, changes a forecast or
model value, or sends anything. Icons are chosen only from genuine ECMWF forecast
values (precipitation, cloud cover) and the forecast input hour; they describe the
forecast, never an observation.

Light and dark palettes follow the viewer's system preference (prefers-color-scheme),
which is also Streamlit's default theme. Motion is disabled for prefers-reduced-motion.
"""
import base64
import html
import math

# Soft cloud bank tiled across the sky. Small inline vector: no image download.
_CLOUDS_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="360" viewBox="0 0 1200 360">'
    '<defs><filter id="b" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="9"/></filter></defs>'
    '<g fill="#ffffff" filter="url(#b)">'
    '<ellipse cx="150" cy="120" rx="120" ry="34" opacity=".55"/><ellipse cx="210" cy="100" rx="70" ry="38" opacity=".6"/>'
    '<ellipse cx="560" cy="70" rx="150" ry="30" opacity=".45"/><ellipse cx="620" cy="52" rx="80" ry="34" opacity=".5"/>'
    '<ellipse cx="960" cy="150" rx="140" ry="32" opacity=".5"/><ellipse cx="1010" cy="128" rx="75" ry="36" opacity=".55"/>'
    '<ellipse cx="380" cy="260" rx="160" ry="28" opacity=".35"/><ellipse cx="860" cy="300" rx="170" ry="26" opacity=".3"/>'
    '</g></svg>')
CLOUDS_URI = 'data:image/svg+xml;base64,' + base64.b64encode(_CLOUDS_SVG.encode('utf-8')).decode('ascii')

CSS = r"""
:root {
  --font: "Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,"Helvetica Neue",Roboto,Arial,sans-serif;
  --sky-top:#7cc4f2; --sky-mid:#b9e2fb; --sky-bottom:#eef8ff; --cloud-opacity:.95; --star-opacity:0;
  --card:rgba(255,255,255,.90); --card-solid:#ffffff; --card-border:rgba(18,78,140,.14);
  --card-shadow:0 10px 28px rgba(16,64,118,.13),0 2px 6px rgba(16,64,118,.06);
  --text:#0d2540; --muted:#3c5877; --heading:#072a52; --accent:#0a6fd6; --accent-soft:#e3f1ff;
  --chip:#ffffffd9; --chip-text:#0d2b4f; --divider:#d6e6f5;
  --sidebar:linear-gradient(170deg,#103152 0%,#0b2440 55%,#081a30 100%); --sidebar-text:#dce9f8; --sidebar-muted:#a9c0da;
  --input-bg:#ffffff; --input-text:#0d2540;
  --good:#0d8a4c; --warn:#a85f00; --bad:#d4283e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --sky-top:#050f22; --sky-mid:#0b1d3a; --sky-bottom:#13294b; --cloud-opacity:.16; --star-opacity:.75;
    --card:rgba(16,30,52,.90); --card-solid:#132540; --card-border:rgba(132,176,228,.22);
    --card-shadow:0 12px 30px rgba(0,0,0,.40),0 2px 6px rgba(0,0,0,.25);
    --text:#e7f0fb; --muted:#a9c0da; --heading:#f3f8fe; --accent:#64b5ff; --accent-soft:#16365a;
    --chip:#13284699; --chip-text:#e7f0fb; --divider:#2a4467;
    --input-bg:#1b304d; --input-text:#e7f0fb;
    --good:#4fd18b; --warn:#ffbf5a; --bad:#ff7085;
  }
}

/* Sky: gradient plus a drifting cloud layer; night sky with faint stars in dark mode. */
.stApp {font-family:var(--font);color:var(--text);isolation:isolate;
  background:linear-gradient(180deg,var(--sky-top) 0%,var(--sky-mid) 38%,var(--sky-bottom) 100%) fixed!important}
.stApp::before {content:"";position:fixed;top:0;left:0;width:200%;height:58vh;pointer-events:none;
  background:url("CLOUDS_URI") repeat-x 0 0/1200px 360px;opacity:var(--cloud-opacity);animation:drift 240s linear infinite;z-index:-1}
.stApp::after {content:"";position:fixed;inset:0;pointer-events:none;z-index:-1;opacity:var(--star-opacity);
  background-image:radial-gradient(1.4px 1.4px at 12% 18%,#fff 50%,transparent 51%),radial-gradient(1.2px 1.2px at 32% 9%,#fff 50%,transparent 51%),
  radial-gradient(1.6px 1.6px at 58% 14%,#fff 50%,transparent 51%),radial-gradient(1.1px 1.1px at 77% 6%,#fff 50%,transparent 51%),
  radial-gradient(1.3px 1.3px at 88% 22%,#fff 50%,transparent 51%),radial-gradient(1.2px 1.2px at 45% 27%,#fff 50%,transparent 51%),
  radial-gradient(1px 1px at 22% 33%,#fff 50%,transparent 51%),radial-gradient(1.3px 1.3px at 68% 31%,#fff 50%,transparent 51%)}
@keyframes drift {from{transform:translateX(0)}to{transform:translateX(-1200px)}}
[data-testid="stAppViewContainer"],[data-testid="stMain"],[data-testid="stHeader"] {background:transparent!important}
[data-testid="stHeader"] {backdrop-filter:blur(6px)}
[data-testid="stMainBlockContainer"] {max-width:1720px;padding:4.5rem 1.25rem 1.5rem}
[data-testid="stVerticalBlock"] {gap:.85rem}
[data-testid="stMain"] [data-testid="stMarkdownContainer"],[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3,[data-testid="stMain"] h4 {color:var(--text)}
[data-testid="stMain"] h4 {font-weight:750;letter-spacing:-.3px;color:var(--heading)}
[data-testid="stMain"] [data-testid="stCaptionContainer"] * {color:var(--muted)!important}

/* Sidebar */
[data-testid="stSidebar"] {background:var(--sidebar);min-width:255px;max-width:275px}
[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {padding:0}
[data-testid="stSidebarHeader"],[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"] {color:var(--sidebar-text)}
[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {color:var(--heading)}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * {color:var(--sidebar-text)!important}
[data-testid="stSidebar"] input {background:#ffffff;color:#0d2540}
[data-testid="stSidebar"] [data-testid="stButton"] button {background:transparent;border:0;color:var(--sidebar-text);min-height:46px;
  justify-content:flex-start;text-align:left;border-radius:12px;padding:10px 14px;transition:background-color .18s ease,transform .18s ease}
[data-testid="stSidebar"] [data-testid="stButton"] button p {font-size:14.5px;font-weight:500}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {background:#ffffff14;transform:translateX(2px)}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {background:linear-gradient(110deg,#0a74e0,#1b8ff0);box-shadow:0 6px 16px #04122a55}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] p {font-weight:700;color:#fff}
[data-testid="stSidebar"] button:focus-visible {outline:3px solid #ffd23f;outline-offset:2px}
[data-testid="stSidebar"] [data-testid="stExpander"] {background:#ffffff0d;border:1px solid #ffffff24;border-radius:12px;margin-top:16px}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {background:transparent!important;color:var(--sidebar-text)!important}
[data-testid="stSidebar"] [data-testid="stAlert"] {background:#eef6ff!important;border-radius:9px}
[data-testid="stSidebar"] [data-testid="stAlert"] p {color:#173452!important}
.brand {display:flex;gap:10px;align-items:center;margin:4px 0 22px}.brand img {width:48px;height:48px}
.brand strong {display:block;font-size:27px;color:#fff;letter-spacing:-1px}.brand span {display:block;color:#e0eaf8;font-size:14px;margin-top:3px}
.brand small {color:#8fd0ff;font-size:11px;letter-spacing:.3px}
.sidebar-note {color:var(--sidebar-muted);font-size:13px;line-height:1.8;border-top:1px solid #ffffff1f;padding:20px 4px;margin-top:40px}
.sidebar-note a {color:#8fd0ff}

/* Mobile section navigation (sidebar is hidden behind a menu on small screens). */
.st-key-mobile_nav {display:none}
@media (max-width:900px) {.st-key-mobile_nav {display:block}}
.st-key-mobile_nav [data-testid="stButtonGroup"] {width:100%}
.st-key-mobile_nav [role="radiogroup"],.st-key-mobile_nav [data-testid="stButtonGroup"] > div {display:flex;flex-wrap:wrap;gap:6px}
.st-key-mobile_nav button {border-radius:999px!important;min-height:40px;background:var(--chip)!important;color:var(--chip-text)!important;border:1px solid var(--card-border)!important}
.st-key-mobile_nav button[aria-checked="true"],.st-key-mobile_nav button[kind*="Active"] {background:#0a6fd6!important;color:#fff!important;border-color:#0a6fd6!important}

/* Hero */
.hero {display:flex;justify-content:space-between;align-items:center;gap:18px;margin:0 0 6px}
.hero-main {display:flex;gap:14px;align-items:center;min-width:0}.hero-main>div {min-width:0}
.hero-main>img {width:54px;height:54px;flex-shrink:0;filter:drop-shadow(0 4px 10px #0a3d7a33)}
.hero h1 {font-size:clamp(21px,2vw,31px);font-weight:800;letter-spacing:-.8px;color:var(--heading);line-height:1.18;margin:0;overflow-wrap:break-word}
.hero p {font-size:14.5px;font-weight:500;color:var(--heading);margin:6px 0 0}
.clock-card {flex-shrink:0;background:linear-gradient(120deg,#0756b8,#0a78de);color:#fff;border-radius:16px;padding:12px 18px;text-align:center;
  font-size:12.5px;box-shadow:0 8px 20px #06386e33}
.clock-card small {display:block;color:#cfe4fb;margin-top:6px}
.status-strip {display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 4px}
.chip {display:inline-flex;align-items:center;gap:7px;background:var(--chip);color:var(--chip-text);border:1px solid var(--card-border);
  border-radius:999px;padding:6px 12px;font-size:12.5px;backdrop-filter:blur(6px)}
.chip b {font-weight:700}
.chip .dot {width:9px;height:9px;border-radius:50%;background:var(--good);box-shadow:0 0 0 0 #16a34a80;animation:pulse 2.4s ease-out infinite}
.chip.stale .dot {background:var(--warn);animation:none}
.chip.sim {background:#4a0f6b;color:#fff;border-color:#ffd23f}
@keyframes pulse {0%{box-shadow:0 0 0 0 #16a34a80}70%{box-shadow:0 0 0 9px #16a34a00}100%{box-shadow:0 0 0 0 #16a34a00}}

/* Cards */
.st-key-map_card,.st-key-weather_card,.st-key-risk_card,.st-key-six_card,.st-key-sample_card,.st-key-predictions_card,.st-key-live_six_card {
  background:var(--card)!important;border:1px solid var(--card-border)!important;border-radius:18px!important;
  box-shadow:var(--card-shadow);backdrop-filter:blur(8px);overflow:hidden}
.st-key-map_card {padding:0!important}
.panel-heading {display:flex;align-items:center;gap:10px;font-size:16px;font-weight:750;color:var(--heading);margin:0 0 9px;line-height:1.4}
.panel-heading img {width:22px;height:22px;flex-shrink:0}
.map-heading {background:linear-gradient(110deg,#0f2f52,#123d68);color:#fff;padding:12px 16px;margin:0;border-radius:17px 17px 0 0}
.section-title {display:flex;align-items:center;gap:10px;margin:14px 0 2px;font-size:18px;font-weight:800;letter-spacing:-.3px;color:var(--heading)}
.section-title small {font-size:12px;font-weight:600;color:var(--muted);letter-spacing:0}
.kpi {display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--card-border);border-left:5px solid var(--accent-c,var(--accent));
  border-radius:16px;padding:14px 12px;min-height:101px;box-shadow:var(--card-shadow)}
.kpi-icon {background:var(--accent-c,var(--accent));color:#fff;width:44px;height:44px;display:flex;align-items:center;justify-content:center;border-radius:50%;flex-shrink:0}
.kpi-icon img {width:27px;height:27px;filter:brightness(0) invert(1)}
.kpi .label {font-size:12px;color:var(--muted);line-height:1.4}
.kpi .value {font-weight:800;font-size:24px;color:var(--heading);line-height:1.25;margin:3px 0}
.kpi .sub {font-size:11.5px;color:var(--muted);line-height:1.4}.kpi.compact .value {font-size:19px}
[data-testid="stDeckGlJsonChart"] {border-radius:12px;overflow:hidden}
.map-source {font-size:11px;color:var(--muted);line-height:1.5;margin:5px 0}
.map-legend {background:var(--card-solid);border:1px solid var(--card-border);border-radius:12px;padding:10px 12px;margin:8px 0 2px}
.map-legend .title {font-size:12px;font-weight:700;color:var(--heading);margin-bottom:6px}
.rain-legend {height:11px;border-radius:6px;background:linear-gradient(90deg,#e5edf5 0%,#378cee 14.286%,#1978ea 28.571%,#1eb4b6 42.857%,#32be5a 57.143%,#f9d732 71.429%,#fa7320 85.714%,#cd2a3e 100%)}
.legend-labels {display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:4px}
.map-legend .note {font-size:11px;color:var(--muted);margin-top:6px}

/* Forecast weather card */
.weather-body {display:grid;grid-template-columns:1fr 1.15fr;gap:16px;align-items:center;min-height:130px}
.weather-primary {border-right:1px solid var(--divider);padding-right:12px}
.weather-primary img {width:76px;height:76px}
.temperature {font-size:clamp(28px,2.7vw,42px);font-weight:800;color:var(--heading);letter-spacing:-1px;white-space:nowrap}
.condition {font-size:13px;font-weight:650;color:var(--text);margin-top:4px}.condition small {display:block;font-weight:400;color:var(--muted)}
.weather-detail {display:flex;justify-content:space-between;gap:6px;align-items:center;margin:9px 0;font-size:12.5px;color:var(--muted)}
.weather-detail strong {color:var(--heading);white-space:nowrap}
.weather-status {font-size:10.5px;color:var(--muted);margin-top:8px}

/* Next-hour gauge (value as HTML text so it follows the theme) */
.risk-body {display:grid;grid-template-columns:1.05fr 1fr;align-items:center;gap:8px}
.risk-gauge {text-align:center;position:relative}.risk-gauge img {width:100%;height:auto;max-width:240px}
.gauge-value {position:absolute;left:0;right:0;top:26%;text-align:center;font-size:28px;font-weight:800;line-height:1.1;color:var(--heading)}
.gauge-label {position:absolute;left:0;right:0;top:47%;text-align:center;font-size:12px;color:var(--muted)}
.risk-badge {border-radius:8px;padding:7px 10px;display:block;font-size:11px;font-weight:800;background:var(--tint);color:var(--accent)}
.risk-key {font-size:11.5px;color:var(--text);display:flex;align-items:center;gap:8px;margin:13px 0}
.risk-key i {width:12px;height:12px;border-radius:4px;display:inline-block;flex-shrink:0}
.risk-status {font-size:10.5px;font-weight:700;color:var(--muted);margin-bottom:6px;letter-spacing:.3px}

/* Tables and research cards */
.prediction-table {width:100%;border-collapse:separate;border-spacing:0;font-size:11.5px;color:var(--text)}
.prediction-table th {background:var(--accent-soft);font-weight:650;padding:10px 7px;text-align:left;border-bottom:1px solid var(--divider);white-space:nowrap}
.prediction-table td {padding:9px 7px;border-bottom:1px solid var(--divider);white-space:nowrap}
.table-badge {font-size:9.5px;font-weight:750;border-radius:6px;padding:4px 7px;display:inline-block}
.table-note {font-size:10.5px;color:var(--muted);margin-top:9px}
.research-card {background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:20px;color:var(--text);margin-bottom:12px;line-height:1.6;box-shadow:var(--card-shadow)}
.research-card .label {color:var(--muted);font-size:12px;margin-bottom:8px}
.research-card .value {color:var(--heading);font-size:23px;font-weight:750;line-height:1.35;overflow-wrap:anywhere}
.research-card .detail {color:var(--muted);font-size:12px;margin-top:8px}
.research-notice {background:#fff5dc;border:1px solid #e5ca83;border-left:5px solid #a46605;border-radius:12px;padding:18px;color:#65430c;line-height:1.6}

/* Resident status banner */
.resident-card {position:relative;border-radius:22px;padding:22px 24px 20px 92px;border:1px solid var(--r-border);background:var(--r-bg);
  color:#102544;line-height:1.55;box-shadow:var(--card-shadow);overflow:hidden}
.resident-card::before {content:var(--r-icon);position:absolute;left:22px;top:22px;width:52px;height:52px;border-radius:16px;display:grid;place-items:center;
  font-size:28px;font-weight:800;color:var(--r-border);background:var(--r-badge);box-shadow:0 6px 14px #00000022}
.resident-card.tone-green {--r-border:#36a46b;--r-bg:linear-gradient(120deg,#effcf4,#e3f6ff);--r-badge:#d7f5e3;--r-icon:"\2714"}
.resident-card.tone-amber {--r-border:#d98b16;--r-bg:linear-gradient(120deg,#fff8e8,#fff1d6);--r-badge:#ffe8b8;--r-icon:"\26A0"}
.resident-card.tone-red {--r-border:#d93449;--r-bg:linear-gradient(120deg,#fff0f1,#ffe4e8);--r-badge:#ffd2d9;--r-icon:"\26C8\FE0F"}
.resident-card.tone-gray {--r-border:#8a9bb0;--r-bg:linear-gradient(120deg,#f4f7fa,#e9eef4);--r-badge:#dfe6ee;--r-icon:"\2753"}
.resident-card.tone-off {--r-border:#8a9bb0;--r-bg:linear-gradient(120deg,#f4f7fa,#e9eef4);--r-badge:#dfe6ee;--r-icon:"\1F515"}
.resident-head {font-size:clamp(20px,2.3vw,30px);font-weight:800;letter-spacing:-.6px;color:#0b2747}
.resident-text {font-size:16px;margin:8px 0 14px;color:#1d3a5c}
.resident-facts {display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}
.resident-facts span {background:#ffffffc4;border:1px solid #ffffff;border-radius:12px;padding:9px 12px;font-size:13px;color:#1d3a5c}
.resident-facts b {display:block;font-size:11px;text-transform:uppercase;letter-spacing:.5px;color:#4b6584}
.resident-note {font-size:12px;color:#4b6584;margin-top:12px}
.resident-sim {background:#7a1fa2;color:#fff;font-weight:800;letter-spacing:.6px;border-radius:8px;padding:7px 11px;margin-bottom:12px;display:inline-block}
.resident-guidance {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:16px 20px;color:var(--text);line-height:1.55;box-shadow:var(--card-shadow)}
.resident-guidance ul {margin:8px 0 0 18px;padding:0}.resident-guidance li {margin:6px 0;font-size:14px}
.resident-guidance .resident-note {color:var(--muted)}
.resident-action {font-size:18px;font-weight:800;color:var(--heading)}

/* Native Streamlit elements in the main area */
[data-testid="stMain"] [data-testid="stAlert"] {background:var(--card-solid);border:1px solid var(--card-border);color:var(--text);border-radius:12px}
[data-testid="stMain"] [data-testid="stAlert"] p {color:var(--text)!important}
[data-testid="stMain"] [data-testid="stExpander"] {background:var(--card);border:1px solid var(--card-border);border-radius:14px}
[data-testid="stMain"] [data-testid="stExpander"] details,[data-testid="stMain"] [data-testid="stExpander"] summary {background:transparent!important;color:var(--text)!important}
[data-testid="stMain"] [data-testid="stDataFrame"] {border:1px solid var(--card-border);border-radius:12px}
[data-testid="stMain"] [data-testid="stMetric"] {background:var(--card);border:1px solid var(--card-border);border-radius:14px;padding:18px}
[data-testid="stMain"] button:focus-visible {outline:3px solid #ffb703;outline-offset:2px}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[role="radio"] {background:var(--card-solid);color:var(--text);border-color:var(--card-border)}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"] {background:#0a6fd6!important;border-color:#0a6fd6!important}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[role="radio"][aria-checked="true"] p {color:#fff!important;font-weight:650}
[data-testid="stMain"] [data-testid="stCheckbox"] label[data-selected="true"] > div:not([data-testid]) {background:#0a6fd6!important}

@media (prefers-color-scheme: dark) {
  .resident-card.tone-green {--r-border:#3fbf7f;--r-bg:linear-gradient(120deg,#0f3326,#10304a);--r-badge:#1d4a38}
  .resident-card.tone-amber {--r-border:#e0a03a;--r-bg:linear-gradient(120deg,#3a2a0c,#33260f);--r-badge:#5a4113}
  .resident-card.tone-red {--r-border:#ff6b80;--r-bg:linear-gradient(120deg,#43121c,#3a1020);--r-badge:#6a1d2c}
  .resident-card.tone-gray {--r-border:#8aa0bb;--r-bg:linear-gradient(120deg,#1c2a3d,#18263a);--r-badge:#2b3d55}
  .resident-card.tone-off {--r-border:#8aa0bb;--r-bg:linear-gradient(120deg,#1c2a3d,#18263a);--r-badge:#2b3d55}
  .resident-head {color:#f4f8fd}.resident-text {color:#dbe7f5}
  .resident-facts span {background:#ffffff12;border-color:#ffffff1f;color:#e3edf9}.resident-facts b,.resident-note {color:#b5c8de}
  .research-notice {background:#3d3216;color:#fff1c8;border-color:#b78e34}
  .clock-card {background:linear-gradient(120deg,#0b3f80,#0d5bb0)}
}
@media (prefers-reduced-motion: reduce) {
  .stApp::before,.chip .dot,.weather-anim * {animation:none!important}
  [data-testid="stSidebar"] [data-testid="stButton"] button {transition:none}
}
@media(max-width:1100px) {.hero {align-items:flex-start}.clock-card {padding:10px}.kpi {gap:7px;padding:12px 8px}.kpi-icon {width:34px;height:34px}
  .kpi .value {font-size:20px}.weather-body {gap:8px}.temperature {font-size:30px}}
@media(max-width:900px) {[data-testid="stHorizontalBlock"] {flex-wrap:wrap}
  [data-testid="stHorizontalBlock"]>[data-testid="stColumn"] {min-width:min(100%,280px);flex:1 1 280px}
  .hero {flex-wrap:wrap}.clock-card {width:100%;box-sizing:border-box;text-align:left}.clock-card small {display:inline;margin-left:12px}
  .weather-body,.risk-body {grid-template-columns:1fr 1fr}}
@media(max-width:640px) {[data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .kpi)>[data-testid="stColumn"] {min-width:0;flex:1 1 calc(50% - 12px)}
  [data-testid="stMainBlockContainer"] {padding:4.5rem .85rem 1rem}.hero h1 {font-size:22px}.hero-main>img {width:38px;height:38px}.hero p {font-size:12.5px}
  .resident-card {padding:84px 16px 16px}.resident-card::before {left:16px;top:16px}.kpi {min-height:90px}.prediction-table {font-size:10.5px}
  .weather-body,.risk-body {grid-template-columns:1fr}.weather-primary {border-right:0;border-bottom:1px solid var(--divider);padding:0 0 10px}}
""".replace('CLOUDS_URI', CLOUDS_URI)


# Animated weather icons (CSS animation inside an SVG image: no scripts, no downloads).
_ICON_STYLE = ('<style>.sun{transform-box:fill-box;transform-origin:center;animation:s 18s linear infinite}'
               '.drift{animation:d 6s ease-in-out infinite alternate}.drop{animation:r 1.2s linear infinite}'
               '.moon{transform-box:fill-box;transform-origin:center;animation:m 7s ease-in-out infinite alternate}'
               '@keyframes s{to{transform:rotate(360deg)}}@keyframes d{to{transform:translateX(3px)}}'
               '@keyframes r{0%{transform:translateY(-3px);opacity:0}30%{opacity:1}100%{transform:translateY(7px);opacity:0}}'
               '@keyframes m{from{transform:rotate(-6deg)}to{transform:rotate(6deg)}}'
               '@media (prefers-reduced-motion:reduce){*{animation:none!important}}</style>')
_RAYS = ''.join(f'<line x1="{32 + 16 * math.cos(a):.1f}" y1="{32 + 16 * math.sin(a):.1f}" '
                f'x2="{32 + 23 * math.cos(a):.1f}" y2="{32 + 23 * math.sin(a):.1f}"/>'
                for a in (i * math.pi / 4 for i in range(8)))
_SUN = (f'<g class="sun"><g stroke="#FDB813" stroke-width="3.5" stroke-linecap="round">{_RAYS}</g>'
        '<circle cx="32" cy="32" r="11" fill="#FDB813"/></g>')
_MOON = '<path class="moon" d="M38 10a22 22 0 1 0 16 36A18 18 0 0 1 38 10z" fill="#F4E3A1"/>'
_CLOUD = ('<g class="drift"><path d="M17 52h30a11 11 0 0 0 1-22 15 15 0 0 0-29-3 11 11 0 0 0-2 25z" '
          'fill="{fill}" stroke="#8aa0bd" stroke-width="1.6"/></g>')
_DROPS = ''.join(f'<line class="drop" style="animation-delay:-{d}s" x1="{x}" y1="54" x2="{x - 3}" y2="61" '
                 'stroke="#2f8cff" stroke-width="3" stroke-linecap="round"/>' for x, d in ((24, 0), (33, .4), (42, .8)))
_ICONS = {
    'clear-day': _SUN,
    'clear-night': _MOON,
    'partly-day': '<g transform="translate(8 -6) scale(.8)">' + _SUN + '</g>' + _CLOUD.format(fill='#ffffff'),
    'partly-night': '<g transform="translate(10 -6) scale(.75)">' + _MOON + '</g>' + _CLOUD.format(fill='#e9f0f8'),
    'cloud': '<g transform="translate(6 -8) scale(.8)">' + _CLOUD.format(fill='#d7e2ee') + '</g>' + _CLOUD.format(fill='#f4f8fc'),
    'rain': '<g transform="translate(0 -8)">' + _CLOUD.format(fill='#dfe8f2') + '</g>' + _DROPS,
    'unknown': _CLOUD.format(fill='#e6edf5'),
}


def weather_icon_svg(kind):
    body = _ICONS.get(kind, _ICONS['unknown'])
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" class="weather-anim">'
            + _ICON_STYLE + body + '</svg>')


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def weather_condition(precipitation_mm, cloud_cover_percent, local_hour):
    """(icon kind, plain label) derived only from genuine forecast values; never an observation.

    Rain: >= 0.1 mm in the hour. Cloud: >= 70 % mostly cloudy, >= 30 % partly cloudy.
    Day/night icon variant: 06:00-17:59 SAST is shown as day (approximate; icon only).
    """
    rain, cloud = _finite(precipitation_mm), _finite(cloud_cover_percent)
    if rain is None and cloud is None:
        return 'unknown', 'Forecast conditions unavailable'
    night = local_hour is not None and not 6 <= int(local_hour) < 18
    if rain is not None and rain >= 0.1:
        return 'rain', 'Rain forecast'
    if cloud is not None and cloud >= 70:
        return 'cloud', 'Mostly cloudy (forecast)'
    if cloud is not None and cloud >= 30:
        return ('partly-night' if night else 'partly-day'), 'Partly cloudy (forecast)'
    if cloud is None:
        return 'unknown', 'No rain forecast'
    return ('clear-night' if night else 'clear-day'), 'Clear (forecast)'


def status_strip(stale, updated, simulated, refresh_minutes=15):
    """Chips for data freshness and mode. `updated` is a preformatted SAST time or None."""
    e = html.escape
    if stale:
        fresh = f'<span class="chip stale"><span class="dot"></span><b>Outdated data</b> &middot; last update {e(updated or "unknown")}</span>'
    else:
        fresh = f'<span class="chip"><span class="dot"></span><b>Live forecast</b> &middot; updated {e(updated or "unknown")}</span>'
    chips = [fresh, f'<span class="chip">Auto-refresh every {int(refresh_minutes)} min while open</span>',
             '<span class="chip">Source: ECMWF via Open-Meteo &middot; model: Random Forest</span>']
    if simulated:
        chips.insert(0, '<span class="chip sim"><b>SIMULATION ON</b> &middot; on screen only</span>')
    return '<div class="status-strip">' + ''.join(chips) + '</div>'
