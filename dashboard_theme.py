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
  --sky-top:#e3eefb; --sky-mid:#eff4fb; --sky-bottom:#f5f7fb; --cloud-opacity:.55; --star-opacity:0;
  --card:#ffffff; --card-solid:#ffffff; --card-border:rgba(15,40,80,.11);
  --card-shadow:0 1px 2px rgba(16,24,40,.05),0 6px 18px rgba(16,40,80,.07);
  --text:#14243a; --muted:#4a5b70; --heading:#0b1f3a; --accent:#1d4ed8; --accent-soft:#e8efff;
  --primary:#1d4ed8; --primary-text:#ffffff; --focus:#f59e0b;
  --chip:#ffffff; --chip-text:#1e2f46; --divider:#e3e9f1;
  --sidebar:linear-gradient(170deg,#103152 0%,#0b2440 55%,#081a30 100%); --sidebar-text:#dce9f8; --sidebar-muted:#a9c0da;
  --input-bg:#ffffff; --input-text:#0d2540;
  --good:#0d8a4c; --warn:#a85f00; --bad:#d4283e;
}
@media (prefers-color-scheme: dark) {
  :root {
    --sky-top:#0a1222; --sky-mid:#0c1527; --sky-bottom:#101a2d; --cloud-opacity:.05; --star-opacity:.45;
    --card:#16233a; --card-solid:#16233a; --card-border:rgba(148,170,200,.17);
    --card-shadow:0 1px 2px rgba(0,0,0,.35);
    --text:#e6edf7; --muted:#a3b3c7; --heading:#f4f7fc; --accent:#60a5fa; --accent-soft:#1c3156;
    --primary:#2563eb; --primary-text:#ffffff; --focus:#fbbf24;
    --chip:#1a2a44; --chip-text:#e6edf7; --divider:#26354f;
    --input-bg:#0f1a2d; --input-text:#e6edf7;
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
.st-key-top_nav_bar {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:6px 8px;box-shadow:var(--card-shadow)}
.st-key-top_nav_bar [data-testid="stButtonGroup"] {width:100%}
.st-key-top_nav_bar [role="radiogroup"],.st-key-top_nav_bar [data-testid="stButtonGroup"] > div {display:flex;flex-wrap:wrap;gap:6px}
.st-key-top_nav_bar button {border-radius:12px!important;min-height:40px;background:transparent!important;color:var(--chip-text)!important;border:0!important;font-weight:600}
.st-key-top_nav_bar button:hover {background:var(--accent-soft)!important}
.st-key-top_nav_bar button[aria-checked="true"],.st-key-top_nav_bar button[kind*="Active"] {background:#1d4ed8!important;color:#fff!important}
.st-key-top_nav_bar button[aria-checked="true"] p,.st-key-top_nav_bar button[kind*="Active"] p {color:#fff!important}

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
.rain-legend {height:11px;border-radius:6px;background:linear-gradient(90deg,#e5edf5 0%,#3c78e6 14.286%,#288cf0 28.571%,#28be6e 42.857%,#78c83c 57.143%,#facd32 71.429%,#f56e28 85.714%,#be1e32 100%)}
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
.resident-card::before {content:"";position:absolute;left:22px;top:22px;width:52px;height:52px;border-radius:16px;background:var(--r-badge)}
.resident-card::after {content:"";position:absolute;left:36px;top:36px;width:24px;height:24px;background-color:var(--r-border);
  -webkit-mask:var(--m) center/contain no-repeat;mask:var(--m) center/contain no-repeat}
.resident-card.tone-green {--r-border:#36a46b;--r-bg:linear-gradient(120deg,#effcf4,#e3f6ff);--r-badge:#d7f5e3}
.resident-card.tone-amber {--r-border:#d98b16;--r-bg:linear-gradient(120deg,#fff8e8,#fff1d6);--r-badge:#ffe8b8}
.resident-card.tone-red {--r-border:#d93449;--r-bg:linear-gradient(120deg,#fff0f1,#ffe4e8);--r-badge:#ffd2d9}
.resident-card.tone-gray {--r-border:#8a9bb0;--r-bg:linear-gradient(120deg,#f4f7fa,#e9eef4);--r-badge:#dfe6ee}
.resident-card.tone-off {--r-border:#8a9bb0;--r-bg:linear-gradient(120deg,#f4f7fa,#e9eef4);--r-badge:#dfe6ee}
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
/* Homepage hero: compact status tile and short action chips. */
.resident-card.hero-risk {box-sizing:border-box;padding:22px 22px 18px 92px;animation:rise .5s ease-out both}
.resident-card.hero-risk.tone-red {animation:rise .5s ease-out both,alarm 2.6s ease-in-out 1s infinite}
.hero-estimate {display:inline-block;margin:12px 0 10px;padding:7px 14px;border-radius:999px;background:var(--r-badge);
  color:var(--heading);font-weight:800;font-size:clamp(15px,1.5vw,19px)}
.hero-facts {display:flex;flex-wrap:wrap;gap:8px 16px;font-size:13.5px;color:var(--muted)}
.hero-note {margin-top:12px;font-size:12px;font-weight:600;color:var(--muted);letter-spacing:.2px}
.quick-actions {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:12px 16px;box-shadow:var(--card-shadow)}
.quick-actions .resident-action {font-size:15px;margin-bottom:8px}
.action-chips {display:flex;flex-wrap:wrap;gap:8px}
.action-chip {display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;background:var(--accent-soft);
  color:var(--heading);font-size:13px;font-weight:600;border:1px solid var(--card-border)}
.action-chip i {font-style:normal}
.st-key-weather_card {animation:rise .6s ease-out .1s both}
.st-key-weather_card .temperature {font-size:clamp(34px,3.4vw,46px)}
/* Menu button: three bars instead of Streamlit's double-arrow icon (open and close the side menu). */
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {font-size:0!important;width:22px;height:16px;display:inline-block;
  background:linear-gradient(currentColor 0 0) 0 0/100% 2.5px no-repeat,linear-gradient(currentColor 0 0) 0 50%/100% 2.5px no-repeat,linear-gradient(currentColor 0 0) 0 100%/100% 2.5px no-repeat}
/* Alerts: status banner, warning cards, contacts (tap to call). */
.alert-banner {border-radius:18px;padding:14px 18px 14px 20px;border:1px solid;box-shadow:var(--card-shadow);margin-bottom:4px}
.alert-banner.green {background:#ecfdf3;border-color:#86d9a8;color:#0b3d24}.alert-banner.red {background:#fff0f1;border-color:#f08a96;color:#5c0a16}
.alert-banner.amber {background:#fff6e0;border-color:#e6b04a;color:#4a3000}
.ab-kicker {font-size:11.5px;font-weight:800;letter-spacing:1.2px;opacity:.85}.ab-title {font-size:17px;font-weight:800;margin:3px 0}
.ab-text {font-size:14px}
.alert-banner.red {animation:alarm 2.6s ease-in-out infinite}
.warn-card {background:var(--card);border:1px solid var(--card-border);border-left:6px solid #8a9bb0;border-radius:14px;padding:10px 14px;box-shadow:var(--card-shadow)}
.warn-card.active {border-left-color:#e11d48}
.warn-top {display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;color:var(--heading)}
.warn-meta {display:flex;flex-wrap:wrap;gap:6px 16px;font-size:13px;color:var(--muted);margin-top:5px}
.warn-badge {font-size:11px;font-weight:800;letter-spacing:.6px;border-radius:999px;padding:3px 9px}
.warn-badge.live {background:#e11d48;color:#fff}.warn-badge.past {background:#dfe6ee;color:#334155}.warn-badge.test {background:#7a4b00;color:#fff}
.contacts-card {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:14px;box-shadow:var(--card-shadow)}
.contacts-head {display:flex;justify-content:space-between;font-size:12.5px;font-weight:800;letter-spacing:1px;color:var(--muted);text-transform:uppercase;margin-bottom:8px}
.contacts-head small {text-transform:none;letter-spacing:0;font-weight:500}
.call-row {display:flex;gap:12px;align-items:center;padding:10px 12px;margin:6px 0;border-radius:12px;border:1px solid var(--card-border);
  background:var(--card-solid);text-decoration:none!important;color:var(--text)!important}
.call-row:hover,.call-row:focus-visible {border-color:#dc2626;outline:none}
.call-icon {display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:#dc2626;flex-shrink:0}
.call-row b {display:block;font-size:19px;color:var(--heading)}.call-row small {color:var(--muted);font-size:12.5px}
.contacts-note {font-size:11.5px;color:var(--muted);margin-top:8px}
.call-chips {display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0}.call-chips span {font-weight:700;color:var(--heading)}
.call-chip {background:#dc2626;color:#fff!important;text-decoration:none!important;font-weight:800;border-radius:999px;padding:7px 14px}
.portal-note {background:var(--accent-soft);border:1px solid var(--card-border);border-radius:12px;padding:9px 14px;font-size:13px;color:var(--text)}
/* Blue weather card and hourly strip (genuine ECMWF forecast values only). */
.wx-card {background:linear-gradient(135deg,#1e40af,#2563eb 55%,#3b82f6);color:#fff;border-radius:22px;padding:18px 22px;box-shadow:0 14px 30px #1e3a8a40;animation:rise .6s ease-out both}
.wx-top {display:flex;flex-wrap:wrap;gap:4px 12px;justify-content:space-between;font-size:14px;font-weight:700;color:#e0ecff}
.wx-main {display:flex;justify-content:space-between;align-items:center;gap:12px}
.wx-temp {font-size:clamp(44px,5vw,78px);font-weight:300;line-height:1.05;margin-top:6px;white-space:nowrap}
.wx-cond {font-size:20px;font-weight:700}.wx-sub {font-size:13px;color:#dbe8ff;margin-top:2px}
.wx-main img {width:clamp(84px,9vw,124px);height:auto;filter:drop-shadow(0 6px 14px #0003)}
.wx-tiles {display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px;margin-top:14px}
.wx-tile {background:#ffffff1f;border:1px solid #ffffff33;border-radius:14px;padding:9px 11px}
.wx-tile span {display:block;font-size:11px;font-weight:700;letter-spacing:.6px;color:#dbe8ff;text-transform:uppercase}
.wx-tile b {display:block;font-size:18px;color:#fff}.wx-tile small {color:#dbe8ff;font-size:11.5px}
.wx-status {font-size:11px;color:#dbe8ff;margin-top:10px}
.hourly {display:flex;gap:8px;overflow-x:auto;padding:4px 2px 8px}
.hour {flex:1 0 84px;background:var(--card);border:1px solid var(--card-border);border-radius:14px;padding:8px;text-align:center;box-shadow:var(--card-shadow)}
.hour .t {font-size:12.5px;font-weight:700;color:var(--muted)}.hour img {width:40px;height:40px}
.hour b {display:block;font-size:17px;color:var(--heading)}.hour small {display:block;font-size:11px;color:var(--muted)}
/* Visual summaries: risk scale, warning flow, storm ingredients, advice cards. */
.risk-scale {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:16px 18px 30px;box-shadow:var(--card-shadow);margin-bottom:12px}
.risk-scale .title {font-weight:800;color:var(--heading);margin-bottom:10px}
.risk-scale .bar {position:relative;display:flex;height:22px;border-radius:11px;overflow:visible}
.risk-scale .band {display:grid;place-items:center;font-size:11px;font-weight:700;color:#fff}
.risk-scale .band:first-child {border-radius:11px 0 0 11px}.risk-scale .band:last-child {border-radius:0 11px 11px 0}
.risk-scale .marker {position:absolute;top:-8px;width:4px;height:38px;background:var(--heading);border-radius:2px;transform:translateX(-2px)}
.risk-scale .marker b {position:absolute;top:40px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:12.5px;color:var(--heading)}
.flow {display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:6px 0 14px}
.flow .step {flex:1 1 140px;background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:12px;text-align:center;box-shadow:var(--card-shadow)}
.flow .step i {display:block;font-style:normal;color:var(--accent)}.flow .step b {display:block;color:var(--heading);font-size:14px;margin-top:4px}
.flow .step small {color:var(--muted);font-size:12px}.flow .arrow {font-size:22px;color:var(--muted)}
.flow .step.decision {border:2px dashed #ed394b}
.risk-body.single {grid-template-columns:1fr;justify-items:center}
.ingredients {display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:10px}
.ingredient {background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:12px 14px;box-shadow:var(--card-shadow)}
.ingredient span {font-size:12px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}
.ingredient b {display:block;font-size:22px;color:var(--heading);margin:4px 0}.ingredient small {color:var(--muted);font-size:12px}
.advice-block {margin:4px 0 8px}.advice-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-top:8px}
.advice-card {background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:12px 14px;box-shadow:var(--card-shadow)}
.advice-card b {color:var(--heading)}.advice-card p {font-size:13.5px;margin:4px 0 0;color:var(--text)}
.advice-icon {color:var(--accent);font-size:24px}
.sr-only {position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
/* Streamlit widgets: one token set for both themes (base theme is pinned to light in config). */
[data-testid="stHeader"] {background:transparent!important}
.stApp [data-testid="stMain"] [data-testid="stMarkdownContainer"],[data-testid="stMain"] [data-testid="stMarkdownContainer"] p,
[data-testid="stMain"] [data-testid="stWidgetLabel"] p,[data-testid="stMain"] label {color:var(--text)}
[data-testid="stMain"] [data-testid="stCaptionContainer"],[data-testid="stMain"] [data-testid="stCaptionContainer"] p {color:var(--muted)!important}
[data-testid="stMain"] [data-baseweb="input"],[data-testid="stMain"] [data-baseweb="base-input"],[data-testid="stMain"] [data-baseweb="textarea"],
[data-testid="stMain"] [data-baseweb="select"] > div {background:var(--input-bg)!important;border-color:var(--card-border)!important}
[data-testid="stMain"] input,[data-testid="stMain"] textarea,[data-testid="stMain"] [data-baseweb="select"] * {color:var(--input-text)!important;-webkit-text-fill-color:var(--input-text)}
[data-baseweb="popover"] ul,[data-baseweb="popover"] li {background:var(--card-solid)!important;color:var(--text)!important}
[data-testid="stMain"] [data-testid="stExpander"] details {background:var(--card);border-color:var(--card-border)!important;border-radius:14px}
[data-testid="stMain"] [data-testid="stExpander"] summary,[data-testid="stMain"] [data-testid="stExpander"] summary p {color:var(--text)}
[data-testid="stMain"] [data-testid="stAlertContainer"] {background:var(--accent-soft)!important;border:1px solid var(--card-border);border-radius:12px}
[data-testid="stMain"] [data-testid="stAlertContainer"] p,[data-testid="stMain"] [data-testid="stAlertContainer"] div {color:var(--text)!important}
[data-testid="stMain"] [data-testid="stBaseButton-secondary"],[data-testid="stMain"] [data-testid="stBaseButton-secondaryFormSubmit"],
[data-testid="stMain"] [data-testid="stBaseLinkButton-secondary"] {background:var(--card-solid)!important;color:var(--text)!important;border-color:var(--card-border)!important}
[data-testid="stMain"] [data-testid="stBaseButton-secondary"] p,[data-testid="stMain"] [data-testid="stBaseLinkButton-secondary"] p {color:var(--text)!important}
[data-testid="stMain"] [data-testid="stBaseButton-primary"],[data-testid="stMain"] [data-testid="stBaseButton-primaryFormSubmit"],
[data-testid="stMain"] [data-testid="stBaseLinkButton-primary"] {background:var(--primary)!important;border-color:var(--primary)!important;color:var(--primary-text)!important}
[data-testid="stMain"] [data-testid="stBaseButton-primary"] p,[data-testid="stMain"] [data-testid="stBaseLinkButton-primary"] p {color:var(--primary-text)!important}
[data-testid="stMain"] [data-testid="stMetricLabel"] p {color:var(--muted)!important}[data-testid="stMain"] [data-testid="stMetricValue"] {color:var(--heading)!important}
[data-testid="stMain"] [data-baseweb="tab"] p {color:var(--muted)}[data-testid="stMain"] [data-baseweb="tab"][aria-selected="true"] p {color:var(--heading);font-weight:700}
[data-testid="stMain"] [data-testid="stCode"] pre,[data-testid="stMain"] code {background:var(--card-solid)!important;color:var(--text)!important}
[data-testid="stMain"] [data-testid="stSliderThumbValue"],[data-testid="stMain"] [data-testid="stSliderTickBar"] {color:var(--muted)!important}
[data-testid="stMain"] hr {border-color:var(--divider)}
[data-testid="stMain"] [data-testid="stButtonGroup"] button[aria-checked="true"] *,.st-key-top_nav_bar button[aria-checked="true"] * {color:#fff!important}
.call-icon {color:#fff}
/* Visible keyboard focus everywhere (buttons, links, inputs, switches). */
.stApp a:focus-visible,.stApp button:focus-visible,.stApp input:focus-visible,.stApp textarea:focus-visible,.stApp [role="switch"]:focus-visible,
.stApp [role="radio"]:focus-visible,.stApp summary:focus-visible {outline:3px solid var(--focus)!important;outline-offset:2px}
/* Header tools: clock and theme switch. */
.st-key-header_tools [data-testid="stCheckbox"] {justify-content:flex-end}
.st-key-header_tools label p {font-weight:700;color:var(--heading)}
.st-key-browser_prefs {height:0;overflow:hidden;margin:0}
/* Themed tables (canvas tables cannot follow the page theme). */
.dtable-wrap {overflow-x:auto;border:1px solid var(--card-border);border-radius:14px;background:var(--card);box-shadow:var(--card-shadow)}
.dtable {width:100%;border-collapse:collapse;font-size:13.5px;color:var(--text)}
.dtable th {text-align:left;font-size:12px;font-weight:700;color:var(--muted);background:var(--accent-soft);padding:9px 12px;white-space:nowrap}
.dtable td {padding:8px 12px;border-top:1px solid var(--divider);vertical-align:top}
.dtable td.num {text-align:right;font-variant-numeric:tabular-nums}
.dtable .bar {display:inline-block;width:80px;height:7px;border-radius:4px;background:var(--divider);margin-right:8px;vertical-align:middle;overflow:hidden}
.dtable .bar i {display:block;height:100%;background:var(--accent)}
.dtable a {color:var(--accent)}
@keyframes rise {from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@keyframes alarm {0%,100%{box-shadow:var(--card-shadow)}50%{box-shadow:0 0 0 6px #ed394b33,var(--card-shadow)}}

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
  .alert-banner.green {background:#0f3326;border-color:#2f8f5f;color:#d7f7e5}.alert-banner.red {background:#43121c;border-color:#ff6b80;color:#ffe1e6}
  .alert-banner.amber {background:#3a2a0c;border-color:#e0a03a;color:#fff1c8}
  .warn-badge.past {background:#2b3d55;color:#dbe7f5}.wx-card {background:linear-gradient(135deg,#0b2a6b,#1e40af 60%,#2457c5)}
  .resident-head {color:#f4f8fd}.resident-text {color:#dbe7f5}
  .resident-facts span {background:#ffffff12;border-color:#ffffff1f;color:#e3edf9}.resident-facts b,.resident-note {color:#b5c8de}
  .research-notice {background:#3d3216;color:#fff1c8;border-color:#b78e34}
  .clock-card {background:linear-gradient(120deg,#0b3f80,#0d5bb0)}
}
@media (prefers-reduced-motion: reduce) {
  .stApp::before,.chip .dot,.weather-anim *,.resident-card.hero-risk,.st-key-weather_card,.wx-card,.alert-banner.red {animation:none!important}
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
  .resident-card {padding:84px 16px 16px}.resident-card::before {left:16px;top:16px}.resident-card::after {left:30px;top:30px}.kpi {min-height:90px}.prediction-table {font-size:10.5px}
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


def weather_card_html(icon_img, temperature, condition, subtitle, tiles, status, updated=''):
    """Blue forecast-weather card. Every value comes from the genuine ECMWF model input."""
    e = html.escape
    tile_html = ''.join(f'<div class="wx-tile"><span>{icons.icon(icon)} {e(label)}</span><b>{e(value)}</b><small>{e(detail)}</small></div>'
                        for icon, label, value, detail in tiles)
    return (f'<div class="wx-card"><div class="wx-top"><span>{icons.icon("map-pin")} Matatiele, Eastern Cape</span><span>{e(updated)}</span></div>'
            f'<div class="wx-main"><div><div class="wx-temp">{e(temperature)}</div><div class="wx-cond">{e(condition)}</div>'
            f'<div class="wx-sub">{e(subtitle)}</div></div>{icon_img}</div><div class="wx-tiles">{tile_html}</div>'
            f'<div class="wx-status">{e(status)}</div></div>')


def hourly_html(hours):
    """hours: (label, icon_img, temperature, rain, wind) per forecast hour."""
    e = html.escape
    cells = ''.join(f'<div class="hour"><div class="t">{e(label)}</div>{icon}<b>{e(temp)}</b><small>{icons.icon("cloud-rain", "Rain")} {e(rain)}</small><small>{icons.icon("wind", "Wind")} {e(wind)}</small></div>'
                    for label, icon, temp, rain, wind in hours)
    return f'<div class="hourly">{cells}</div>'


def risk_scale_html(probability, threshold=0.35):
    """The four risk bands on one bar, with a marker at the current estimate (None: no marker)."""
    # Label colours keep at least 4.5:1 contrast on each band.
    bands = [(0, 10, '#4cc27a', '#0b1f3a', 'Low'), (10, 20, '#f5c242', '#0b1f3a', 'Elevated'),
             (20, round(threshold * 100), '#fb9a4b', '#0b1f3a', 'Moderate'), (round(threshold * 100), 100, '#c81e33', '#ffffff', 'Warning')]
    segments = ''.join(f'<div class="band" style="flex:{high - low};background:{color};color:{text}">{name}</div>' for low, high, color, text, name in bands)
    marker = ''
    if probability is not None and 0 <= probability <= 1:
        side = 'left:0;transform:none' if probability < .08 else ('right:0;left:auto;transform:none' if probability > .92 else '')
        marker = f'<div class="marker" style="left:{probability * 100:.1f}%"><b style="{side}">Now {probability:.1%}</b></div>'
    return (f'<div class="risk-scale"><div class="title">Risk scale · warning at {threshold:.0%}</div>'
            f'<div class="bar">{segments}{marker}</div></div>')


def flow_html():
    """How a storm warning is produced and reaches people (one picture instead of a paragraph)."""
    steps = [('radar', 'Forecast', 'ECMWF, every hour', ''), ('cpu', 'Storm model', 'Random Forest, next hour', ''),
             ('scale', '35% or more?', 'No: check again next hour', ' decision'), ('siren', 'Warning', 'Alerts page', ''),
             ('message', 'SMS', 'Registered phones', ''), ('clipboard', 'Officials', 'Review and record', '')]
    parts = []
    for name, title, detail, extra in steps:
        parts.append(f'<div class="step{extra}"><i>{icons.icon(name, size="28px")}</i><b>{html.escape(title)}</b><small>{html.escape(detail)}</small></div>')
    return '<div class="flow">' + f'<span class="arrow">{icons.icon("arrow-right")}</span>'.join(parts) + '</div>'


def ingredient_tiles_html(tiles):
    """tiles: (icon, label, value, detail)."""
    e = html.escape
    return '<div class="ingredients">' + ''.join(
        f'<div class="ingredient"><span>{icons.icon(icon)} {e(label)}</span><b>{e(value)}</b><small>{e(detail)}</small></div>'
        for icon, label, value, detail in tiles) + '</div>'


import icons  # noqa: E402  (icon masks share this theme)

TONE_ICONS = {'green': 'check-circle', 'amber': 'alert', 'red': 'siren', 'gray': 'help-circle', 'off': 'bell-off'}
CHART_COLORS = {'light': {'text': '#334155', 'grid': '#e2e8f0'}, 'dark': {'text': '#a3b3c7', 'grid': '#26354f'}}


def theme_css(mode):
    """The whole stylesheet for 'light' or 'dark': the dark token layer is switched on or off explicitly,
    so every page (and the officials' portal) follows the visitor's choice rather than the device setting."""
    switch = '@media all' if mode == 'dark' else '@media not all'
    tones = ''.join(f'.resident-card.tone-{tone}{{--m:url("{icons._uri(name)}")}}' for tone, name in TONE_ICONS.items())
    return CSS.replace('@media (prefers-color-scheme: dark)', switch) + icons.CSS + tones


def style_chart(chart, mode):
    """Altair chart colours for the selected theme (transparent background, readable axes)."""
    colours = CHART_COLORS[mode]
    return (chart.configure(background='transparent').configure_view(stroke=None)
            .configure_axis(labelColor=colours['text'], titleColor=colours['text'], gridColor=colours['grid'],
                            domainColor=colours['grid'], tickColor=colours['grid'])
            .configure_legend(labelColor=colours['text'], titleColor=colours['text']))


def table_html(frame, bars=None, links=None, caption=''):
    """A themed, scrollable HTML table. bars: {column: maximum} shows a bar beside the value; links: {column: text}."""
    bars, links = bars or {}, links or {}
    e = html.escape
    head = ''.join(f'<th scope="col">{e(str(c))}</th>' for c in frame.columns)
    rows = []
    for _, row in frame.iterrows():
        cells = []
        for column in frame.columns:
            value = row[column]
            text = '' if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)
            if column in links and text:
                cells.append(f'<td><a href="{e(text, quote=True)}" target="_blank" rel="noopener">{e(links[column])}</a></td>')
            elif column in bars and text:
                width = max(0.0, min(100.0, float(value) / bars[column] * 100))
                cells.append(f'<td class="num"><span class="bar"><i style="width:{width:.0f}%"></i></span>{e(text)}</td>')
            else:
                numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
                cells.append(('<td class="num">' if numeric else '<td>') + e(text) + '</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    cap = f'<caption class="sr-only">{e(caption)}</caption>' if caption else ''
    return f'<div class="dtable-wrap"><table class="dtable">{cap}<thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
