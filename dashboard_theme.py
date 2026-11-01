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
[data-testid="stMain"] [data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"] {gap:.7rem}
[data-testid="stHeader"] {backdrop-filter:blur(6px)}
[data-testid="stMainBlockContainer"] {max-width:1720px;padding:3.1rem 1.25rem 1.25rem}
[data-testid="stVerticalBlock"] {gap:.85rem}
[data-testid="stMain"] [data-testid="stMarkdownContainer"],[data-testid="stMain"] [data-testid="stWidgetLabel"] p,
[data-testid="stMain"] h1,[data-testid="stMain"] h2,[data-testid="stMain"] h3,[data-testid="stMain"] h4 {color:var(--text)}
[data-testid="stMain"] h4 {font-weight:750;letter-spacing:-.3px;color:var(--heading)}
[data-testid="stMain"] [data-testid="stCaptionContainer"] * {color:var(--muted)!important}

/* Sidebar */
[data-testid="stSidebar"] {background:var(--sidebar)}
[data-testid="stSidebar"][aria-expanded="true"] {min-width:255px;max-width:275px}  /* closed: no reserved width */
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
.status-strip {display:flex;flex-wrap:wrap;gap:6px;margin:0}
.chip {display:inline-flex;align-items:center;gap:7px;background:var(--chip);color:var(--chip-text);border:1px solid var(--card-border);
  border-radius:999px;padding:6px 12px;font-size:12.5px;backdrop-filter:blur(6px)}
.chip b {font-weight:700}
.chip .dot {width:9px;height:9px;border-radius:50%;background:var(--good);box-shadow:0 0 0 0 #16a34a80;animation:pulse 2.4s ease-out infinite}
.chip.stale .dot {background:var(--warn);animation:none}
.chip.sim {background:#4a0f6b;color:#fff;border-color:#ffd23f}
@keyframes pulse {0%{box-shadow:0 0 0 0 #16a34a80}70%{box-shadow:0 0 0 9px #16a34a00}100%{box-shadow:0 0 0 0 #16a34a00}}

/* Cards */
.st-key-map_card,.st-key-risk_card,.st-key-six_card,.st-key-sample_card,.st-key-predictions_card,.st-key-live_six_card {
  background:var(--card)!important;border:1px solid var(--card-border)!important;border-radius:18px!important;
  box-shadow:var(--card-shadow);backdrop-filter:blur(8px);overflow:hidden}
.st-key-map_card {padding:0!important}
.panel-heading {display:flex;align-items:center;gap:10px;font-size:16px;font-weight:750;color:var(--heading);margin:0 0 9px;line-height:1.4}
.panel-heading img {width:22px;height:22px;flex-shrink:0}
.section-title {display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;margin:6px 0 0;font-size:18px;font-weight:800;letter-spacing:-.3px;color:var(--heading)}
.section-title small {font-size:12px;font-weight:600;color:var(--muted);letter-spacing:0}
.kpi {display:flex;align-items:center;gap:12px;background:var(--card);border:1px solid var(--card-border);border-left:5px solid var(--accent-c,var(--accent));
  border-radius:16px;padding:14px 12px;min-height:101px;box-shadow:var(--card-shadow)}
.kpi-icon {background:var(--accent-c,var(--accent));color:#fff;width:44px;height:44px;display:flex;align-items:center;justify-content:center;border-radius:50%;flex-shrink:0}
.kpi-icon img {width:27px;height:27px;filter:brightness(0) invert(1)}
.kpi .label {font-size:12px;color:var(--muted);line-height:1.4}
.kpi .value {font-weight:800;font-size:24px;color:var(--heading);line-height:1.25;margin:3px 0}
.kpi .sub {font-size:11.5px;color:var(--muted);line-height:1.4}.kpi.compact .value {font-size:19px}
[data-testid="stDeckGlJsonChart"] {border-radius:12px;overflow:hidden}
.map-legend {background:var(--card-solid);border:1px solid var(--card-border);border-radius:12px;padding:8px 12px;margin:6px 0 2px}
.map-legend .title {font-size:12px;font-weight:700;color:var(--heading);margin-bottom:6px}
.rain-legend {height:11px;border-radius:6px;background:linear-gradient(90deg,#e5edf5 0%,#3c78e6 14.286%,#288cf0 28.571%,#28be6e 42.857%,#78c83c 57.143%,#facd32 71.429%,#f56e28 85.714%,#be1e32 100%)}
.legend-labels {display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:4px}
.map-legend .note {font-size:11px;color:var(--muted);margin-top:6px}

/* Forecast weather card */
.temperature {font-size:clamp(28px,2.7vw,42px);font-weight:800;color:var(--heading);letter-spacing:-1px;white-space:nowrap}
.condition {font-size:13px;font-weight:650;color:var(--text);margin-top:4px}.condition small {display:block;font-weight:400;color:var(--muted)}

/* Next-hour gauge (value as HTML text so it follows the theme) */
.risk-body {display:grid;grid-template-columns:1.05fr 1fr;align-items:center;gap:8px}
.risk-gauge {text-align:center;position:relative}.risk-gauge img {width:100%;height:auto;max-width:240px}
.gauge-value {position:absolute;left:0;right:0;top:26%;text-align:center;font-size:28px;font-weight:800;line-height:1.1;color:var(--heading)}
.gauge-label {position:absolute;left:0;right:0;top:47%;text-align:center;font-size:12px;color:var(--muted)}
.risk-badge {border-radius:8px;padding:7px 10px;display:block;font-size:11px;font-weight:800;background:var(--tint);color:var(--accent)}
.risk-status {font-size:10.5px;font-weight:700;color:var(--muted);margin-bottom:6px;letter-spacing:.3px}

/* Tables and research cards */
.research-card {background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:20px;color:var(--text);margin-bottom:12px;line-height:1.6;box-shadow:var(--card-shadow)}
.research-card .label {color:var(--muted);font-size:12px;margin-bottom:8px}
.research-card .value {color:var(--heading);font-size:23px;font-weight:750;line-height:1.35;overflow-wrap:anywhere}
.research-card .detail {color:var(--muted);font-size:12px;margin-top:8px}
.research-notice {background:#fff5dc;border:1px solid #e5ca83;border-left:5px solid #a46605;border-radius:12px;padding:18px;color:#65430c;line-height:1.6}
.research-notice a {color:#6b2f00!important;font-weight:700;text-decoration:underline;text-underline-offset:2px}
.research-notice a:hover {color:#3d1a00!important;text-decoration-thickness:2px}.research-notice a:focus-visible {outline:3px solid #1d4ed8;outline-offset:2px;border-radius:3px}

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
.quick-actions {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:12px 16px;box-shadow:var(--card-shadow)}
.quick-actions .resident-action {font-size:15px;margin-bottom:8px}
.action-chips {display:flex;flex-wrap:wrap;gap:8px}
.action-chip {display:inline-flex;align-items:center;gap:6px;padding:6px 12px;border-radius:999px;background:var(--accent-soft);
  color:var(--heading);font-size:13px;font-weight:600;border:1px solid var(--card-border)}
.action-chip i {font-style:normal}
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
.contacts-card.wide .call-list {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.contacts-card.wide .call-row {margin:0}
@media(max-width:700px) {.contacts-card.wide .call-list {grid-template-columns:1fr}}
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
/* Blue weather card (genuine ECMWF forecast values only). */
/* Visual summaries: risk scale, warning flow, storm ingredients, advice cards. */
.risk-scale {background:var(--card);border:1px solid var(--card-border);border-radius:18px;padding:16px 18px 30px;box-shadow:var(--card-shadow);margin-bottom:12px}
.risk-scale .title {font-weight:800;color:var(--heading);margin-bottom:10px}
.risk-scale .bar {position:relative;display:flex;height:22px;border-radius:11px;overflow:visible}
.risk-scale .band {display:grid;place-items:center;font-size:11px;font-weight:700;color:#fff}
.risk-scale .band:first-child {border-radius:11px 0 0 11px}.risk-scale .band:last-child {border-radius:0 11px 11px 0}
.risk-scale .marker {position:absolute;top:-8px;width:4px;height:38px;background:var(--heading);border-radius:2px;transform:translateX(-2px)}
.risk-scale .marker b {position:absolute;top:40px;left:50%;transform:translateX(-50%);white-space:nowrap;font-size:12.5px;color:var(--heading)}
.flow {margin:4px 0 8px}
.flow .lane-steps {display:flex;align-items:stretch;gap:4px}
.flow .step {flex:1 1 0;display:flex;align-items:center;gap:9px;min-width:0;overflow-wrap:anywhere;background:var(--card);border:1px solid var(--card-border);
  border-radius:12px;padding:8px 10px;box-shadow:var(--card-shadow)}
.flow .step.optional {border-style:dashed}
.flow .step .ico {color:var(--accent)}.flow .step>div {min-width:0}.flow .step b {display:block;hyphens:auto;color:var(--heading);font-size:13.5px;line-height:1.25}
.flow .step small {display:block;color:var(--muted);font-size:12px;line-height:1.3}
.flow .arrow {display:flex;align-items:center;color:var(--muted)}
.flow .badge {display:inline-block;margin-top:3px;font-size:11px;font-weight:800;border-radius:999px;padding:1px 8px}
.flow .badge.on {background:#dcfce7;color:#14532d}.flow .badge.opt {background:#fef3c7;color:#713f12}
.explainer {margin:4px 0 0 18px;padding:0;color:var(--text);font-size:14px;line-height:1.5}.explainer li {margin:4px 0}
.explainer b {color:var(--heading)}
.lowdata-link {font-size:13px;color:var(--muted);margin-top:2px}.lowdata-link a {color:var(--accent);font-weight:700}
/* Streamlit's own menu has a separate theme setting that conflicts with the header switch, so it is hidden. */
[data-testid="stMainMenu"] {display:none!important}
/* Homepage: four compact summary cards. */
.summary-grid {display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr) minmax(0,.95fr) minmax(0,1fr);grid-template-areas:"weather risk period decision";gap:12px;margin:4px 0 10px}
.risk-summary {grid-area:risk}.decision-summary {grid-area:decision}.wx-summary {grid-area:weather}.period-summary {grid-area:period}
.period-row {display:flex;gap:10px;align-items:flex-start;margin:8px 0}.period-row>.ico {width:22px;height:22px;color:var(--accent);margin-top:2px}
.period-row small {display:block;font-size:11.5px;color:var(--muted)}.period-row b {font-size:14px;color:var(--heading)}
.fresh-badge {display:inline-block;margin-top:8px;padding:6px 12px;border-radius:10px;font-weight:700;font-size:13px;background:#dcfce7;color:#14532d}.fresh-badge.stale {background:#fef3c7;color:#713f12}
.var-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px 16px}.var-tile {display:flex;gap:10px;align-items:center}
.var-tile>.ico {width:26px;height:26px;color:var(--accent);flex-shrink:0}.var-tile small {display:block;font-size:11.5px;color:var(--muted)}.var-tile b {font-size:19px;color:var(--heading)}
.log-wrap {overflow-x:auto}.pred-log {width:100%;border-collapse:collapse;font-size:13px;color:var(--text)}
.pred-log th {text-align:left;font-size:12px;color:var(--muted);padding:6px 8px;border-bottom:1px solid var(--divider)}.pred-log td {padding:7px 8px;border-bottom:1px solid var(--divider)}
.log-decision {font-weight:700;white-space:nowrap}
.sev {display:inline-block;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:800;letter-spacing:.4px;background:#e2e8f0;color:#1e293b}.sev-high,.sev-warning {background:#fde2e4;color:#9f1239}.sev-moderate {background:#ffedd5;color:#9a3412}.sev-elevated {background:#fef3c7;color:#854d0e}.sev-low,.sev-normal {background:#dcfce7;color:#14532d}.syslog td:first-child {white-space:nowrap}.log-decision.tone-red {color:#c81e33}.log-decision.tone-amber {color:#b45309}.log-decision.tone-green {color:var(--good)}
.risk-dial {position:relative;max-width:330px;margin:4px auto 0}.risk-gauge-img {display:block;width:100%;height:auto}
.risk-value {position:absolute;left:0;right:0;bottom:2px;text-align:center;font-size:clamp(40px,4.4vw,58px);font-weight:800;color:var(--heading);line-height:1;letter-spacing:-1px}
.risk-badge-row {text-align:center;margin:10px 0 4px}.risk-pill {display:inline-block;padding:5px 14px;border-radius:999px;font-size:13px;font-weight:800;letter-spacing:.6px;color:#fff;background:#2f855a}
.risk-pill.tone-amber {background:#b45309}.risk-pill.tone-red {background:#c81e33}.risk-pill.tone-gray {background:#5b6b80}
.risk-note {text-align:center;font-size:12.5px;font-weight:600;color:var(--muted)}
.risk-meta {display:flex;flex-wrap:wrap;justify-content:center;gap:4px 14px;margin-top:10px;font-size:12.5px;color:var(--text)}.risk-meta span {display:inline-flex;align-items:center;gap:5px}
.risk-caveat {text-align:center;margin-top:6px;font-size:11.5px;color:var(--muted)}
.decision-badge {display:flex;align-items:center;gap:10px;padding:12px 14px;border-radius:14px;margin:4px 0 8px;font-size:17px;letter-spacing:.4px;color:#fff;background:#2f855a}
.decision-badge .ico {width:26px;height:26px;flex-shrink:0}.decision-badge.tone-amber {background:#b45309}.decision-badge.tone-red {background:#c81e33}.decision-badge.tone-gray {background:#5b6b80}
.decision-foot {display:flex;flex-wrap:wrap;align-items:center;gap:4px 12px;margin-top:8px}.decision-foot .threshold-info {margin-top:0}
.wx-now {display:flex;align-items:center;justify-content:space-between;gap:8px}.wx-now img {width:64px;height:64px}
.wx-stats {display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}.wx-stats span {background:#ffffff1f;border-radius:10px;padding:6px;text-align:center;display:flex;flex-direction:column;align-items:center}
.wx-stats .ico {width:21px;height:21px;color:#ffffff}.wx-stats b {font-size:15px;color:#fff}.wx-stats small {font-size:11px;color:#dbe8ff}
.comm-tiles {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.comm-tile {display:flex;flex-direction:column;gap:4px;padding:10px;border-radius:12px;border:1px solid var(--card-border);font-size:12.5px;color:var(--muted)}
.comm-tile .ico {width:20px;height:20px;color:var(--accent)}
.summary-card {background:var(--card);border:1px solid var(--card-border);border-radius:16px;padding:13px 15px;box-shadow:var(--card-shadow);min-width:0;font-size:13px;color:var(--text)}
.sc-title {display:flex;align-items:center;gap:6px;font-size:12px;font-weight:800;letter-spacing:.3px;text-transform:uppercase;color:var(--muted);margin-bottom:6px}
.sc-value {font-size:30px;font-weight:700;color:var(--heading);line-height:1.1}
.sc-line {margin:3px 0;line-height:1.4}.sc-foot {margin-top:6px;font-size:11.5px;color:var(--muted);line-height:1.4}
.wx-summary {background:linear-gradient(135deg,#1e40af,#2563eb 60%,#3b82f6);color:#fff;border:0}.wx-summary .sc-title,.wx-summary .sc-foot {color:#dbe8ff}.wx-summary .sc-value {color:#fff}
.sc-state {display:inline-flex;align-items:center;gap:6px;font-weight:700;color:var(--heading)}
.sc-state::before {content:"";width:9px;height:9px;border-radius:50%;background:#8a9bb0;flex-shrink:0}.sc-state.ok::before {background:#16a34a}.sc-state.warn::before {background:#d97706}
.risk-summary {border-left:5px solid #36a46b}.risk-summary.tone-amber {border-left-color:#d98b16}.risk-summary.tone-red {border-left-color:#d93449}.risk-summary.tone-gray {border-left-color:#8a9bb0}
@media(max-width:1100px) {.summary-grid {grid-template-columns:repeat(2,minmax(0,1fr));grid-template-areas:"risk decision" "weather period"}}
@media(max-width:640px) {.summary-grid {grid-template-columns:1fr;grid-template-areas:"risk" "decision" "period" "weather"}.comm-tiles {grid-template-columns:1fr}
  .comm-tile {flex-direction:row;align-items:center;justify-content:space-between}.risk-value {font-size:46px}}
.threshold-info {margin-top:8px;font-size:13px;color:var(--text)}
.threshold-info summary {cursor:pointer;font-weight:700;color:var(--heading);display:inline-flex;align-items:center;gap:6px}
.threshold-info p {margin:6px 0 0;max-width:72ch}
.map-band {display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;margin:0}
.map-band b {font-size:17px;color:var(--heading)}.map-band small {font-size:12px;color:var(--muted)}
.st-key-map_card [data-testid="stVerticalBlock"] {gap:.45rem}
.map-legend .ring {display:inline-block;width:12px;height:12px;border-radius:50%;border:3px solid var(--ring);vertical-align:-2px;margin-right:4px}
@media (min-width:641px) and (max-width:1100px) {
  .st-key-map_controls [data-testid="stHorizontalBlock"] {flex-wrap:wrap!important;row-gap:2px!important}
  .st-key-map_controls [data-testid="stColumn"]:first-child {flex:1 1 100%!important;width:100%!important}
  .st-key-map_controls [data-testid="stColumn"]:not(:first-child) {flex:1 1 0!important;min-width:0!important}}
@media (max-width:700px) {.flow .lane-steps {flex-direction:column}.flow .arrow {justify-content:center;transform:rotate(90deg)}
  .status-strip .chip {white-space:normal}
  .st-key-map_controls [data-testid="stHorizontalBlock"] {gap:4px!important}}
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
[data-testid="stMain"] [data-testid="stMainBlockContainer"] > div > [data-testid="stVerticalBlock"] {gap:.7rem}
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
  .warn-badge.past {background:#2b3d55;color:#dbe7f5}
  .resident-head {color:#f4f8fd}.resident-text {color:#dbe7f5}
  .resident-facts span {background:#ffffff12;border-color:#ffffff1f;color:#e3edf9}.resident-facts b,.resident-note {color:#b5c8de}
  .research-notice {background:#3d3216;color:#fff1c8;border-color:#b78e34}
  .research-notice a {color:#ffe08a!important}.research-notice a:hover {color:#ffffff!important}.research-notice a:focus-visible {outline-color:#93c5fd}
  .clock-card {background:linear-gradient(120deg,#0b3f80,#0d5bb0)}
}
@media (prefers-reduced-motion: reduce) {
  .stApp::before,.chip .dot,.weather-anim *,.alert-banner.red {animation:none!important}
  [data-testid="stSidebar"] [data-testid="stButton"] button {transition:none}
}
@media(max-width:1100px) {.hero {align-items:flex-start}.clock-card {padding:10px}.kpi {gap:7px;padding:12px 8px}.kpi-icon {width:34px;height:34px}
  .kpi .value {font-size:20px}.temperature {font-size:30px}}
@media(max-width:900px) {[data-testid="stHorizontalBlock"] {flex-wrap:wrap}
  [data-testid="stHorizontalBlock"]>[data-testid="stColumn"] {min-width:min(100%,280px);flex:1 1 280px}
  .hero {flex-wrap:wrap}.clock-card {width:100%;box-sizing:border-box;text-align:left}.clock-card small {display:inline;margin-left:12px}
  .risk-body {grid-template-columns:1fr 1fr}}
@media(max-width:640px) {[data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .kpi)>[data-testid="stColumn"] {min-width:0;flex:1 1 calc(50% - 12px)}
  [data-testid="stMainBlockContainer"] {padding:3.1rem .85rem 1rem}.hero h1 {font-size:22px}.hero-main>img {width:38px;height:38px}.hero p {font-size:12.5px}
  .resident-card {padding:84px 16px 16px}.resident-card::before {left:16px;top:16px}.resident-card::after {left:30px;top:30px}.kpi {min-height:90px}
  .risk-body {grid-template-columns:1fr}}
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


# Header artwork: the project's own illustrative Matatiele storm landscape (static/matatiele_storm_banner*.jpg),
# created for the research and survey material. It is branding, not a picture of current weather.
BANNER_IMAGE, BANNER_IMAGE_SMALL = 'app/static/matatiele_storm_banner.jpg', 'app/static/matatiele_storm_banner_small.jpg'


def refresh_text(next_refresh, now):
    """'Next refresh in MM:SS' from the scheduled time (the page's own timer then counts down each second)."""
    if next_refresh is None:
        return 'Refreshes every 15 min'
    seconds = int((next_refresh - now).total_seconds())
    return f'Next refresh in {seconds // 60:02d}:{seconds % 60:02d}' if seconds > 0 else 'Refreshing now'


BANNER_LABEL = 'Illustrative Matatiele storm landscape artwork — not current weather.'


def banner_html(clock, status_ok, refresh, last_update=None, update_state=None, next_refresh_ms=None, now_ms=None):
    """Header: brand, location, the clock and the system status.

    status_ok: the latest retrieved ECMWF forecast and model result are current (not radar or a sensor feed).
    update_state: 'updated' when a newer genuine result has just arrived, 'restored' when it arrived after out-of-date
    data; None otherwise. next_refresh_ms / now_ms let the page count down and run the clock between reruns.
    """
    e = html.escape
    if status_ok:
        chip = '<span class="bn-chip ok"><i></i>System online</span>'
    else:
        chip = f'<span class="bn-chip stale"><i></i>Saved data · last update {e(last_update or "unknown")}</span>'
    note = {'updated': 'Updated just now', 'restored': 'Connection restored · latest data retrieved'}.get(update_state)
    updated = f'<span class="bn-updated">{note}</span>' if note else ''
    timer = (f' data-next="{int(next_refresh_ms)}"' if next_refresh_ms else '') + (f' data-now="{int(now_ms)}"' if now_ms else '')
    return (f'<div class="banner{" just-updated" if update_state else ""}" title="{e(BANNER_LABEL)}">'
            f'<span class="sr-only" role="img" aria-label="{e(BANNER_LABEL)}"></span>'
            f'<div class="bn-brand">{icons.icon("cloud", "")}'
            '<div><h1>Matatiele<span>Storm Early Warning System</span></h1><small>Machine-learning storm-risk assessment for safer communities</small></div></div>'
            f'<div class="bn-place"><b>{icons.icon("map-pin")} Matatiele, Eastern Cape</b><span>Smart · Resilient · Low-connectivity</span></div>'
            f'<div class="bn-clock"{timer}><div><small>{e(clock.strftime("%a, %d %b %Y"))}</small>'
            f'<b class="bn-time">{e(clock.strftime("%H:%M"))}<span class="bn-sec">:{e(clock.strftime("%S"))}</span></b><small>SAST (UTC+2)</small></div>'
            f'<div>{chip}{updated}<small class="bn-countdown">{e(refresh)}</small></div></div></div>')


# Runs in a zero-height component frame: updates the header clock and the refresh countdown once a second on the
# visitor's device, aligned to the server's clock. It changes text only; it never contacts the server.
LIVE_CLOCK_JS = """<script>
(function () {
  var doc = window.parent.document, win = window.parent;
  if (win.__matatieleTimer) win.clearInterval(win.__matatieleTimer);
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  function tick() {
    var box = doc.querySelector('.bn-clock[data-now]');
    if (!box) return;
    if (!box.dataset.offset) box.dataset.offset = String(Number(box.dataset.now) - Date.now());
    var now = Date.now() + Number(box.dataset.offset), sast = new Date(now + 2 * 3600000);
    var time = box.querySelector('.bn-time');
    if (time) time.innerHTML = pad(sast.getUTCHours()) + ':' + pad(sast.getUTCMinutes()) + '<span class="bn-sec">:' + pad(sast.getUTCSeconds()) + '</span>';
    var count = box.querySelector('.bn-countdown');
    if (count && box.dataset.next) {
      var left = Math.round((Number(box.dataset.next) - now) / 1000);
      count.textContent = left > 0 ? 'Next refresh in ' + pad(Math.floor(left / 60)) + ':' + pad(left % 60) : 'Refreshing now';
    }
  }
  tick();
  win.__matatieleTimer = win.setInterval(tick, 1000);
})();
</script>"""


def sidebar_card_html():
    return ('<div class="side-card"><b>Protecting Matatiele through earlier warnings</b>'
            '<small>Smart · resilient · low-connectivity storm early warning</small></div>')


CHROME_CSS = """
:root {--banner-overlay:linear-gradient(90deg,rgba(13,48,110,.74),rgba(29,78,216,.30) 48%,rgba(29,78,216,.06))}
@media (prefers-color-scheme: dark) {:root {--banner-overlay:linear-gradient(90deg,rgba(6,16,32,.80),rgba(6,16,32,.40) 48%,rgba(6,16,32,.10))}}
.banner {display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1fr) auto;gap:18px;align-items:center;min-height:128px;max-height:160px;padding:14px 20px;border-radius:18px;color:#fff;margin:0 0 6px;
  background:var(--banner-overlay),url(BANNER_IMAGE) center 46%/cover;box-sizing:border-box}
.bn-brand {display:flex;gap:14px;align-items:center}.bn-brand>.ico {width:48px;height:48px;color:#bfdbfe}
.banner h1 {margin:0;color:#fff;font-size:clamp(21px,2.1vw,28px);line-height:1.12;font-weight:800;text-shadow:0 1px 3px #0006}.banner h1 span {display:block;font-size:.64em;font-weight:600}
.banner small {display:block;color:#e2ecff;font-size:12.5px;text-shadow:0 1px 2px #0006}
.bn-place b {display:flex;align-items:center;gap:6px;font-size:clamp(15px,1.5vw,20px);text-shadow:0 1px 3px #0006}.bn-place span {display:block;color:#e2ecff;font-size:13px}
.bn-clock {display:flex;gap:14px;align-items:center;background:#fff;color:#0b1f3a;border-radius:14px;padding:10px 14px;box-shadow:0 8px 24px #0004}
.bn-clock b {display:block;font-size:28px;line-height:1.1}.bn-clock small {color:#4a5b70;text-shadow:none}.bn-clock>div+div {border-left:1px solid #d9e1ec;padding-left:12px}
.bn-chip {display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:9px;font-weight:700;font-size:13px;margin-bottom:3px}
.bn-chip i {width:10px;height:10px;border-radius:50%}.bn-chip.ok {background:#dcfce7;color:#14532d}.bn-chip.ok i {background:#16a34a;animation:ring 2s ease-out infinite}.chip:not(.stale) .dot {animation:ring 2s ease-out infinite!important}
@keyframes ring {0%{box-shadow:0 0 0 0 rgba(22,163,74,.75)}80%{box-shadow:0 0 0 11px rgba(22,163,74,0)}100%{box-shadow:0 0 0 0 rgba(22,163,74,0)}}
.bn-chip.stale {background:#fef3c7;color:#713f12}.bn-chip.stale i {background:#d97706}.chip.stale .dot {animation:none}
.bn-updated {display:inline-block;margin:0 0 3px 6px;padding:2px 8px;border-radius:8px;background:#dbeafe;color:#1e3a8a;font-size:12px;font-weight:700;animation:fadeout 8s ease-out forwards}.bn-sec {font-size:.6em;color:#4a5b70}
.just-updated ~ * .summary-grid,.summary-grid.just-updated {animation:glow 2.4s ease-out 1}
@keyframes glow {0%{box-shadow:0 0 0 0 #16a34a66;border-radius:16px}100%{box-shadow:0 0 0 14px #16a34a00}}
@keyframes fadeout {0%,70%{opacity:1}100%{opacity:0}}
.side-card {margin-top:12px;border-radius:12px;padding:10px 12px;background:#ffffff14;color:var(--sidebar-text)}
.side-card b {display:block;font-size:13.5px}.side-card small {display:block;color:var(--sidebar-muted);font-size:12px}
.sc-title {font-size:16px!important;font-weight:800!important;text-transform:none!important;letter-spacing:0!important;color:var(--heading)!important;margin-bottom:2px!important}
.sc-title .ico {width:22px;height:22px;color:var(--accent)}.sc-sub {display:block;font-size:12.5px;font-weight:500;color:var(--muted);margin:0 0 6px}
.summary-card {padding:10px 13px!important}.risk-dial {max-width:240px!important;overflow:hidden}
@property --g {syntax:'\\3C number>';inherits:false;initial-value:0}  /* \\3C is '<', escaped: the HTML sanitiser drops a style block containing '<' followed by a letter */
.risk-track,.risk-arc {position:absolute;left:5.4545%;top:11.29%;width:89.0909%;aspect-ratio:1;border-radius:50%;-webkit-mask:radial-gradient(farthest-side,transparent 79.3%,#000 79.8%);mask:radial-gradient(farthest-side,transparent 79.3%,#000 79.8%)}
.risk-track {background:conic-gradient(from 270deg,#c7d2e0 0 180deg,transparent 0)}
.risk-arc {--g:var(--to);background:conic-gradient(from 270deg,var(--arc) 0 calc(var(--g) * 180deg),transparent 0)}
.risk-arc.animate {animation:sweep 1.4s ease-out both}@keyframes sweep {from{--g:var(--from)}to{--g:var(--to)}}
.risk-gauge-img {position:relative}
.kpi {padding:10px 14px!important;min-height:0!important}.st-key-outlook_card,.st-key-six_hour_chart {padding-top:2px}.risk-note,.risk-meta {margin-top:4px!important}
.wx-summary {background:var(--card)!important;color:var(--text)!important;border:1px solid var(--card-border)!important}
.wx-summary .sc-title,.wx-summary .sc-foot {color:var(--muted)}.wx-summary .sc-value {color:var(--heading)!important}
.wx-stats span {background:var(--accent-soft)!important}.wx-stats b {color:var(--heading)!important}.wx-stats small {color:var(--muted)!important}.wx-stats .ico {color:var(--accent)!important}
.chart-legend {display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12.5px;color:var(--muted);margin:0 0 4px}.chart-legend i {display:inline-block;width:14px;height:10px;border-radius:3px;margin-right:6px;vertical-align:middle}
.chart-legend .dash {height:0;border-top:3px dashed #d93449;border-radius:0}.chart-legend b {color:var(--heading);font-weight:700}
.advice-grid.compact {grid-template-columns:repeat(5,minmax(0,1fr))!important;gap:8px!important}.advice-grid.compact .advice-card {padding:10px!important}
.advice-grid.compact .advice-card p {font-size:12.5px;margin:4px 0 0}.advice-card {padding:12px 14px!important}
body:has([data-testid=stSidebar][aria-expanded="true"]) .st-key-top_nav_bar {display:none}  /* the open side menu has every section */
/* Streamlit versions differ: some mark the open sidebar with aria-expanded, others (e.g. Community Cloud's) with data-collapsed. */
body:has([data-testid=stSidebar][data-collapsed="false"]) .st-key-top_nav_bar,
body:has([data-testid=stSidebar][data-collapsed="false"]) [data-testid=stLayoutWrapper]:has(> .st-key-top_nav_bar) {display:none}
/* Side-menu download button (phone drawer): the same look as the other side-menu entries, readable on the dark menu. */
[data-testid=stSidebar] [data-testid=stDownloadButton] button {background:transparent!important;border:1px solid rgba(255,255,255,.35)!important;color:var(--sidebar-text,#e8f1fb)!important}
[data-testid=stSidebar] [data-testid=stDownloadButton] button p,[data-testid=stSidebar] [data-testid=stDownloadButton] button [data-testid=stIconMaterial] {color:inherit!important}
@media (max-width:1100px) {.banner {grid-template-columns:1fr auto}.bn-place {display:none}.advice-grid.compact {grid-template-columns:repeat(3,minmax(0,1fr))!important}}
@media (max-width:640px) {
  .banner {grid-template-columns:1fr;min-height:0;max-height:none;padding:10px 12px;gap:8px;background:var(--banner-overlay),url(BANNER_IMAGE_SMALL) center 46%/cover}
  .banner h1 {font-size:19px}.bn-brand small {display:none}.bn-brand>.ico {width:32px;height:32px}
  .bn-clock {padding:6px 10px;gap:10px}.bn-clock b {font-size:18px}.bn-sec {display:none}.bn-clock small {font-size:11px}.bn-chip {font-size:12px;padding:2px 8px}
  .status-strip {display:none}  /* the banner already shows the system status */
  .st-key-top_nav_bar button {padding:6px 8px!important;font-size:13px!important;min-height:36px!important}.st-key-top_nav_bar [data-testid=stButtonGroup] > div {gap:2px!important;flex-wrap:nowrap!important}
  .decision-summary .sc-sub,.risk-summary .sc-sub {display:none}
  .summary-card {padding:8px 10px!important}.risk-dial {max-width:180px!important}.risk-value {font-size:38px!important}
  .decision-badge {padding:9px 12px!important;font-size:15px!important;margin:2px 0 6px!important}.decision-summary .sc-foot {display:none}
  .wx-now img {width:46px;height:46px}.sc-value {font-size:26px!important}.period-row {margin:4px 0!important}
  .comm-tile {padding:6px 8px!important}.var-grid {gap:8px 12px!important}.var-tile b {font-size:16px!important}
  .advice-grid.compact {grid-template-columns:repeat(2,minmax(0,1fr))!important}.advice-card {padding:10px 12px!important}
  .st-key-home_actions [data-testid=stHorizontalBlock] {flex-wrap:wrap!important;gap:8px!important}
  .st-key-home_actions [data-testid=stColumn] {flex:1 1 calc(50% - 8px)!important;min-width:calc(50% - 8px)!important;width:calc(50% - 8px)!important}
}
/* Zero-height helpers (clock and connection scripts, the phone navigation) take no space in the page flow. */
[data-testid=stElementContainer]:has(> iframe[data-testid=stIFrame]),[data-testid=stLayoutWrapper]:has(> .st-key-bottom_nav) {position:absolute!important}
/* Phones: fixed bottom navigation instead of the top bar and side menu (tablets and desktop keep those). */
.st-key-bottom_nav,.st-key-menu_phone_extras {display:none!important}
@media (max-width:640px) {
  /* Menu (hamburger) drawer on phones: secondary pages and tools only; Home, Risk Analysis, Map and Safety are bottom tabs. */
  [data-testid=stSidebar] .st-key-menu_Dashboard,[data-testid=stSidebar] .st-key-menu_Risk-Analysis,[data-testid=stSidebar] .st-key-menu_Map,
  [data-testid=stSidebar] .st-key-menu_Safety {display:none!important}
  .st-key-menu_phone_extras {display:flex!important}
  .st-key-top_nav_bar,[data-testid=stLayoutWrapper]:has(> .st-key-top_nav_bar),[data-testid=stElementContainer]:has(.status-strip) {display:none!important}
  .st-key-bottom_nav {display:flex!important;position:fixed!important;left:0;right:0;bottom:var(--platform-clearance,0px);z-index:999990;margin:0!important;width:100%!important;
    background:var(--card);border-top:1px solid var(--card-border);box-shadow:0 -4px 18px rgba(15,23,42,.14);padding:4px 4px calc(4px + env(safe-area-inset-bottom))!important}
  .st-key-bottom_nav [data-testid=stHorizontalBlock] {flex-wrap:nowrap!important;gap:2px!important;width:100%}
  .st-key-bottom_nav [data-testid=stColumn] {flex:1 1 0!important;min-width:0!important;width:auto!important}
  .st-key-bottom_nav button {min-height:54px!important;width:100%!important;padding:4px 2px!important;border-radius:12px!important;border:0!important;position:relative;
    background:transparent!important;color:var(--muted)!important;box-shadow:none!important}
  .st-key-bottom_nav button > div {flex-direction:column!important;gap:1px!important;justify-content:center!important}
  .st-key-bottom_nav button p {font-size:12px!important;font-weight:700!important;white-space:nowrap!important;margin:0!important;color:inherit!important}
  .st-key-bottom_nav button [data-testid=stIconMaterial] {font-size:23px!important;margin:0!important;color:inherit!important}
  .st-key-bottom_nav button[kind=primary] {background:#1d4ed8!important;color:#fff!important}
  .st-key-bottom_nav button[kind=primary] p,.st-key-bottom_nav button[kind=primary] [data-testid=stIconMaterial] {color:#fff!important}
  .st-key-bottom_nav button:focus-visible {outline:3px solid var(--accent)!important;outline-offset:-3px}
  .st-key-bottom_nav [data-testid=stPopoverButton] div[aria-hidden="true"] {display:none!important}  /* no dropdown chevron */
  .st-key-bnav_more_alert button::after {content:'';position:absolute;top:7px;right:calc(50% - 18px);width:11px;height:11px;border-radius:50%;background:#dc2626;border:2px solid var(--card)}
  [data-testid=stMainBlockContainer],.block-container {padding-bottom:calc(104px + var(--platform-clearance,0px) + env(safe-area-inset-bottom))!important}  /* last content never hidden */
  .st-key-home_actions [data-testid=stColumn]:has(.st-key-home_safety) {display:none!important}  /* Safety is a bottom tab on phones */
}
@media (prefers-reduced-motion: reduce) {.bn-chip.ok i,.chip .dot,.chip:not(.stale) .dot,.bn-updated,.summary-grid.just-updated,.risk-arc.animate {animation:none!important}}
""".replace('BANNER_IMAGE_SMALL', BANNER_IMAGE_SMALL).replace('BANNER_IMAGE', BANNER_IMAGE)


def status_strip(stale, updated, simulated, refresh_minutes=15):
    """Chips for data freshness and mode. `updated` is a preformatted SAST time or None."""
    e = html.escape
    if stale:
        fresh = f'<span class="chip stale"><span class="dot"></span><b>Outdated data</b> &middot; last update {e(updated or "unknown")}</span>'
    else:
        fresh = f'<span class="chip" title="Refreshes every {int(refresh_minutes)} minutes while open"><span class="dot"></span><b>Live forecast data</b></span>'
    chips = [fresh, '<span class="chip">ECMWF forecast &rarr; Random Forest risk score &rarr; 35% decision</span>']
    if simulated:
        chips.insert(0, '<span class="chip sim"><b>SIMULATION ON</b> &middot; on screen only</span>')
    return '<div class="status-strip">' + ''.join(chips) + '</div>'


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


def flow_html(sms_mode='disabled'):
    """The resident-facing warning workflow in one line: external forecast -> Random Forest -> 35% decision ->
    warning information -> SMS. SMS is optional and labelled with its real state. (The officials' portal is a
    separate interface and is not part of this explanation.)"""
    e = html.escape
    arrow = f'<span class="arrow" aria-hidden="true">{icons.icon("arrow-right")}</span>'
    sms_badge = {'twilio': 'Optional · configured', 'outbox': 'Optional · development outbox, nothing sent'}.get(sms_mode, 'Optional · not enabled')

    def step(name, title, detail, badge='', optional=False):
        tag = f'<span class="badge {"opt" if optional else "on"}">{e(badge)}</span>' if badge else ''
        return (f'<div class="step{" optional" if optional else ""}">{icons.icon(name, size="22px")}'
                f'<div><b>{e(title)}</b><small>{e(detail)}</small>{tag}</div></div>')
    steps = [step('radar', 'External forecast', 'ECMWF via Open-Meteo, hourly'),
             step('cpu', 'Random Forest', 'Model-estimated storm risk'),
             step('scale', '35% warning decision', 'Estimate at or above 35%'),
             step('siren', 'Warning information', 'Alerts page and public record'),
             step('message', 'SMS communication', 'Only when enabled and configured', sms_badge, sms_mode != 'twilio')]
    return f'<div class="flow"><div class="lane-steps">{arrow.join(steps)}</div></div>'


def explainer_html(steps):
    """Numbered steps: (title, text)."""
    e = html.escape
    items = ''.join(f'<li><b>{e(title)}</b> {e(text)}</li>' for title, text in steps)
    return f'<ol class="explainer">{items}</ol>'


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
    return (CSS + CHROME_CSS).replace('@media (prefers-color-scheme: dark)', switch) + icons.CSS + tones


def style_chart(chart, mode):
    """Altair chart colours for the selected theme (transparent background, readable axes)."""
    colours = CHART_COLORS[mode]
    return (chart.configure(background='transparent').configure_view(stroke=None)
            .configure_axis(labelColor=colours['text'], titleColor=colours['text'], gridColor=colours['grid'],
                            domainColor=colours['grid'], tickColor=colours['grid'])
            .configure_legend(labelColor=colours['text'], titleColor=colours['text']))


def system_log_html(rows):
    """System log rows (timestamp, severity, delivery, status) as a table with severity badges."""
    e = html.escape
    body = ''.join(f'<tr><td>{e(at)}</td><td><span class="sev sev-{e(severity.lower())}">{e(severity)}</span></td>'
                   f'<td>{e(delivery)}</td><td>{e(status)}</td></tr>' for at, severity, delivery, status in rows)
    body = body or '<tr><td colspan="4">No events recorded yet.</td></tr>'
    return ('<div class="dtable-wrap"><table class="dtable syslog"><thead><tr><th scope="col">Timestamp (SAST)</th><th scope="col">Severity</th>'
            f'<th scope="col">Delivery method</th><th scope="col">Status</th></tr></thead><tbody>{body}</tbody></table></div>')


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


# Installed once in the dashboard page itself (not in the component frame), so it keeps working when the server
# connection drops. It never claims a restored connection: live data return only through a successful retrieval.
CONNECTION_WATCH = r"""
(function () {
  if (window.__matatieleWatch) return; window.__matatieleWatch = 1;
  var d = document;
  var bar = d.createElement('div');
  bar.id = 'connection-lost'; bar.setAttribute('role', 'alert');
  bar.style.cssText = 'position:fixed;left:8px;right:8px;top:8px;z-index:2147483000;display:none;flex-wrap:wrap;gap:6px 12px;align-items:center;' +
    'background:#7c2d12;color:#fff;border:2px solid #fdba74;border-radius:12px;padding:10px 12px;font:600 14px/1.4 system-ui,Segoe UI,sans-serif;box-shadow:0 6px 24px rgba(0,0,0,.35)';
  bar.innerHTML = '<b style="font-size:15px">Connection lost — live updates paused</b>' +
    '<span style="font-weight:500">The information on screen is the last received. New forecasts and warnings need a connection.</span>' +
    '<button type="button" style="font:700 14px system-ui,sans-serif;background:#fff;color:#7c2d12;border:0;border-radius:9px;padding:9px 12px;min-height:44px;cursor:pointer">Open saved offline dashboard</button>';
  d.body.appendChild(bar);
  function openSaved() {
    var page = window.__matatieleOffline;
    if (!page) { bar.querySelector('span').textContent = 'No saved offline dashboard is available in this page yet.'; return; }
    var old = d.getElementById('saved-offline-view'); if (old) old.remove();
    var view = d.createElement('div');
    view.id = 'saved-offline-view';
    view.style.cssText = 'position:fixed;inset:0;z-index:2147483001;background:#f5f7fb;display:flex;flex-direction:column';
    var url = URL.createObjectURL(new Blob([page], {type: 'text/html'}));
    view.innerHTML = '<div style="display:flex;gap:8px;align-items:center;justify-content:space-between;padding:8px 10px;background:#1e3a8a;color:#fff;font:600 14px system-ui,sans-serif">' +
      '<button type="button" style="font:700 14px system-ui,sans-serif;background:#fff;color:#1e3a8a;border:0;border-radius:9px;padding:8px 12px;min-height:44px">Back to live dashboard</button>' +
      '<a style="color:#fff;font-weight:700" download="matatiele-storm-info.html">Save a copy</a></div>';
    view.querySelector('a').href = url;
    var frame = d.createElement('iframe');
    frame.title = 'Saved offline dashboard'; frame.style.cssText = 'flex:1;border:0;width:100%;background:#f5f7fb';
    frame.srcdoc = page;
    view.appendChild(frame);
    view.querySelector('button').onclick = function () { view.remove(); };
    d.body.appendChild(view);
  }
  bar.querySelector('button').onclick = openSaved;
  // Streamlit Community Cloud draws its own floating controls (hosting badge, creator avatar) over the bottom-right of the
  // app. They are left exactly as they are: on phones, the bottom navigation is lifted just clear of them, and only while
  // they are present (measured in the hosting page). Elsewhere, and on wider screens, the lift is 0.
  function platformClearance() {
    if (!/\.streamlit\.app$/.test(location.hostname) || innerWidth > 640 || window.parent === window) return 0;
    var shell, frame;
    try {
      shell = window.parent.document;
      frame = Array.prototype.find.call(shell.querySelectorAll('iframe'), function (f) { return f.contentWindow === window; });
    } catch (e) { return 0; }
    if (!frame) return 0;
    var fr = frame.getBoundingClientRect(), top = Infinity;
    for (var x = fr.left + 4; x < fr.right; x += 20) {
      for (var y = fr.bottom - 2; y > fr.bottom - 90; y -= 10) {
        shell.elementsFromPoint(x, y).forEach(function (e) {
          if (e === frame || e.contains(frame)) return;
          var r = e.getBoundingClientRect();
          if (r.width > 0 && r.height > 0 && r.height < 120) top = Math.min(top, r.top);
        });
      }
    }
    return top === Infinity ? 0 : Math.max(0, Math.ceil(fr.bottom - top) + 6);
  }
  function applyClearance() {
    var px = platformClearance() + 'px';
    if (d.documentElement.style.getPropertyValue('--platform-clearance') !== px) d.documentElement.style.setProperty('--platform-clearance', px);
  }
  applyClearance(); window.addEventListener('resize', applyClearance); setInterval(applyClearance, 3000);
  // Phone menu (hamburger) drawer: closes after a choice, on a tap outside it, and with Escape.
  function drawer() {
    var s = d.querySelector('[data-testid=stSidebar]');
    var open = s && (s.getAttribute('aria-expanded') === 'true' || s.getAttribute('data-collapsed') === 'false');  // both Streamlit variants
    return open && innerWidth <= 640 ? s : null;
  }
  function closeDrawer() {
    var b = d.querySelector('[data-testid=stSidebarCollapseButton] button') || d.querySelector('[data-testid=stSidebarCollapseButton]');
    if (b) b.click();
  }
  d.addEventListener('click', function (e) {
    var s = drawer(); if (!s) return;
    if (!s.contains(e.target)) { if (!e.target.closest('[data-testid=stExpandSidebarButton]')) closeDrawer(); return; }
    var b = e.target.closest('button');
    if (b && b.closest('[class*="st-key-menu_"]')) setTimeout(closeDrawer, 250);
  }, true);
  d.addEventListener('keydown', function (e) { if (e.key === 'Escape' && drawer()) closeDrawer(); });
  d.addEventListener('click', function (e) {
    var b = e.target.closest && e.target.closest('[data-testid=stPopoverBody] button');
    if (b) setTimeout(function () { d.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', keyCode: 27, bubbles: true})); }, 150);
  }, true);
  function update() { bar.style.display = navigator.onLine === false ? 'flex' : 'none'; }
  window.addEventListener('offline', update); window.addEventListener('online', update); update();
})();
"""


def connection_watch_html(offline_page_html):
    """Component frame content: keeps the page's saved offline dashboard up to date and installs CONNECTION_WATCH once."""
    import json
    safe = lambda text: json.dumps(text).replace('</', '<\\/')  # noqa: E731  (cannot close the script element)
    return ('<script>(function(){var w=window.parent,d;try{d=w.document;}catch(e){return;}'
            f'var page={safe(offline_page_html or "")};if(page)w.__matatieleOffline=page;'
            'if(!w.__matatieleWatch){var s=d.createElement("script");s.textContent=' + safe(CONNECTION_WATCH) + ';d.head.appendChild(s);}'
            '})();</script>')
