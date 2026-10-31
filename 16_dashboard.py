"""Matatiele Smart Resilient Storm Early Warning System — research beta dashboard.
Forecast-driven interface; no SMS is sent on page load or in presentation mode.
"""
from pathlib import Path
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from typing import Any, cast
import os
import hmac
import hashlib
import subprocess
import sys
import html
import requests
import math
import base64
import io
import threading
import time
import tempfile
import logging
import json
import numpy as np
from PIL import Image, ImageFilter

import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
import pydeck as pdk
from pydeck.types import String
from app_config import get_setting
from forecast_timing import (local_time, six_hour_forecast, forecast_axis_order,
                             interval_label, timestamp_labels, next_complete_hour_endpoint,
                             is_next_complete_prediction,
                             TARGET_LABEL, GENERATED_LABEL)
from sms_alert import sms_is_configured, send_test_sms
from subscriptions import delivery_mode
import model_evidence
import offline_page
import outlook as storm_outlook
import system_log
import prediction_log as run_log
import resident_view
import dashboard_theme
import resident_pages
import resident_alerts
import official_portal
import emergency_contacts
import warning_events

BASE = Path(__file__).resolve().parent
MODEL = BASE / 'outputs' / 'model_live'
# Separate result prevents dashboard selection from overwriting the SMS worker's input.
PRED = MODEL / 'dashboard_forecast_prediction.csv'
HISTORY = MODEL / 'prediction_history.csv'
THRESHOLD = MODEL / 'live_selected_threshold.txt'
LIVE_SCRIPT = BASE / '12_live_forecast_and_predict.py'
SMS_LOG = MODEL / 'sms_alert_log.csv'
SAST = ZoneInfo('Africa/Johannesburg')
MATATIELE_LAT, MATATIELE_LON = -30.3436, 28.8116
# Town centres are geographic references, never additional model predictions.
# Sources: Mapcarta / OpenStreetMap town nodes (Cedarville 262704622,
# Maloti 2282707579, Qacha's Nek 4654350286); Mount Fletcher Wikidata Q3643045.
# Screen-space label offsets separate nearby names without moving coordinates.
NEARBY_PLACES=[
    {'name':'Cedarville','lat':-30.38657,'lon':29.04144,'offset':[12,38],'anchor':'start'},
    {'name':'Mount Fletcher','lat':-30.691944,'lon':28.503056,'offset':[-12,4],'anchor':'end'},
    {'name':'Maluti (Maloti)','lat':-30.26257,'lon':28.79194,'offset':[-12,-20],'anchor':'end'},
    {'name':"Qacha's Nek",'lat':-30.11333,'lon':28.68110,'offset':[12,-14],'anchor':'start'},
]
REGIONAL_FILE = MODEL / 'regional_ecmwf_forecast.csv'
REFRESH_SECONDS = 15 * 60
MIN_MANUAL_SECONDS = 60
SATELLITE_STYLE={
    'version':8,
    'sources':{
        'imagery':{'type':'raster','tiles':['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],'tileSize':256,'attribution':'Tiles © Esri · Earthstar Geographics'},
        # Transparent, zoom-dependent reference tiles designed for dark imagery.
        # Shared by both map views; no weather data or model output is changed.
        'place_reference':{'type':'raster','tiles':['https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}'],
            'tileSize':256,'minzoom':0,'maxzoom':23,
            'attribution':'Labels © Esri, HERE, Garmin, OpenStreetMap contributors, GIS user community'}},
    'layers':[{'id':'satellite','type':'raster','source':'imagery'},
              {'id':'geographic-reference','type':'raster','source':'place_reference'}]}
SATELLITE_STYLE_URL='data:application/json;base64,'+base64.b64encode(json.dumps(SATELLITE_STYLE).encode()).decode()
STREETS_STYLE={'version':8,'sources':{'streets':{'type':'raster','tiles':['https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}'],
    'tileSize':256,'attribution':'Tiles © Esri, HERE, Garmin, OpenStreetMap contributors'}},'layers':[{'id':'streets','type':'raster','source':'streets'}]}
# Low-data basemap: no tiles are downloaded; only the forecast overlay and labels are drawn.
LOW_DATA_STYLE={'version':8,'sources':{},'layers':[{'id':'background','type':'background','paint':{'background-color':'#d9e6f2'}}]}
BASEMAPS={name:'data:application/json;base64,'+base64.b64encode(json.dumps(style).encode()).decode()
          for name,style in (('Satellite',SATELLITE_STYLE),('Streets',STREETS_STYLE),('Low data',LOW_DATA_STYLE))}
# Inline so it is identical in both themes and in the text view (which loads no stylesheet).
SIM_BANNER_STYLE='background:#4a0f6b;color:#ffffff;border:3px solid #ffd23f;border-radius:10px;padding:12px 16px;font-weight:700;font-size:14px;line-height:1.5'
# ?view=text: minimal low-data page. ?admin=1: show the administrator login (password still required).
text_view=st.query_params.get('view','')=='text'
show_admin_login=st.query_params.get('admin','')=='1'
st.set_page_config(page_title='Matatiele | Storm Early Warning Research', page_icon=':material/thunderstorm:', layout='centered' if text_view else 'wide',
                   initial_sidebar_state='locked')  # always open on desktop with every section; behind ☰ on narrow screens

# Theme: light or dark, chosen with the header switch and applied to every page and the officials' portal.
# Order: this session's choice, the ?theme= link (kept on refresh), the choice remembered in this browser,
# then the device setting. Not loaded in the text view.
THEMES=('light','dark')
_browser_prefs=components.declare_component('browser_prefs',path=str(BASE/'components'/'browser_prefs'))

def resolve_theme(prefs: Any) -> str:
    if st.session_state.get('theme') in THEMES:return st.session_state.theme
    if st.query_params.get('theme') in THEMES:return st.query_params['theme']
    prefs=prefs if isinstance(prefs,dict) else {}
    if prefs.get('theme') in THEMES:return prefs['theme']
    return 'dark' if prefs.get('dark') is True else 'light'

def toggle_theme() -> None:
    st.session_state.theme='dark' if st.session_state.theme_switch else 'light'
    st.query_params['theme']=st.session_state.theme

prefs=None
if not text_view:
    with st.container(key='browser_prefs'):
        try:prefs=_browser_prefs(key='browser_prefs_value',theme=st.session_state.get('theme'),default=None)
        except Exception:prefs=None  # components unavailable: the link or the default decides
theme_mode=resolve_theme(prefs)
if not text_view:st.html('<style>'+dashboard_theme.theme_css(theme_mode)+'</style>')

def secret(name):
    return get_setting(name)

def run_prediction() -> bool:
    """Run only inference: this script imports no SMS module."""
    if not LIVE_SCRIPT.exists():return False
    try:
        result=subprocess.run([sys.executable,str(LIVE_SCRIPT),'--dashboard-next-hour'],cwd=BASE,
                              capture_output=True,text=True,timeout=150)
        if result.returncode:
            logging.error('ECMWF inference failed (exit %s); saved prediction retained.',result.returncode)
            return False
        return True
    except (OSError,subprocess.SubprocessError):
        logging.exception('ECMWF inference could not complete.')
        return False

def atomic_csv(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',suffix='.csv',dir=destination.parent,
                                     encoding='utf-8',newline='',delete=False) as handle:
        temporary=Path(handle.name)
        try:frame.to_csv(handle,index=False)
        except Exception:
            handle.close();temporary.unlink(missing_ok=True);raise
    try:os.replace(temporary,destination)
    finally:temporary.unlink(missing_ok=True)

class RefreshState:
    def __init__(self):
        self.lock=threading.Lock()
        self.last_attempt: datetime | None=None
        self.prediction_error=''
        self.regional_error=''
        self.history_error=''
        self.regional=pd.DataFrame()
        try:
            if REGIONAL_FILE.exists():
                saved=pd.read_csv(REGIONAL_FILE)
                required={'forecast_hour','precipitation_mm','sample_id','lat','lon','forecast_retrieved_at','cloud_cover'}
                if required.issubset(saved.columns):self.regional=saved
        except (OSError,ValueError):pass

@st.cache_resource
def refresh_state() -> RefreshState:
    return RefreshState()

LOGIN_WINDOW_SECONDS,MAX_FAILED_LOGINS=900,10

@st.cache_resource
def failed_logins() -> list[float]:
    # Shared by every session of this server process: a new browser session cannot reset it.
    return []

@st.cache_resource
def failed_official_logins() -> list[float]:
    return []

def refresh_due(state: RefreshState, now: datetime, force: bool=False) -> bool:
    if state.last_attempt is None:return True
    elapsed=(now-state.last_attempt).total_seconds()
    if force:return elapsed>=MIN_MANUAL_SECONDS
    hour_changed=now.replace(minute=0,second=0,microsecond=0)!=state.last_attempt.replace(minute=0,second=0,microsecond=0)
    return elapsed>=REFRESH_SECONDS or (hour_changed and elapsed>=MIN_MANUAL_SECONDS)

def refresh_sources(force: bool=False) -> RefreshState:
    """One process-wide refresh cycle; failures retain the last genuine files."""
    state=refresh_state()
    if not state.lock.acquire(blocking=False):return state
    try:
        if not refresh_due(state,datetime.now(SAST),force):return state
        state.last_attempt=datetime.now(SAST)
        state.prediction_error='' if run_prediction() else 'Latest ECMWF/model refresh failed.'
        if not state.prediction_error:
            try:
                new=pd.read_csv(PRED)
                existing=pd.read_csv(HISTORY) if HISTORY.exists() else pd.DataFrame()
                combined=pd.concat([existing,new],ignore_index=True)
                combined=combined.drop_duplicates(subset=['prediction_for'],keep='last')
                atomic_csv(combined,HISTORY)
                state.history_error=''
            except (OSError,ValueError,KeyError):
                state.history_error='Prediction refreshed, but history could not be saved.'
        try:
            regional=fetch_regional_forecast()
            atomic_csv(regional,REGIONAL_FILE)
            state.regional=regional
            state.regional_error=''
        except (requests.RequestException,OSError,ValueError,KeyError,TypeError):
            state.regional_error='Latest regional ECMWF retrieval failed; saved samples may be outdated.'
        return state
    finally:state.lock.release()

@st.fragment(run_every='60s')
def refresh_clock():
    # Trigger a full render so expiry labels and every data product update together.
    count=st.session_state.get('refresh_clock_count',0)
    st.session_state.refresh_clock_count=count+1
    if count:st.rerun()
    # Refresh clock renders no visible element; provenance lives in the sidebar.

def number(row,key,default=float("nan")):
    try:
        v=float(row.get(key,default))
        return v if math.isfinite(v) else default
    except (ValueError,TypeError):return default

def numeric_series(values: pd.Series) -> pd.Series:
    """Keep numeric column conversion a Series for pandas and type checkers."""
    return pd.Series(pd.to_numeric(values,errors='coerce'),index=values.index,dtype='float64')

def weather_value(value: float, unit: str, precision: int=1) -> str:
    return f'{value:.{precision}f} {unit}' if math.isfinite(value) else 'Unavailable'

def risk(prob, threshold):
    if not math.isfinite(prob) or not 0 <= prob <= 1:return 'UNAVAILABLE','#68798d'
    if prob>=threshold:return 'WARNING','#d93449'
    if prob>=.20:return 'MODERATE','#e87932'
    if prob>=.10:return 'ELEVATED','#b78711'
    return 'LOW','#17985a'

def fetch_regional_forecast() -> pd.DataFrame:
    """26 real ECMWF locations: 25 regional samples and Matatiele itself."""
    points=[(a,b) for a in [-31.0,-30.7,-30.4,-30.1,-29.8]
                    for b in [28.1,28.45,28.8,29.15,29.5]]
    points.append((MATATIELE_LAT,MATATIELE_LON))
    params={'latitude':','.join(str(a) for a,b in points),
            'longitude':','.join(str(b) for a,b in points),
            'hourly':'precipitation,cloud_cover,temperature_2m,wind_speed_10m,wind_gusts_10m',
            'forecast_days':2,'timezone':'UTC','models':'ecmwf_ifs025',
            'wind_speed_unit':'ms','precipitation_unit':'mm'}
    response=requests.get('https://api.open-meteo.com/v1/forecast',params=params,timeout=(10,45))
    response.raise_for_status()
    payload=response.json()
    if not isinstance(payload,list) or len(payload)!=len(points):
        raise ValueError('Incomplete ECMWF regional response')
    retrieved=datetime.now(UTC).isoformat()
    frames=[]
    for index,site in enumerate(payload):
        if site.get('hourly_units',{}).get('precipitation')!='mm':
            raise ValueError('Unexpected precipitation units')
        frame=pd.DataFrame(site['hourly'])
        frame['forecast_hour']=pd.to_datetime(frame.pop('time'),utc=True,errors='coerce')
        frame['precipitation_mm']=numeric_series(pd.Series(frame.pop('precipitation')))
        # Use returned forecast grid coordinates rather than pretending each request
        # was measured at its exact requested coordinate.
        frame['lat']=float(site['latitude']);frame['lon']=float(site['longitude'])
        frame['sample_id']=index
        frame['forecast_retrieved_at']=retrieved
        frame['source']='ECMWF IFS 0.25° / Open-Meteo'
        frames.append(frame)
    combined=pd.concat(frames,ignore_index=True)
    future=pd.DataFrame(combined.loc[combined['forecast_hour']>datetime.now(UTC)])
    if future.empty:raise ValueError('No future ECMWF samples')
    target=next_complete_hour_endpoint(datetime.now(UTC))
    select=pd.DataFrame(future.loc[future['forecast_hour']==target])
    if len(select)!=26 or not np.isfinite(select['precipitation_mm']).all() or (select['precipitation_mm']<0).any():
        raise ValueError('Missing or invalid upcoming regional precipitation')
    return combined

def regional_hours(frame: pd.DataFrame, count: int=36) -> list[pd.Timestamp]:
    """Upcoming hourly endpoints (UTC) for which all 25 genuine ECMWF samples exist."""
    if frame.empty:return []
    values=frame.loc[frame['sample_id']<25].copy()
    values['forecast_hour']=pd.to_datetime(values['forecast_hour'],utc=True,errors='coerce')
    first=next_complete_hour_endpoint(datetime.now(UTC))
    counts=values.loc[values['forecast_hour']>=first].groupby('forecast_hour')['sample_id'].nunique()
    return [hour for hour,n in counts.items() if n==25][:count]

def upcoming_regional(frame: pd.DataFrame, target: pd.Timestamp | None=None) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    if frame.empty:return pd.DataFrame(),None
    values=frame.copy()
    values['forecast_hour']=pd.to_datetime(values['forecast_hour'],utc=True,errors='coerce')
    target=target if target is not None else next_complete_hour_endpoint(datetime.now(UTC))
    values=pd.DataFrame(values.loc[(values['forecast_hour']==target) & (values['sample_id']<25)])
    if values.empty:return pd.DataFrame(),None
    if len(values)!=25 or values['sample_id'].nunique()!=25:return pd.DataFrame(),None
    values['name']=values.apply(lambda row:f"ECMWF sample: {float(row['precipitation_mm']):.2f} mm",axis=1)
    valid_time=target.tz_convert(SAST)
    return values,valid_time if isinstance(valid_time,pd.Timestamp) else None

def make_rainfall_overlay(regional):
    """Local bilinear interpolation on returned ECMWF coordinates, not radar."""
    grid=regional.pivot(index='lat',columns='lon',values='precipitation_mm').sort_index().sort_index(axis=1)
    values=grid.to_numpy(dtype=float)
    if min(grid.shape)<2 or not np.isfinite(values).all() or (values<0).any():
        raise ValueError('Incomplete or invalid ECMWF grid')
    source_lat=grid.index.to_numpy(dtype=float)
    source_lon=grid.columns.to_numpy(dtype=float)
    west,east=float(source_lon[0]),float(source_lon[-1])
    south,north=float(source_lat[0]),float(source_lat[-1])
    width,height=360,320
    lons=np.linspace(west,east,width,retstep=False)
    # Match the basemap's Web Mercator pixel rows rather than linear latitude.
    mercator=np.log(np.tan(np.pi/4+np.deg2rad([north,south])/2))
    lats=np.rad2deg(2*np.arctan(np.exp(np.linspace(float(mercator[0]),float(mercator[1]),height,retstep=False)))-np.pi/2)
    rows=np.stack([np.interp(lons,source_lon,row) for row in values])
    rainfall=np.stack([np.interp(lats,source_lat,rows[:,column]) for column in range(width)],axis=1)
    # Storm-map palette (as on nowcasting maps): transparent when dry; blue, green, yellow, orange, red as rain intensifies.
    stops=np.array([0,0.1,1,3,5,10,20,40],dtype=float)
    colors=np.array([[60,120,230,0],[60,120,230,120],[40,140,240,170],
                     [40,190,110,190],[120,200,60,200],[250,205,50,215],
                     [245,110,40,225],[190,30,50,240]],dtype=float)
    rgba=np.stack([np.interp(rainfall,stops,colors[:,c]) for c in range(4)],axis=2)
    # Fade out towards the edge of the sampled area (no data beyond it), so it does not read as a hard rectangle.
    fade_y=np.clip(np.minimum(np.arange(height),np.arange(height)[::-1])/(height*.18),0,1)
    fade_x=np.clip(np.minimum(np.arange(width),np.arange(width)[::-1])/(width*.18),0,1)
    rgba[:,:,3]*=np.outer(fade_y,fade_x)
    # Soft edges: the source grid is coarse (about 0.25 degrees), so sharp pixels would suggest radar detail that does not exist.
    out=Image.frombytes('RGBA',(int(rgba.shape[1]),int(rgba.shape[0])),np.clip(rgba,0,255).astype('uint8').tobytes()).filter(ImageFilter.GaussianBlur(5))
    buf=io.BytesIO()
    out.save(buf,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode('ascii'),[west,south,east,north]

def load_history():
    try:
        if HISTORY.exists():return pd.read_csv(HISTORY)
    except Exception:pass
    return pd.DataFrame()

@st.cache_data(ttl=600,show_spinner=False)
def worker_run_log(repo: str) -> tuple[pd.DataFrame, bool]:
    """The hourly worker's published run records (public [RUN-LOG] issue). Returns (rows, reachable)."""
    try:return run_log.worker_frame(run_log.fetch_records(repo)),True
    except Exception:return pd.DataFrame(columns=run_log.COLUMNS),False

def model_runs() -> tuple[pd.DataFrame, bool]:
    """Every saved output of the trained model: worker records, plus the dashboard's own runs for other hours."""
    worker,reachable=worker_run_log(resident_pages.LEDGER_REPO)
    runs=run_log.combine(worker,hist)
    weather=[c for c in ('precipitation_mm','temperature_c','wind_gust_ms') if c in hist.columns]
    if weather and not runs.empty:  # the dashboard's runs also saved the forecast weather for their hour
        saved=hist[['prediction_for']+weather].assign(prediction_for=pd.to_datetime(hist['prediction_for'],utc=True,errors='coerce'))
        runs=runs.merge(saved.drop_duplicates('prediction_for',keep='last'),on='prediction_for',how='left')
    return runs,reachable

@st.cache_resource(show_spinner=False)
def outlook_model() -> tuple[Any, list]:
    """The deployed model, loaded once for the outlook (the next-hour estimate itself still runs in the live script)."""
    import joblib
    return joblib.load(MODEL/'random_forest_live_model.pkl'),(MODEL/'live_model_features.txt').read_text(encoding='utf-8').split()

@st.cache_data(ttl=900,show_spinner=False)
def outlook_scores(hour: str) -> tuple[list, bool]:
    """Model risk scores for the next 12 forecast hours (refreshed each hour). Returns (rows, available)."""
    try:
        model,features=outlook_model()
        return storm_outlook.score(storm_outlook.fetch(),model,features,now=datetime.now(UTC)),True
    except Exception:
        return [],False

@st.cache_data(ttl=600,show_spinner=False)
def early_alerts(repo: str) -> tuple[list, bool]:
    try:return storm_outlook.early_alert_records(repo),True
    except Exception:return [],False

def ui_icon(kind: str) -> str:
    paths={
        'cloud':'<path d="M6 17a4 4 0 1 1 1-8 6 6 0 0 1 11-1 4.5 4.5 0 0 1 0 9H6"/><path d="m12 14-3 6h4l-1 4 5-7h-4l2-3"/>',
        'clock':'<circle cx="12" cy="12" r="9"/><path d="M12 6v6h5"/>',
        'wifi':'<path d="M3 8a14 14 0 0 1 18 0M6 12a9 9 0 0 1 12 0M9 16a4 4 0 0 1 6 0"/><circle cx="12" cy="20" r="1"/>',
        'model':'<path d="M12 4v16M4 12h16M6 6l12 12M6 18 18 6"/><circle cx="12" cy="3" r="2"/><circle cx="3" cy="12" r="2"/><circle cx="21" cy="12" r="2"/><circle cx="12" cy="21" r="2"/>',
        'warning':'<path d="M12 4v10"/><circle cx="12" cy="19" r="1"/>',
        'risk':'<path d="M4 20V12M10 20V5M16 20V9M22 20V2"/>',
        'table':'<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 11h8M8 15h8"/>',
        'map':'<path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5M9 3v16M15 5v16"/>',
        'weather':'<circle cx="16" cy="7" r="4" fill="#ffce46" stroke="#ffce46"/><path d="M5 20a5 5 0 1 1 1-10 6 6 0 0 1 11 2 4 4 0 0 1 0 8H5" fill="#80b4fc" stroke="#80b4fc"/>'}
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 26 26" fill="none" stroke="#0879d8" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'+paths.get(kind,paths['cloud'])+'</svg>'
    return svg_image(svg)

def svg_image(svg: str, alt: str='') -> str:
    # st.html sanitizes inline SVG. An SVG image preserves safe vector artwork.
    encoded=base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f'<img src="data:image/svg+xml;base64,{encoded}" alt="{html.escape(alt,quote=True)}" />'


def panel_title(title: str, icon: str, extra_class: str='') -> None:
    st.html(f'<div class="panel-heading {extra_class}">{ui_icon(icon)}<span>{html.escape(title)}</span></div>')

def status_card(label: str, value: str, detail: str, icon: str, tone: str='blue', compact: bool=False) -> None:
    palette={'green':('#0b8448','#e4fbed','#b5edcc'), 'blue':('#0760c7','#e8f3ff','#bcdcff'),
             'red':('#e8334b','#fff0f3','#ffc6d0'),'amber':('#a46605','#fff5dc','#f1dc9b'),
             'gray':('#607287','#edf2f7','#d5e0eb')}
    accent,tint,border=palette[tone]
    st.html(f'<div class="kpi {"compact" if compact else ""}" style="--accent:{accent};--tint:{tint};--border:{border}"><div class="kpi-icon">{ui_icon(icon)}</div><div><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div><div class="sub">{html.escape(detail)}</div></div></div>')

def information_card(label: str, value: str, detail: str='') -> None:
    st.html(f'<div class="research-card"><div class="label">{html.escape(label)}</div><div class="value">{html.escape(value)}</div><div class="detail">{html.escape(detail)}</div></div>')


def render_history(hist: pd.DataFrame) -> None:
    if not hist.empty and 'prediction_for' in hist.columns:
        display=hist.copy()
        display['prediction_for']=pd.to_datetime(display['prediction_for'],utc=True,errors='coerce')
        display=display.dropna(subset=['prediction_for']).sort_values('prediction_for',ascending=False).head(15)
        display[TARGET_LABEL]=display['prediction_for'].dt.tz_convert(SAST).dt.strftime('%d %b %H:%M')
        if 'storm_probability' in display:display['Probability (%)']=(numeric_series(pd.Series(display['storm_probability']))*100).round(1)
        display[GENERATED_LABEL]=[timestamp_labels({'prediction_generated_at':row.get('prediction_generated_at')})[GENERATED_LABEL] for _,row in display.iterrows()]
        cols=[TARGET_LABEL,GENERATED_LABEL]
        if 'Probability (%)' in display:cols.append('Probability (%)')
        if 'storm_probability' in display:
            display['Risk']=numeric_series(pd.Series(display['storm_probability'])).apply(lambda v:risk(float(v),threshold)[0])
            cols.append('Risk')
        if 'source' in display:display['Source']=display['source'];cols.append('Source')
        for field,label in [('precipitation_mm','Precipitation (mm)'),('temperature_c','Temperature (°C)'),('wind_gust_ms','Wind gust (m/s)')]:
            if field in display:display[label]=numeric_series(pd.Series(display[field])).round(2);cols.append(label)
        with st.expander(f'Saved predictions table (latest {len(display)})',expanded=False):
            st.html(dashboard_theme.table_html(display[cols],bars={'Probability (%)':100},caption='Saved model predictions'))
            st.caption('Only genuine saved model predictions are included; demonstration values are excluded.')
    else:st.info('Prediction history will appear after multiple successful updates.')


threshold=.35
try:
    selected_threshold=float(THRESHOLD.read_text().strip()) if THRESHOLD.exists() else .35
    if not math.isclose(selected_threshold,threshold):
        st.error('The selected threshold file differs from the required 35%. Model refreshes will fail until that configuration is corrected.')
except (OSError,ValueError):
    st.warning('Selected threshold file is unreadable. The dashboard uses the required 35%; model refresh may fail.')

# Authentication. A password protects demo controls; it is not production-grade IAM.
# Streamlit's recursive DeltaGenerator mixins confuse some Pylance versions.
# Limit the typing workaround to the native sidebar; runtime object is unchanged.
sidebar = cast(Any, st.sidebar)
if 'admin_authenticated' not in st.session_state:st.session_state.admin_authenticated=False
with sidebar:
    # Side menu: every section, open on desktop. Phones and tablets also get the top bar (Home, Risk Analysis,
    # Map, Safety), since their side menu sits behind the ☰ button.
    navigation = ['🏠 Dashboard','📈 Risk Analysis','🗺️ Weather Map','🛟 Safety Advice']
    MENU = [('🏠 Dashboard','home'),('📈 Risk Analysis','monitoring'),('🗺️ Weather Map','map'),('🛟 Safety Advice','health_and_safety'),
            ('🚨 Alerts','notifications'),('🌦️ Live Forecast','partly_cloudy_day'),('🕒 Historical Data','insert_chart'),('ℹ️ About','info')]
    MENU_LABELS = {'🏠 Dashboard':'Dashboard','🗺️ Weather Map':'Map','🛟 Safety Advice':'Safety','🌦️ Live Forecast':'Forecast'}
    NAV_LABELS = {'🏠 Dashboard':':material/home: Home','📈 Risk Analysis':':material/monitoring: Risk Analysis',
                  '🗺️ Weather Map':':material/map: Map','🛟 Safety Advice':':material/health_and_safety: Safety'}
    if 'dashboard_page' not in st.session_state:st.session_state.dashboard_page=navigation[0]
    if st.session_state.dashboard_page in ('🔔 SMS Alerts','📜 Warning History','📱 Alerts & Notifications'):st.session_state.dashboard_page='🚨 Alerts'
    def _go(section: str) -> None:
        st.session_state.dashboard_page=section
    for item,menu_icon in MENU:
        label=MENU_LABELS.get(item,item.split(' ',1)[1])
        st.button(label,icon=f':material/{menu_icon}:',key='menu_'+label,width='stretch',on_click=_go,args=(item,),
                  type='primary' if st.session_state.dashboard_page==item else 'secondary')
    page=st.session_state.dashboard_page
    st.divider()
    # The login is shown only via ?admin=1 (or while signed in), never in the text view;
    # the password check is unchanged.
    if not text_view and (show_admin_login or st.session_state.admin_authenticated):
        with st.expander('Administrator Access'):
            if st.session_state.admin_authenticated:
                st.success('Administrator access enabled')
                if st.button('Log Out',width='stretch'):
                    st.session_state.admin_authenticated=False;st.rerun()
            else:
                entered=st.text_input('Administrator Password',type='password')
                if st.button('Unlock Admin Controls',width='stretch'):
                    password=secret('ADMIN_PASSWORD')
                    failures=failed_logins()
                    failures[:]=[t for t in failures if time.monotonic()-t<LOGIN_WINDOW_SECONDS]
                    if not password:st.error('Administrator password is not configured.')
                    elif len(failures)>=MAX_FAILED_LOGINS:st.error('Too many failed sign-in attempts. Try again in 15 minutes.')
                    elif hmac.compare_digest(entered.encode('utf-8'),password.encode('utf-8')):
                        st.session_state.admin_authenticated=True;st.rerun()
                    else:
                        failures.append(time.monotonic());st.error('Incorrect password.')
    is_admin=bool(st.session_state.admin_authenticated) and not text_view  # text view is public-only
    st.html('<div class="sidebar-note">Research prototype · not an official SAWS service<br><a href="?view=text" style="color:#7cc0f0">Low-data text version</a></div>')
    if is_admin:
        st.divider()
        st.markdown('**Administrator controls**')
        test_mode=st.toggle('Warning simulation (on screen only)',key='presentation_test_mode',value=False,help='Shows a clearly labelled 60% simulated model output, the warning advice and an SMS preview. Nothing is sent, saved or recorded; genuine data return when switched off.')
        demo_offline=st.toggle('Connectivity-failure demonstration (this session only)',key='demo_offline',value=False,
                               help='Treats the forecast service as unreachable for this browser session: the last known information is shown, labelled out of date, and no warning decision is made. Other users are not affected.')
        if test_mode:st.html('<div style="background:#4a0f6b;color:#ffffff;border:3px solid #ffd23f;border-radius:10px;padding:10px 12px;font-weight:700;font-size:13px;line-height:1.5">Simulation on: on screen only. No SMS can be sent and no records change.</div>')
        if not test_mode and sms_is_configured() and st.button('Send Test SMS',icon=':material/sms:',width='stretch'):
            outcome=send_test_sms()
            (st.success if outcome.get('sent') else st.error)('SMS accepted by provider.' if outcome.get('sent') else 'SMS request failed. Review private server logs.')
    else:test_mode=demo_offline=False
    if is_admin and st.button('Administration',icon=':material/admin_panel_settings:',key='nav_admin',width='stretch',
                              type='primary' if page=='🛠️ Administration' else 'secondary'):
        st.session_state.dashboard_page='🛠️ Administration';st.rerun()
    if not is_admin:st.session_state.presentation_test_mode=False
    # Administration is never shown to a session that is not signed in (e.g. after logging out).
    if page=='🛠️ Administration' and not is_admin:page=st.session_state.dashboard_page=navigation[0]

if not text_view:
    banner_slot=st.empty()  # filled once the data state is known (system status and next refresh)
    with st.container(key='header_tools'):
        st.session_state.theme_switch=theme_mode=='dark'
        st.toggle('Dark theme',key='theme_switch',on_change=toggle_theme,help='Switch between the light and dark theme. Your choice is kept when you change page or refresh.')
# Officials use a separate portal (?portal=officials); it has its own sign-in and never shows resident pages.
portal_mode=st.query_params.get('portal')=='officials' and not text_view
if not text_view and not portal_mode:
    # One navigation bar for every screen size.
    st.session_state.top_nav=page if page in navigation else None
    def _go_to_section():
        if st.session_state.get('top_nav'):st.session_state.dashboard_page=st.session_state.top_nav
    with st.container(key='top_nav_bar'):
        st.segmented_control('Section',navigation,key='top_nav',format_func=lambda item:NAV_LABELS.get(item,item),on_change=_go_to_section,label_visibility='collapsed')

st.session_state.refresh_clock_count=0
refresh_clock()
with sidebar:
    manual_refresh=st.button('Refresh weather and model',key='refresh_all',icon=':material/refresh:',width='stretch')
    st.caption('Automatic refresh every 15 minutes while open.')
    st.html(dashboard_theme.sidebar_card_html())
previous_attempt=refresh_state().last_attempt
if demo_offline:state=refresh_state()  # demonstration: no retrieval this session
elif refresh_due(refresh_state(),datetime.now(SAST),manual_refresh):
    with st.spinner('Retrieving ECMWF forecasts and running the existing Random Forest…'):
        state=refresh_sources(force=manual_refresh)
else:state=refresh_state()
if manual_refresh and state.last_attempt==previous_attempt:
    st.caption('Refresh requests are limited to one per minute to protect the forecast service.')
if state.last_attempt:sidebar.caption(f'Last attempt: {state.last_attempt:%d %b %H:%M} SAST')
if state.prediction_error:st.warning(state.prediction_error+' OUTDATED DATA: the saved prediction is not a verified current assessment.')
if state.regional_error:st.warning(state.regional_error)
if state.history_error:st.warning(state.history_error)
if test_mode:
    # Fixed colours (not theme colours) keep the notice readable in light and dark themes.
    st.html(f'<div style="{SIM_BANNER_STYLE}">SIMULATION ONLY: the resident card shows a fixed 60% simulated model output, not a forecast. Genuine predictions and records are unchanged, and SMS sending is disabled.</div>')

df=pd.DataFrame()
try:
    if PRED.exists():df=pd.read_csv(PRED)
except (OSError,ValueError):st.error('Saved model prediction could not be read. Regional forecasts remain independent.')
if df.empty:st.warning('No saved model prediction is available. Regional forecasts remain independent; retry after restoring connectivity.')
latest=df.iloc[-1] if not df.empty else pd.Series(dtype='object')
valid=local_time(latest.get('prediction_for'))
input_time=local_time(latest.get('forecast_input_time'))
generated_time=local_time(latest.get('prediction_generated_at'))
now=datetime.now(SAST)
# A forecast is stale if its valid-for hour is already past.
retrieved_time=local_time(latest.get('forecast_retrieved_at'))
stale=bool(state.prediction_error) or valid is None or now>=valid.to_pydatetime() or retrieved_time is None or (now-retrieved_time.to_pydatetime()).total_seconds()>1800
stale=stale or not is_next_complete_prediction(input_time,valid,now)
data_stale=stale  # before any demonstration override: what the system really observed
if demo_offline:
    stale=True
    st.warning('DEMONSTRATION: the forecast service is treated as unreachable for this session. The last known information is shown, labelled out of date; no warning decision is made.')

# prediction_for is the next-hour target; a passed target must never look current.
real_prob=number(latest,'storm_probability')
real_label,real_color=risk(real_prob,threshold)
prob=real_prob
level,level_color=risk(prob,threshold)
configured=sms_is_configured()

hist=load_history()
runs,runs_reachable=model_runs()

# Resident view. The simulation replaces only what this card shows; `prob`, saved files and
# every other output stay genuine, and nothing here can send an SMS.
simulated=bool(is_admin and test_mode)
resident=resident_view.resident_status(real_prob,input_time,valid,generated_time or retrieved_time,stale,simulated)
advice=resident_view.guidance(resident['guidance_level'])
if text_view:
    st.markdown(resident_view.text_only_page(resident,advice))
    st.caption('Low-data text version. [Open the full dashboard](?)')
    st.stop()
updated_label=(generated_time or retrieved_time).strftime('%d %b %H:%M SAST') if (generated_time or retrieved_time) is not None else None
# A newer genuine result than this session last showed: a brief "Updated" signal (never on first load).
seen=st.session_state.get('seen_update')
just_updated=bool(seen and updated_label and seen!=updated_label and not stale)
st.session_state.seen_update=updated_label
if not text_view:
    refresh=dashboard_theme.refresh_text(state.last_attempt+timedelta(minutes=15) if state.last_attempt else None,datetime.now(SAST))
    banner_slot.html(dashboard_theme.banner_html(datetime.now(SAST),not stale,refresh,updated_label,just_updated))
st.html(dashboard_theme.status_strip(stale,updated_label,simulated))

if stale:
    st.warning('**Saved forecast / outdated prediction.** The latest retrieval failed, is too old, lacks a retrieval timestamp, or no longer matches the next complete hourly interval. This is NOT a current storm-risk assessment. Refresh is required.')

# GitHub Actions is the sole storm-warning sender; dashboard tests remain manual.
if is_admin and not test_mode and not stale and threshold<=real_prob<=1:
    st.error('The current prediction meets the warning threshold. Storm warning SMS is reserved for the scheduled GitHub Actions worker; this dashboard cannot send weather warnings.')

# Show real data in every chart. Do not invent a spatial rainfall/radar field.
forecast_status='OUTDATED' if stale else 'FIXED HOURLY TARGET'
model_status='FILE AVAILABLE' if (MODEL/'random_forest_live_model.pkl').exists() else 'MODEL FILE MISSING'
def weather_summary() -> dict:
    """Forecast weather for Matatiele from the saved model input (ECMWF), never an observation."""
    kind,label=dashboard_theme.weather_condition(number(latest,'precipitation_mm'),number(latest,'cloud_cover_percent'),input_time.hour if input_time is not None else None)
    return {'temperature':weather_value(number(latest,'temperature_c'),chr(176)+'C'),'rain':weather_value(number(latest,'precipitation_mm'),'mm'),
            'wind':weather_value(number(latest,'wind_speed_ms'),'m/s'),'gust':weather_value(number(latest,'wind_gust_ms'),'m/s'),
            'icon':svg_image(dashboard_theme.weather_icon_svg(kind),label),
            'source':'OUTDATED SAVED FORECAST' if stale else f'ECMWF forecast · {input_time:%H:%M} SAST' if input_time is not None else 'ECMWF forecast'}

def outlook_card() -> None:
    """Hours 2-12 ahead from the outlook, with an early-alert badge. Never shown from out-of-date data."""
    rows,available=outlook_scores(f'{datetime.now(UTC):%Y-%m-%dT%H}') if not stale else ([],False)
    later=[r for r in rows if r['lead_hours']>=2]
    hit=storm_outlook.first_exceedance(rows)
    with st.container(border=True,key='outlook_card'):
        st.html('<div class="section-title">Storm-risk outlook <small>Next 12 hours · Model outlook — unvalidated beyond one hour</small></div>')
        if not (available and later):
            st.html(resident_view.outlook_badge_html('unavailable'));return
        if hit:
            start=pd.Timestamp(hit['target_end_utc']).tz_convert(SAST)-pd.Timedelta(hours=1)
            st.html(resident_view.outlook_badge_html('alert',f'{start:%H:%M}',resident_view.score_text(hit['score'])))
        else:st.html(resident_view.outlook_badge_html('clear'))
        data=pd.DataFrame({'Hour starting (SAST)':[f"{pd.Timestamp(r['target_end_utc']).tz_convert(SAST)-pd.Timedelta(hours=1):%H:%M}" for r in later],
                           'Risk score (%)':[round(100*r['score'],1) for r in later],
                           'Level':['At or above 35%' if r['score']>=threshold else 'Below 35%' for r in later]})
        bars=alt.Chart(data).mark_bar(cornerRadiusTopLeft=3,cornerRadiusTopRight=3,size=22).encode(
            x=alt.X('Hour starting (SAST):O',title=None,sort=None,axis=alt.Axis(labelAngle=0)),
            y=alt.Y('Risk score (%):Q',scale=alt.Scale(domain=[0,100]),title='Model risk score (%)'),
            color=alt.Color('Level:N',scale=alt.Scale(domain=['Below 35%','At or above 35%'],range=['#2563eb','#d93449']),legend=alt.Legend(title=None,orient='top')),
            tooltip=['Hour starting (SAST)','Risk score (%)'])
        rule=alt.Chart(pd.DataFrame({'t':[35]})).mark_rule(color='#d93449',strokeDash=[6,4]).encode(y='t:Q')
        st.altair_chart(dashboard_theme.style_chart((bars+rule).properties(height=170),theme_mode),width='stretch',theme=None)
        st.caption(resident_view.OUTLOOK_NOTE)

def warning_record(events: list, error: str | None) -> dict:
    """What the public warning record holds for the current prediction period: genuine, dev (test only), none or unknown."""
    match=[e for e in events if valid is not None and e['end']==valid.to_pydatetime()]
    genuine=[e for e in match if e['source']==warning_events.GENUINE]
    if genuine:
        issued=genuine[0]['issued_at']
        return {'state':'genuine','issued':f'{issued:%H:%M}' if issued else None}
    if match:return {'state':'dev','issued':None}
    return {'state':'unknown' if error else 'none','issued':None}

def six_hour_chart() -> None:
    """Next six hours: ECMWF rain (bars) and wind (line), with the model-outlook risk score for the same hours (line).

    The risk line is the same unchanged model applied to each forecast hour; it is drawn only where a score exists
    and is never interpolated or invented. Hours with missing forecast values are left out.
    """
    hours=six_hour_forecast(state.regional,datetime.now(SAST),complete_intervals=True)
    st.html('<div class="section-title">6-hour forecast <small>ECMWF weather · model-outlook storm-risk score</small></div>')
    if hours.empty:
        st.caption('Hourly forecast unavailable until the next successful forecast retrieval.');return
    data=pd.DataFrame({'end':pd.to_datetime(hours['time'],utc=True),'Rain (mm)':numeric_series(pd.Series(hours['precipitation'])),
                       'Wind (m/s)':numeric_series(pd.Series(hours['wind_speed_10m']))})
    rows,_=outlook_scores(f'{datetime.now(UTC):%Y-%m-%dT%H}') if not stale else ([],False)
    scores={pd.Timestamp(r['target_end_utc']):round(100*r['score'],1) for r in rows}
    data['Storm-risk score (%)']=[scores.get(end) for end in data['end']]
    data['Hour (SAST)']=data['end'].dt.tz_convert(SAST).dt.strftime('%H:%M')
    x=alt.X('Hour (SAST):O',title=None,sort=None,axis=alt.Axis(labelAngle=0))
    tip=['Hour (SAST)','Rain (mm)','Wind (m/s)','Storm-risk score (%)']
    rain=alt.Chart(data).mark_bar(color='#2f80ed',opacity=.8,cornerRadiusTopLeft=3,cornerRadiusTopRight=3,size=26).encode(
        x=x,y=alt.Y('Rain (mm):Q',title='Rain (mm) · wind (m/s)',scale=alt.Scale(domainMin=0)),tooltip=tip)
    wind=alt.Chart(data).mark_line(color='#64748b',strokeWidth=2.5,point=alt.OverlayMarkDef(size=40)).encode(x=x,y=alt.Y('Wind (m/s):Q'),tooltip=tip)
    weather=alt.layer(rain,wind)
    layers=[weather]
    if data['Storm-risk score (%)'].notna().any():
        risk=alt.Chart(data.dropna(subset=['Storm-risk score (%)'])).mark_line(color='#d93449',strokeWidth=3,strokeDash=[7,4],point=alt.OverlayMarkDef(size=50,color='#d93449',shape='diamond')).encode(
            x=x,y=alt.Y('Storm-risk score (%):Q',title='Storm-risk score (%)',scale=alt.Scale(domain=[0,100])),tooltip=tip)
        layers=[risk,weather]
    chart=alt.layer(*layers).resolve_scale(y='independent') if len(layers)>1 else weather
    with st.container(border=True,key='six_hour_chart'):
        st.html('<div class="chart-legend"><b>ECMWF forecast:</b><span><i style="background:#2f80ed"></i>Rain (mm)</span><span><i style="background:#64748b"></i>Wind (m/s)</span>'
                '<b>Random Forest outlook:</b><span><i class="dash"></i>Storm-risk score (%, unvalidated beyond 1 h)</span></div>')
        st.altair_chart(dashboard_theme.style_chart(chart.properties(height=200),theme_mode),width='stretch',theme=None)
        st.caption('Rain and wind: ECMWF forecasts. Risk: the model applied to each forecast hour; beyond one hour ahead it is unvalidated.')

def key_variables() -> tuple[list, str]:
    """The ECMWF values the model used for its current estimate (its input hour)."""
    tiles=[('cloud-rain','Rainfall',weather_value(number(latest,'precipitation_mm'),'mm')),('wind','Wind speed',weather_value(number(latest,'wind_speed_ms'),'m/s')),
           ('thermometer','Temperature',weather_value(number(latest,'temperature_c'),chr(176)+'C')),('droplets','Dew point',weather_value(number(latest,'dewpoint_c'),chr(176)+'C')),
           ('zap','CAPE (storm energy)',weather_value(number(latest,'cape'),'J/kg',0)),('gauge','Pressure',weather_value(number(latest,'pressure_msl_hpa'),'hPa',0))]
    hour=f'{input_time:%H:%M} SAST' if input_time is not None else 'the input hour'
    return tiles,('Out-of-date saved values. ' if stale else '')+f'ECMWF forecast for {hour}: the inputs behind the current risk score.'

def prediction_log(events: list, count: int=6) -> list:
    """The trained model's recent hourly outputs (newest first). 'Warning' only with a genuine record."""
    if runs.empty:return []
    genuine={e['end'] for e in events if e['source']==warning_events.GENUINE}
    rows=[]
    for _,row in runs.tail(count).iloc[::-1].iterrows():
        end=row['prediction_for'].tz_convert(SAST)
        decision='Warning' if end.to_pydatetime() in genuine else 'Threshold reached' if row['storm_probability']>=threshold else 'No warning'
        source=f"{row['forecast_input_time'].tz_convert(SAST):%H:%M} SAST" if pd.notna(row['forecast_input_time']) else 'Unknown'
        rows.append((f'{end-pd.Timedelta(hours=1):%d %b %H:%M}–{end:%H:%M}',source,resident_view.score_text(row['storm_probability']),decision,row['source']))
    return rows

def forecast_chart() -> None:
    """Next 36 hours at the Matatiele grid point: rain bars and a temperature line (genuine ECMWF values)."""
    if state.regional.empty or 'temperature_2m' not in state.regional:
        st.info('The 36-hour forecast is unavailable until the next successful forecast retrieval.');return
    if state.regional_error:st.warning('Saved forecast: the latest retrieval failed.')
    data=state.regional.loc[state.regional['sample_id']==25].copy()
    data['time']=pd.to_datetime(data['forecast_hour'],utc=True,errors='coerce')
    data=data.loc[data['time']>datetime.now(UTC)].sort_values('time').head(36)
    if data.empty:
        st.info('No future hours in the saved forecast.');return
    data['Hour (SAST)']=data['time'].dt.tz_convert(SAST).dt.tz_localize(None)
    base=alt.Chart(data).encode(x=alt.X('Hour (SAST):T',title=None,axis=alt.Axis(format='%a %H:%M',labelAngle=0,tickCount=8)))
    rain=base.mark_bar(color='#2f80ed',opacity=.75,cornerRadiusTopLeft=3,cornerRadiusTopRight=3).encode(
        y=alt.Y('precipitation_mm:Q',title='Rain (mm)',scale=alt.Scale(domainMin=0)),
        tooltip=[alt.Tooltip('Hour (SAST):T',format='%a %H:%M'),alt.Tooltip('precipitation_mm:Q',title='Rain (mm)',format='.1f')])
    temperature=base.mark_line(color='#f59e0b',strokeWidth=3,point=True).encode(
        y=alt.Y('temperature_2m:Q',title='Temperature (°C)'),
        tooltip=[alt.Tooltip('Hour (SAST):T',format='%a %H:%M'),alt.Tooltip('temperature_2m:Q',title='Temperature (°C)',format='.1f')])
    with st.container(border=True,key='forecast_chart'):
        st.altair_chart(dashboard_theme.style_chart(alt.layer(rain,temperature).resolve_scale(y='independent').properties(height=270),theme_mode),width='stretch',theme=None)
        st.caption('Bars: rain (mm, hour ending). Line: temperature. ECMWF forecast for Matatiele.')

def open_sms_alerts() -> None:
    st.session_state.dashboard_page='🚨 Alerts';st.session_state.alerts_view=resident_alerts.VIEWS[1]
    st.session_state.pop('alert_selected',None)

def open_warning(key: str) -> None:
    st.session_state.dashboard_page='🚨 Alerts';st.session_state.alerts_view=resident_alerts.VIEWS[0]
    st.session_state.alert_selected=key

SEVERITY_FOR_LEVEL={'LOW':'LOW','ELEVATED':'ELEVATED','MODERATE':'MODERATE','WARNING':'HIGH'}
SYSTEM_LOG=system_log.SystemLog(get_setting('SYSTEM_LOG_PATH') or BASE/'outputs'/'system_log.sqlite')

def sms_period(value: str) -> str:
    """A warning's stored period end (UTC) as the SAST hour it covers."""
    try:
        end=pd.Timestamp(value).tz_convert(SAST)
        return f'{end-pd.Timedelta(hours=1):%d %b %H:%M}–{end:%H:%M} SAST'
    except (ValueError,TypeError):return str(value)

def record_system_events() -> None:
    """Record what this run observed. Keys and stored state make every event appear once, however often the page reruns."""
    log=SYSTEM_LOG
    data='out_of_date' if data_stale else 'current'  # the real state, never the per-session demonstration
    previous=log.swap('forecast_data',data)
    if previous and previous!=data:
        if data=='out_of_date':
            log.record('WARNING','Dashboard',('Forecast service unreachable' if state.prediction_error else 'Forecast data out of date')+
                       ': last known information shown, labelled out of date; no warning decisions from out-of-date data.')
        else:log.record('NORMAL','Dashboard','Current forecast data available again: model risk score up to date.')
    level=resident_view.classify(real_prob)  # the genuine model output, never the on-screen simulation
    if not data_stale and level in SEVERITY_FOR_LEVEL:
        if log.swap('risk_level',level)!=level:
            log.record(SEVERITY_FOR_LEVEL[level],'Dashboard',f'Risk level set to {resident_view.RISK_BADGES[level].title()}: model risk score '
                       f'{resident_view.score_text(real_prob)} for {resident["period"]}.')  # period: the same in simulation
    events,_=resident_alerts.load_events(secret)
    for event in events:
        genuine=event['source']==warning_events.GENUINE
        log.record('HIGH','Dashboard + public warning record' if genuine else 'Dashboard (development test)',
                   ('' if genuine else 'DEVELOPMENT TEST, not a real warning: ')+f'Storm warning for Matatiele: model risk score '
                   f'{warning_events.probability_text(event)}, {warning_events.period_text(event)}.',key='warning:'+event['key'],at=event['issued_at'])
    for alert in early_alerts(resident_pages.LEDGER_REPO)[0]:
        start=pd.Timestamp(alert['first_target_end_utc']).tz_convert(SAST)-pd.Timedelta(hours=1)
        log.record('HIGH','Early alert record (model outlook)',f'Early storm alert for Matatiele: raised risk from about {start:%d %b %H:%M} SAST '
                   f'(outlook score {alert["score"]:.0%}; unvalidated beyond one hour).',key='early:'+alert['key'],
                   at=pd.Timestamp(alert['created_at']).to_pydatetime() if alert.get('created_at') else None)
    for delivery in resident_alerts.sms_deliveries(secret):
        status=delivery['status']
        log.record('WARNING' if status in ('failed','uncertain') else 'INFO','SMS (simulation outbox)' if status=='outbox' else 'SMS',
                   f'SMS for the warning for {sms_period(delivery["period"])}: {resident_alerts.SMS_STATUS_LABELS.get(status,status)}.',
                   key=f'sms:{hashlib.sha256(delivery["key"].encode()).hexdigest()[:16]}:{status}',at=pd.Timestamp(delivery['updated_at']).to_pydatetime() if delivery.get('updated_at') else None)
    for flag,on_text,off_text in (('presentation_test_mode','Warning simulation shown on screen only (simulated 60% score): no warning record and no SMS.',
                                   'Warning simulation switched off: genuine data shown.'),
                                  ('demo_offline','Forecast connection set to OFFLINE for a low-connectivity demonstration (this session only).',
                                   'Forecast connection restored after the low-connectivity demonstration.')):
        active=bool(is_admin and st.session_state.get(flag)); logged=st.session_state.get('logged_'+flag,False)
        if active!=logged:
            log.record('WARNING' if active and flag=='demo_offline' else 'INFO','Administrator demonstration',on_text if active else off_text)
            st.session_state['logged_'+flag]=active

try:record_system_events()
except Exception:logging.exception('System log could not be updated.')  # logging must never interrupt the dashboard

# The banner and officials always use the genuine estimate; only the resident card shows the simulation.
genuine_status=resident_view.resident_status(real_prob,input_time,valid,generated_time or retrieved_time,stale,False)

def write_offline_status() -> None:
    """The offline page's status file, from the genuine output and the real data state (never a demonstration)."""
    status=resident_view.resident_status(real_prob,input_time,valid,generated_time or retrieved_time,data_stale,False)
    events,error=resident_alerts.load_events(secret)
    active=[e for e in events if e['source']==warning_events.GENUINE and warning_events.is_active(e)]
    early=None
    if not data_stale:
        hit=storm_outlook.first_exceedance(outlook_scores(f'{datetime.now(UTC):%Y-%m-%dT%H}')[0])
        if hit:early=f"Raised storm risk from about {pd.Timestamp(hit['target_end_utc']).tz_convert(SAST)-pd.Timedelta(hours=1):%H:%M} SAST"
    offline_page.write(BASE/'static'/'status.json',offline_page.build(status,real_prob,warning_record(events,error),active,early))

try:write_offline_status()
except Exception:logging.exception('Offline status could not be written.')  # never interrupts the dashboard
if portal_mode:
    official=official_portal.sign_in(secret,failed_official_logins(),LOGIN_WINDOW_SECONDS,MAX_FAILED_LOGINS)
    if official:
        events,_=resident_alerts.load_events(secret)
        operations,operations_error=resident_alerts.operations_store(secret)
        regional_now,regional_hour=upcoming_regional(state.regional)
        official_portal.render(official,events,operations,operations_error,regional_now,regional_hour,genuine_status)
    st.stop()

# Verified against the project's scripts (01-15) and evaluation reports; no performance figures are claimed here.
MODEL_STEPS=[
    ('Historical weather data.','Hourly ERA5 reanalysis for grid cells covering Matatiele, January 2018 onwards, supports model development only.'),
    ('Preprocessing.','The ERA5 files are cleaned and merged into one hourly record (scripts 01-04 and 06).'),
    ('Storm labels and features.','An hour is labelled a storm when ERA5 shows at least 1 mm of rain and at least one supporting sign (CAPE of 200 J/kg or more, convective rain of 0.5 mm or more, K-index of 26 or more, or cloud cover of 90% or more). The model learns to estimate the next hour\'s label from 29 inputs: the current and previous hour of temperature, dew point, pressure, rainfall, CAPE, convective rain, cloud, wind and gusts, plus location and time of year.'),
    ('Random Forest training.','300 decision trees with balanced class weights, trained on the earliest 80% of the hourly record (to 25 August 2025).'),
    ('Evaluation.','The most recent 20% of the record was held out to test the model and to compare warning thresholds; the evaluation reports document this and its limitations.'),
    ('External weather forecasts.','During operation, the system retrieves ECMWF forecasts through Open-Meteo every hour. It does not produce weather forecasts itself.'),
    ('Storm-risk estimate.','The Random Forest turns those forecast values into a next-hour storm-risk estimate for Matatiele (one location).'),
    ('Warning decision.','An estimate at or above the 35% warning threshold creates a warning record.'),
    ('Warning communication.','Warnings are shown on the Alerts page; SMS can deliver them to registered phones when it is enabled and configured.'),
]
LOW_CONNECTIVITY=[
    ('Low-data view.','Essential storm-risk information as plain text, without maps, charts or images.'),
    ('SMS warnings.','When enabled, a warning can reach a basic phone without opening the dashboard; an SMS needs only mobile signal.'),
    ('Low-data map.','The map can be shown without downloading map tiles.'),
    ('Not claimed.','The system needs a connection to update; it does not run offline, and sensors or LoRa links are future research, not implemented.'),
]

PHASES=[
    ('Development (done once, offline).','Historical ERA5 reanalysis from 2018 was cleaned, labelled with storm rules and used to train and evaluate the Random Forest and to compare warning thresholds. This data is not used during operation.'),
    ('Operation (every hour).','The system retrieves the latest ECMWF forecast, the saved model estimates next-hour storm risk for Matatiele, the 35% rule decides whether to warn, and warnings are recorded and shown; SMS is optional.'),
]
RO3_STATUS=[
    ('Smart: Random Forest storm-risk assessment','Implemented','ECMWF forecast inputs, the trained Random Forest (29 inputs), model-estimated risk score; evidence on Risk Analysis'),
    ('Early warning: 35% threshold decision','Implemented','Warning decision, public warning record, Alerts page'),
    ('Resilient: degraded operation','Implemented','Fresh or out-of-date status, last-known information, offline saved-information page, warning records kept if SMS fails'),
    ('Low connectivity: dashboard alerts, low-data view, offline page','Implemented','Plain-text view; offline page keeps the last warning, advice and emergency numbers'),
    ('Low connectivity: SMS and community relays','Implemented as simulation','SMS simulation and controlled test; relay role and announcement scripts (not field-tested with relays)'),
    ('Early: 2 to 12 hour storm-risk outlook','Exploratory, unvalidated','Same model on later forecast hours; evaluated one hour ahead only'),
    ('Public SMS, sensors, LoRa, sirens, Cell Broadcast, field validation','Future / deployment-dependent','Not implemented'),
]

OFFLINE_PAGE='app/static/offline.html'
HISTORY_RANGES=('Last 24 hours','Last 7 days','All saved')

def more_safety_advice() -> None:
    st.session_state.dashboard_page='🛟 Safety Advice'

def open_contacts() -> None:
    st.session_state.dashboard_page='🛟 Safety Advice';st.session_state.scroll_to_contacts=True

def go_to(section: str) -> None:
    st.session_state.dashboard_page=section

# Each piece of information has one place: Home summarises; every other section adds detail not shown on Home.
if page=='🏠 Dashboard':
    events,events_error=resident_alerts.load_events(secret)
    active_events=[e for e in events if warning_events.is_active(e)]
    banner=resident_alerts.status_banner_html(active_events,genuine_status)  # only when a warning is in effect
    if banner:st.html(banner)
    if active_events:
        warning_actions=st.columns([1,1,2])
        warning_actions[0].button('Open the warning',key='home_open_warning',on_click=open_warning,args=(active_events[0]['key'],),type='primary',icon=':material/warning:',width='stretch')
        warning_actions[1].button('Safety and emergency contacts',key='home_warning_safety',on_click=open_contacts,icon=':material/health_and_safety:',width='stretch')
    communication=resident_alerts.communication_status(secret,events_error,BASE)
    genuine_active=[e for e in active_events if e['source']==warning_events.GENUINE]
    if genuine_active:  # a genuine warning is in effect: the act-now advice comes straight after the warning
        st.html(resident_view.quick_actions_html(resident_view.guidance('WARNING')))
    st.html(resident_view.summary_html(resident,real_prob,weather_summary(),warning_record(events,events_error),just_updated))
    with st.container(key='home_actions'):
        actions=st.columns(5,gap='small')
        actions[0].button('View warnings',key='home_alerts',on_click=go_to,args=('🚨 Alerts',),icon=':material/notifications:',type='primary',width='stretch')
        actions[1].button('Safety advice',key='home_safety',on_click=more_safety_advice,icon=':material/health_and_safety:',width='stretch')
        actions[2].button('Emergency contacts',key='home_contacts',on_click=open_contacts,icon=':material/call:',width='stretch')
        actions[3].button('SMS service',key='cta_sms_alerts',on_click=open_sms_alerts,icon=':material/sms:',width='stretch',
                          help='SMS warning service: research prototype. Public SMS delivery is not active.')
        actions[4].link_button('Offline access',OFFLINE_PAGE,icon=':material/wifi_off:',width='stretch',
                               help='Open once while you have signal: your phone keeps the last warning, safety advice and emergency numbers for when the network is down. It cannot receive new warnings offline.')
    outlook_column,chart_column=st.columns([1,1.35],gap='medium')
    with outlook_column:outlook_card()
    with chart_column:six_hour_chart()
    variables_column,log_column,comms_column=st.columns([1,1.25,.9],gap='medium')
    with variables_column:st.html(resident_view.variables_html(*key_variables()))
    with log_column:st.html(resident_view.prediction_log_html(prediction_log(events),runs_reachable))
    with comms_column:st.html(resident_view.communication_html(communication))
    if not genuine_active:
        st.html(resident_view.quick_actions_html(advice))
    st.html('<div class="lowdata-link">Low connectivity: <a href="?view=text">Low-data view</a> (plain text) · '
            f'<a href="{OFFLINE_PAGE}" target="_blank" rel="noopener">Offline access</a> (open once with signal; keeps the last '
            'warning, safety advice and emergency numbers for when the network is down).</div>')
    if simulated:
        st.markdown('**SMS preview (simulation): this is the text a warning would contain. It has NOT been sent.**')
        st.code(resident_view.sms_preview(valid.isoformat() if valid is not None else ''),language=None,wrap_lines=True)

if page=='🛟 Safety Advice':
    st.html('<div class="section-title">Safety advice <small>Before a storm, and when a storm is close</small></div>')
    st.html(resident_view.advice_cards_html(resident_view.guidance('LOW'),'Be prepared',compact=True))
    st.caption('Full advice for when a storm is close:')
    st.html(resident_view.advice_cards_html(resident_view.guidance('WARNING'),'Act now'))
    st.caption(resident_view.OFFICIAL_NOTE)
    st.html('<div class="section-title">Emergency contacts <small>National emergency numbers for South Africa</small></div>')
    st.html(emergency_contacts.contacts_html('Call for help',wide=True))
    if st.session_state.pop('scroll_to_contacts',False):
        # Opened from an "Emergency contacts" shortcut: bring the contacts into view (they sit below the safety advice).
        components.html('<script>let n=0;const go=()=>{const d=window.parent.document,el=d.getElementById("emergency-contacts")||d.querySelector(".contacts-card");'
                        'if(el){el.scrollIntoView({block:"start"});}else if(n++<25){setTimeout(go,200);}};setTimeout(go,300);</script>',height=0)

layers: list[Any]=[]
TOOLTIP_STYLE={'backgroundColor':'#0f2440','color':'white','fontFamily':'Segoe UI, Arial, sans-serif','fontSize':'12px','borderRadius':'8px','padding':'8px 10px'}
map_tooltip=cast(Any, {'html':'<b>{name}</b><br/>{detail}', 'style':TOOLTIP_STYLE})
basemap_url=SATELLITE_STYLE_URL
if page=='🗺️ Weather Map':
    with st.container(key='map_card'):
        # Title and controls in one compact band (stacks on phones); the map takes the remaining space.
        hours=regional_hours(state.regional)
        with st.container(key='map_controls'):
            control_title,control_basemap,control_hour=st.columns([1.1,1.1,2.6],gap='medium',vertical_alignment='bottom')
        control_title.html('<div class="map-band"><b>Storm map</b><small>ECMWF rainfall forecast · model storm risk</small></div>')
        with control_basemap:
            basemap=st.segmented_control('Basemap',list(BASEMAPS),default='Satellite',key='map_basemap',
                                         help='Low data draws no map tiles: only the forecast overlay and labels.')
        with control_hour:
            map_hour=st.select_slider('Forecast hour (SAST)',options=hours,key='map_hour',format_func=lambda hour:f'{hour.tz_convert(SAST):%a %H:%M}',
                                      help='Step through the coming hours of the ECMWF rainfall forecast to see where rain is expected and how it moves.') if len(hours)>1 else None
        # The map is drawn into this slot; the overlay switch sits under it, beside the legend it controls.
        map_slot=st.container()
        overlay_switch,overlay_strength=st.columns([1,2],vertical_alignment='center')
        show_overlay=overlay_switch.toggle('Rainfall overlay',value=True,key='map_overlay',help='Interpolated ECMWF forecast rainfall for the selected hour.')
        overlay_opacity=overlay_strength.slider('Overlay opacity',.2,1.,.78,.05,key='map_opacity',disabled=not show_overlay,
                                                help='How strongly the rainfall colours cover the basemap. The data does not change.')
        basemap_url=BASEMAPS.get(basemap or 'Satellite',SATELLITE_STYLE_URL)
        regional,regional_valid=upcoming_regional(state.regional,map_hour)
        regional_retrieved=local_time(state.regional.iloc[0].get('forecast_retrieved_at')) if not state.regional.empty else None
        regional_stale=bool(state.regional_error) or regional_retrieved is None or (datetime.now(SAST)-regional_retrieved.to_pydatetime()).total_seconds()>1800
        layers=[]
        if regional_stale:st.warning('OUTDATED / UNVERIFIED regional forecast. Rainfall overlay withheld until a fresh retrieval succeeds.')
        if not regional.empty and not regional_stale:
            regional=regional.assign(detail=f'Forecast rainfall for the hour ending {regional_valid:%H:%M} SAST (ECMWF grid point). Not radar.')
            try:
                overlay_image,bounds=make_rainfall_overlay(regional)
                if show_overlay:layers.append(pdk.Layer('BitmapLayer',image=String(overlay_image),bounds=bounds,opacity=overlay_opacity))
                layers.append(pdk.Layer('ScatterplotLayer',regional,get_position='[lon, lat]',get_radius=700,get_fill_color=[25,45,65,150],pickable=True))
            except (ValueError,KeyError):st.warning('Incomplete rainfall grid: overlay unavailable. No artificial values substituted.')
        matatiele=pd.DataFrame([{'lat':MATATIELE_LAT,'lon':MATATIELE_LON,'name':'Matatiele','detail':'Location of the next-hour storm-risk model'}])
        ring=[int(level_color[i:i+2],16) for i in (1,3,5)]
        model_area=matatiele.assign(name=f'Storm model: {level}',detail=f'Next-hour model-estimated storm risk {prob:.0%} for Matatiele (one location)' if math.isfinite(prob) else 'No current model estimate')
        layers.append(pdk.Layer('ScatterplotLayer',model_area,get_position='[lon, lat]',get_radius=9000,get_fill_color=ring+[40],get_line_color=ring+[230],line_width_min_pixels=3,stroked=True,pickable=True))
        layers.append(pdk.Layer('ScatterplotLayer',matatiele,get_position='[lon, lat]',get_radius=3000,get_fill_color=[221,45,67,240],get_line_color=[255,255,255,255],line_width_min_pixels=3,stroked=True,pickable=True))
        nearby=pd.DataFrame(NEARBY_PLACES)
        nearby['reference']='Geographic reference only; no town-specific storm prediction'
        nearby['detail']=nearby['reference']
        layers.append(pdk.Layer('ScatterplotLayer',nearby,get_position='[lon, lat]',
            radius_units=String('pixels'),get_radius=4,get_fill_color=[235,245,255,255],
            get_line_color=[12,32,54,255],line_width_min_pixels=1.5,stroked=True,pickable=True))
        # Both map views share these layers. Text stays anchored to longitude/
        # latitude while its pixel-sized background remains readable at any zoom.
        labels=pd.concat([nearby,pd.DataFrame([{'name':'Matatiele','lat':MATATIELE_LAT,
            'lon':MATATIELE_LON,'offset':[12,12],'anchor':'start',
            'reference':'Primary next-hour model location','detail':'Location of the next-hour storm-risk model'}])],ignore_index=True)
        layers.append(pdk.Layer('TextLayer',labels,get_position='[lon, lat]',get_text='name',
            get_size=12,size_units=String('pixels'),get_color=[255,255,255],font_family=String('Arial, sans-serif'),
            font_weight=600,get_pixel_offset='offset',get_text_anchor='anchor',
            get_alignment_baseline=String('center'),background=True,
            get_background_color=[12,32,54,235],background_padding=[5,3],pickable=True))
        map_slot.pydeck_chart(pdk.Deck(map_style=basemap_url,initial_view_state=pdk.ViewState(latitude=MATATIELE_LAT,longitude=MATATIELE_LON,zoom=8.6,pitch=0),layers=layers,tooltip=map_tooltip),width='stretch',height=560)
        if not regional.empty and not regional_stale:
            st.html(f'<div class="map-legend"><div class="title">Forecast rainfall, mm in the hour ending {regional_valid:%a %d %b %H:%M} SAST (ECMWF, retrieved {regional_retrieved:%H:%M} SAST)</div><div class="rain-legend"></div>'
                    '<div class="legend-labels"><span>0</span><span>0.1</span><span>1</span><span>3</span><span>5</span><span>10</span><span>20</span><span>40+</span></div>'
                    f'<div class="note">Colours: ECMWF IFS 0.25° rainfall forecast at 25 ECMWF grid cells (a 5 × 5 set, 0.25° to 0.5° apart, about 24 to 48 km), interpolated and smoothed between points, so detail finer than the grid is not real. It is not radar or observed rain. '
                    f'<span class="ring" style="--ring:{level_color}"></span>Ring: model-estimated storm risk for Matatiele ({level.lower()}); the model covers that one point only. Drag, zoom or tap a point.'
                    +('' if show_overlay else ' Overlay hidden.')+'</div></div>')
        with st.expander('Map data and method'):
            if not regional.empty and not regional_stale:
                st.caption(f'ECMWF / Open-Meteo: hour ending {regional_valid:%d %b %Y %H:%M SAST}; retrieved {regional_retrieved:%d %b %Y %H:%M SAST}. Bilinear interpolation of 25 actual grid samples, not radar. Colour intervals are nonlinear.')
                st.caption('Grid: 25 points requested on a regular 0.30° × 0.35° pattern; the forecast service returns the nearest ECMWF 0.25° grid cell for each, so the cells used lie at latitudes 29.75° to 31.0° S and longitudes 28.0° to 29.5° E, 0.25° to 0.5° apart. The storm-risk model uses a separate ECMWF forecast requested for Matatiele (30.30° S, 28.80° E), with its location inputs set to the ERA5 training cell at 30.25° S, 28.75° E.')
                st.caption(f'Sampled rainfall range: {regional.precipitation_mm.min():.2f} to {regional.precipitation_mm.max():.2f} mm. Dry areas are transparent; trace rainfall is faint.')
            st.caption('Town labels are geographic references. The Random Forest storm prediction applies only to Matatiele.')
        if regional.empty or regional_stale:st.info('Matatiele is shown in red. Refresh to retrieve genuine regional rainfall forecasts.')

if page=='🌦️ Live Forecast':
    st.html('<div class="section-title">Weather forecast <small>Supplied by ECMWF via Open-Meteo for the next 36 hours, and the forecast variables the storm-risk model uses</small></div>')
    forecast_chart()
    cape,previous=number(latest,'cape'),number(latest,'previous_cape')
    change=f'{cape-previous:+.0f} J/kg vs previous hour' if math.isfinite(cape) and math.isfinite(previous) else 'Change unavailable'
    st.html(dashboard_theme.ingredient_tiles_html([
        ('zap','Storm energy (CAPE)',weather_value(cape,'J/kg',0),change),
        ('droplets','Dew point',weather_value(number(latest,'dewpoint_c'),chr(176)+'C'),'Moisture in the air'),
        ('cloud-rain','Showers',weather_value(number(latest,'showers_mm'),'mm'),'Convective rain in the input hour'),
        ('clock','Model input hour',f'{input_time:%H:%M} SAST' if input_time is not None else 'Unknown','ECMWF forecast used by the model')]))
    st.caption('All values are external ECMWF forecasts via Open-Meteo, not observations. This system does not produce weather forecasts; it uses them to estimate storm risk.')
    if input_time is not None and valid is not None:
        st.caption(f'The storm-risk model uses the forecast for {input_time:%d %b %H:%M} SAST and the hour before it to estimate the risk for the hour {interval_label(valid)}. '
                   'The other hours in the chart are shown for information only: the model makes one estimate, for the next hour.')

if page=='📈 Risk Analysis':
    st.html('<div class="section-title">Risk analysis <small>How the next-hour model estimate compares with the 35% warning threshold</small></div>')
    left,right=st.columns([1,1.3],gap='medium')
    with left,st.container(border=True,key='risk_card'):
        panel_title('Model-estimated storm risk','risk')
        usable=math.isfinite(prob) and 0<=prob<=1
        gauge_value=prob if usable else 0.0
        value_text=f'{prob:.1%}' if usable else 'Unavailable'
        gauge=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 165" font-family="Arial, sans-serif"><path d="M25 120 A105 105 0 0 1 235 120" fill="none" stroke="#d4dce7" stroke-width="20" stroke-linecap="round"/><path d="M25 120 A105 105 0 0 1 235 120" fill="none" stroke="{level_color}" stroke-width="20" stroke-linecap="round" pathLength="100" stroke-dasharray="{gauge_value*100} 100"/></svg>'
        st.html(f'<div class="risk-status">{"OUTDATED / UNVERIFIED SAVED RESULT" if stale else "RANDOM FOREST - FIXED HOURLY TARGET"}</div><div class="risk-body single"><div class="risk-gauge">{svg_image(gauge,"Storm probability "+value_text)}<div class="gauge-value">{value_text}</div><div class="gauge-label">Storm probability</div><span class="risk-badge" style="--accent:{level_color};--tint:{level_color}25">{level} RISK</span></div></div>')
    with right:
        st.html(dashboard_theme.risk_scale_html(prob if math.isfinite(prob) else None,threshold))
        st.html(resident_view.details_html(genuine_status))
        st.caption(f'Target interval: {interval_label(valid)} · generated {generated_time.strftime("%d %b %H:%M SAST") if generated_time is not None else "unknown"} · fixed hourly target, not a rolling 60 minutes.')
    with st.expander('About the 35% warning threshold',expanded=True):
        st.markdown(resident_view.THRESHOLD_TEXT)
        st.caption(resident_view.THRESHOLD_METHOD)
    evidence=model_evidence.load(BASE/'docs'/'model_evidence.json')
    if evidence is None:
        st.info('Model evaluation evidence is unavailable (docs/model_evidence.json could not be read).')
    else:
        st.html('<div class="section-title">Patterns learned from historical weather data <small>Which inputs the Random Forest relies on</small></div>')
        groups=model_evidence.importance_frame(evidence)
        bars=alt.Chart(groups).mark_bar(color='#2563eb',cornerRadiusEnd=3).encode(
            x=alt.X('Share (%):Q',title='Share of split decisions (%)'),y=alt.Y('Input group:N',sort='-x',title=None,axis=alt.Axis(labelLimit=260)),
            tooltip=['Input group','Share (%)','Inputs']).properties(height=230)
        st.altair_chart(dashboard_theme.style_chart(bars,theme_mode),width='stretch',theme=None)
        st.caption(model_evidence.IMPORTANCE_NOTE)
        with st.expander('Why a Random Forest?'):
            st.html(dashboard_theme.explainer_html(model_evidence.WHY_RF))
        st.html('<div class="section-title">Model performance and threshold comparison <small>Held-out historical data, by warning threshold</small></div>')
        st.html(dashboard_theme.table_html(model_evidence.threshold_frame(evidence),caption='Deployed model on the held-out test period'))
        st.caption(model_evidence.performance_caption(evidence))
        with st.expander('Stricter evaluation with a separate validation year'):
            st.html(dashboard_theme.table_html(model_evidence.chronological_frame(evidence),caption='Test year, threshold chosen on the validation year'))
            st.caption(model_evidence.CHRONOLOGICAL_NOTE)
        with st.expander('Outcomes at the 35% threshold (confusion matrix)'):
            st.html(dashboard_theme.table_html(model_evidence.confusion_frame(evidence),caption='Held-out test period, 35% threshold'))
        st.html('<div class="section-title">What the percentage means <small>Model score, performance, calibration and confidence</small></div>')
        st.html(dashboard_theme.explainer_html(model_evidence.CONFIDENCE_POINTS))
        with st.expander('Calibration check'):
            st.html(dashboard_theme.table_html(model_evidence.reliability_frame(evidence),caption='Model score against labelled storm frequency'))
            st.caption(model_evidence.reliability_caption(evidence))

if page=='🕒 Historical Data':
    st.html('<div class="section-title">Historical data <small>Saved model predictions (genuine records only)</small></div>')
    if not runs_reachable:st.caption('The hourly worker\'s public run log could not be reached; only this dashboard\'s saved runs are shown.')
    if not runs.empty:
        series=pd.DataFrame(runs[['prediction_for','storm_probability']]).copy()
        series['target']=pd.to_datetime(series['prediction_for'],utc=True,errors='coerce')
        series['Probability (%)']=numeric_series(pd.Series(series['storm_probability']))*100
        series=series.dropna()
        valid_probabilities=numeric_series(pd.Series(series['Probability (%)'])).between(0,100)
        series=pd.DataFrame(series.loc[valid_probabilities]).sort_values(by='target').drop_duplicates('target',keep='last')
        span=st.segmented_control('Period',HISTORY_RANGES,default=HISTORY_RANGES[1],key='history_range',label_visibility='collapsed')
        hours={'Last 24 hours':24,'Last 7 days':24*7}.get(span or HISTORY_RANGES[1])
        if hours and not series.empty:series=series.loc[series['target']>series['target'].max()-pd.Timedelta(hours=hours)]
        if not series.empty:
            series['Target (SAST)']=series['target'].dt.tz_convert(SAST).dt.tz_localize(None)
            # A new line segment starts after any gap of more than one hour: missing records are never interpolated.
            series['segment']=(series['target'].diff()>pd.Timedelta(hours=1)).cumsum()
            x=alt.X('Target (SAST):T',title=None,axis=alt.Axis(format='%d %b %H:%M',labelAngle=0,tickCount=6))
            y=alt.Y('Probability (%):Q',title='Model-estimated storm risk (%)',scale=alt.Scale(domain=[0,100]))
            tip=[alt.Tooltip('Target (SAST):T',title='Hour ending (SAST)',format='%d %b %Y %H:%M'),alt.Tooltip('Probability (%):Q',format='.1f')]
            base=alt.Chart(series)
            lines=base.mark_line(color='#1268c4').encode(x=x,y=y,detail='segment:N')
            points=base.mark_circle(size=34,color='#1268c4').encode(x=x,y=y,tooltip=tip)
            rule=alt.Chart(pd.DataFrame({'threshold':[35],'label':['35% warning threshold']}))
            line=rule.mark_rule(color='#d93449',strokeDash=[6,4]).encode(y='threshold:Q')
            text=rule.mark_text(align='left',dx=4,dy=-7,color='#d93449',fontSize=11).encode(y='threshold:Q',text='label:N',x=alt.value(0))
            st.altair_chart(dashboard_theme.style_chart((lines+points+line+text).properties(height=240).interactive(bind_y=False),theme_mode),width='stretch',theme=None)
            st.caption(f'{len(series)} saved hourly predictions. Lines break where hours are missing; nothing is filled in. Scroll or pinch on the chart to zoom in time, double-click to reset.')
        else:st.info('No valid recorded probabilities available.')
    else:st.info('Recorded predictions will appear after successful forecast updates.')
    render_history(runs)

if page=='🚨 Alerts':
    log_rows=[(f'{pd.Timestamp(at).tz_convert(SAST):%Y-%m-%d %H:%M:%S}',severity,delivery,status) for at,severity,delivery,status in SYSTEM_LOG.recent(100)]
    resident_alerts.render_alerts(secret,genuine_status,log_rows,early_alerts(resident_pages.LEDGER_REPO)[0])
    if is_admin:
        st.markdown('**Operational status (administrators)**')
        a,b,c=st.columns(3)
        with a:status_card('Dashboard warnings','OUTDATED' if stale else 'AVAILABLE','Saved forecast freshness' if stale else 'Model-estimated storm risk available','warning','amber' if stale else 'green',compact=True)
        with b:status_card('Automatic SMS','MANAGED BY GITHUB ACTIONS','Independent worker. Check Actions logs for execution and Twilio/recipient for delivery; neither is verified here.','wifi','blue',compact=True)
        with c:status_card('SMS trigger','ACTIONS ONLY','Administrator test SMS: dashboard-local Twilio '+('configured' if configured else 'not configured')+'. This does not indicate Actions configuration.','model','blue',compact=True)
        if SMS_LOG.exists():
            try:
                log=pd.read_csv(SMS_LOG)
                cols=[c for c in ['logged_at_utc','storm_probability','status'] if c in log]
                if cols:st.html(dashboard_theme.table_html(log[cols].tail(20),caption='SMS log'))
            except Exception:st.info('SMS log is currently unavailable.')
        st.info('Automatic storm-warning checks are handled by an independent GitHub Actions scheduled worker. The dashboard does not need to remain open.')

if page=='🛠️ Administration' and is_admin:
    health={'Prediction data':'Outdated' if stale else 'Fresh',
            'Last forecast update':updated_label or 'Unknown',
            'Regional rainfall data':'Outdated' if state.regional_error else 'Fresh',
            'Last refresh attempt':f'{state.last_attempt:%d %b %H:%M} SAST' if state.last_attempt else 'Not yet',
            'Random Forest model file':model_status,'Warning threshold':f'{threshold:.0%}'}
    resident_pages.render_admin(secret,health)
if page=='ℹ️ About':
    st.html('<div class="section-title">About <small>How a storm warning reaches residents</small></div>')
    st.html(dashboard_theme.flow_html(delivery_mode(secret)))
    with st.expander('How the model and system work'):
        st.html(dashboard_theme.explainer_html(MODEL_STEPS))
    with st.expander('Designed for low connectivity'):
        st.html(dashboard_theme.explainer_html(LOW_CONNECTIVITY)+'<div class="lowdata-link"><a href="?view=text">Open the low-data view</a></div>')
    with st.expander('Development and operation'):
        st.html(dashboard_theme.explainer_html(PHASES))
    with st.expander('Research Objective 3 (RO3) and how this system addresses it'):
        st.markdown('**RO3:** to design and develop a smart resilient storm early warning system for low-connectivity environments, using Matatiele as a case study.')
        st.html(dashboard_theme.table_html(pd.DataFrame(RO3_STATUS,columns=['Part of RO3','Status','How']),caption='Implemented, simulated and future work'))
    a,b,c=st.columns(3)
    verified=not stale and not state.regional_error
    with a:status_card('System status','ONLINE' if verified else 'SAVED DATA','Latest retrieval verified' if verified else 'Outdated / unverified','wifi','green' if verified else 'amber')
    with b:status_card('Model','Random Forest','29 forecast input variables · ERA5-trained','model','blue')
    with c:status_card('Warning threshold',f'{threshold:.0%}','Model-risk score required to trigger a warning decision.','warning','red')
    st.html(f'<div class="research-notice"><strong>Academic research prototype</strong> — not an official weather warning service. Follow official warnings and local emergency guidance. '
            f'Official South African warnings: <a href="{resident_alerts.SAWS_URL}" target="_blank" rel="noopener">South African Weather Service</a>.</div>')
    with st.expander('Forecast source and timestamps'):
        st.caption(f'Weather forecast retrieved: {retrieved_time.strftime("%d %b %Y %H:%M:%S SAST") if retrieved_time is not None else "Unknown (legacy saved record)"} · Forecast input hour: {input_time.strftime("%d %b %Y %H:%M SAST") if input_time is not None else "Unknown"} · Forecast target (hour ending): {valid.strftime("%d %b %Y %H:%M SAST") if valid is not None else "Unknown"}')
        st.caption(f'Prediction generated: {generated_time.strftime("%d %b %Y %H:%M:%S SAST") if generated_time is not None else "Unknown (legacy saved record)"}. Target interval: {interval_label(valid)}. Fixed hourly target, not a rolling 60-minute window. Instantaneous conditions are valid at their timestamp; rainfall covers the preceding hour.')
        st.caption('ECMWF run issue time is not supplied by this API response; retrieval time is recorded separately.')

st.divider()
st.caption('Academic research prototype, not an official warning service · Official warnings: South African Weather Service (weathersa.co.za) · Times in SAST (UTC+2)')
