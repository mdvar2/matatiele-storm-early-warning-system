"""Matatiele Smart Resilient Storm Early Warning System — research beta dashboard.
Forecast-driven interface; no SMS is sent on page load or in presentation mode.
"""
from pathlib import Path
from datetime import datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from typing import Any, cast
import os
import hmac
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
                   initial_sidebar_state='collapsed')  # the ☰ menu opens the side menu

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
        for field,label in [('precipitation_mm','Precipitation (mm)'),('temperature_c','Temperature (°C)'),('wind_gust_ms','Wind gust (m/s)')]:
            if field in display:display[label]=numeric_series(pd.Series(display[field])).round(2);cols.append(label)
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
    st.html(f'<div class="brand">{ui_icon("cloud")}<div><strong>Matatiele</strong><span>Storm Early Warning</span><small>Eastern Cape · Research Beta</small></div></div>')
    # Top bar: everyday sections. The ☰ side menu: Alerts and the research sections.
    navigation = ['🏠 Dashboard','🌦️ Live Forecast','🗺️ Weather Map','🛟 Safety Advice']
    MENU = [('🚨 Alerts','notifications'),('📈 Risk Analysis','monitoring'),('🕒 Historical Data','insert_chart'),('ℹ️ About','info')]
    NAV_LABELS = {'🏠 Dashboard':':material/home: Home','🌦️ Live Forecast':':material/partly_cloudy_day: Forecast',
                  '🗺️ Weather Map':':material/map: Map','🛟 Safety Advice':':material/health_and_safety: Safety'}
    if 'dashboard_page' not in st.session_state:st.session_state.dashboard_page=navigation[0]
    if st.session_state.dashboard_page in ('🔔 SMS Alerts','📜 Warning History','📱 Alerts & Notifications'):st.session_state.dashboard_page='🚨 Alerts'
    def _go(section: str) -> None:
        st.session_state.dashboard_page=section
    for item,menu_icon in MENU:
        st.button(item.split(' ',1)[1],icon=f':material/{menu_icon}:',key='menu_'+item.split(' ',1)[1],width='stretch',on_click=_go,args=(item,),
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
        if test_mode:st.html('<div style="background:#4a0f6b;color:#ffffff;border:3px solid #ffd23f;border-radius:10px;padding:10px 12px;font-weight:700;font-size:13px;line-height:1.5">Simulation on: on screen only. No SMS can be sent and no records change.</div>')
        if not test_mode and sms_is_configured() and st.button('Send Test SMS',icon=':material/sms:',width='stretch'):
            outcome=send_test_sms()
            (st.success if outcome.get('sent') else st.error)('SMS accepted by provider.' if outcome.get('sent') else 'SMS request failed. Review private server logs.')
    else:test_mode=False
    if is_admin and st.button('Administration',icon=':material/admin_panel_settings:',key='nav_admin',width='stretch',
                              type='primary' if page=='🛠️ Administration' else 'secondary'):
        st.session_state.dashboard_page='🛠️ Administration';st.rerun()
    if not is_admin:st.session_state.presentation_test_mode=False
    # Administration is never shown to a session that is not signed in (e.g. after logging out).
    if page=='🛠️ Administration' and not is_admin:page=st.session_state.dashboard_page=navigation[0]

if not text_view:
    head,tools=st.columns([4,1.3],vertical_alignment='center')
    head.html(f'<div class="hero"><div class="hero-main">{ui_icon("cloud")}<div><h1>Matatiele Smart Resilient Storm Early Warning System</h1><p>Is a storm likely in Matatiele in the next hour, and what should you do?</p></div></div></div>')
    with tools,st.container(key='header_tools'):
        st.html(f'<div class="clock-card">{datetime.now(SAST):%d %B %Y &nbsp; %H:%M} SAST<small>Dashboard time · Research Beta</small></div>')
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
previous_attempt=refresh_state().last_attempt
if refresh_due(refresh_state(),datetime.now(SAST),manual_refresh):
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

# prediction_for is the next-hour target; a passed target must never look current.
real_prob=number(latest,'storm_probability')
real_label,real_color=risk(real_prob,threshold)
prob=real_prob
level,level_color=risk(prob,threshold)
configured=sms_is_configured()

hist=load_history()

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
st.html(dashboard_theme.status_strip(stale,updated_label,simulated))

if stale:
    st.warning('**Saved forecast / outdated prediction.** The latest retrieval failed, is too old, lacks a retrieval timestamp, or no longer matches the next complete hourly interval. This is NOT a current storm-risk assessment. Refresh is required.')

# GitHub Actions is the sole storm-warning sender; dashboard tests remain manual.
if is_admin and not test_mode and not stale and threshold<=real_prob<=1:
    st.error('The current prediction meets the warning threshold. Storm warning SMS is reserved for the scheduled GitHub Actions worker; this dashboard cannot send weather warnings.')

# Show real data in every chart. Do not invent a spatial rainfall/radar field.
forecast_status='OUTDATED' if stale else 'FIXED HOURLY TARGET'
model_status='FILE AVAILABLE' if (MODEL/'random_forest_live_model.pkl').exists() else 'MODEL FILE MISSING'
def weather_card() -> None:
    """Forecast weather for Matatiele from the saved model input (ECMWF), never an observation."""
    condition_kind,condition_label=dashboard_theme.weather_condition(number(latest,'precipitation_mm'),number(latest,'cloud_cover_percent'),input_time.hour if input_time is not None else None)
    forecast_hour=f'{input_time:%H:%M} SAST' if input_time is not None else 'unknown hour'
    tiles=[('cloud-rain','Rainfall',weather_value(number(latest,'precipitation_mm'),'mm'),'Forecast hour'),
           ('wind','Wind',weather_value(number(latest,'wind_speed_ms'),'m/s'),'Gusts '+weather_value(number(latest,'wind_gust_ms'),'m/s')),
           ('cloud','Cloud',weather_value(number(latest,'cloud_cover_percent'),'%',0),'Pressure '+weather_value(number(latest,'pressure_msl_hpa'),'hPa',0))]
    st.html(dashboard_theme.weather_card_html(svg_image(dashboard_theme.weather_icon_svg(condition_kind),condition_label),
        weather_value(number(latest,'temperature_c'),chr(176)+'C'),condition_label,'Weather · next hour (forecast)',tiles,
        'OUTDATED SAVED CONDITIONS' if stale else f'ECMWF forecast for {forecast_hour} - not an observation',
        f'Updated {updated_label}' if updated_label else ''))

def hourly_forecast() -> None:
    """Genuine ECMWF hourly values at the Matatiele grid point (no imputation; missing hours are omitted)."""
    hours=six_hour_forecast(state.regional,datetime.now(SAST),complete_intervals=True)
    if hours.empty:
        st.caption('Hourly forecast unavailable until the next successful forecast retrieval.');return
    cells=[]
    for _,row in hours.iterrows():
        kind,label=dashboard_theme.weather_condition(number(row,'precipitation'),number(row,'cloud_cover'),row['time'].hour)
        cells.append((f'{row["time"]:%H:%M}',svg_image(dashboard_theme.weather_icon_svg(kind),label),
                      weather_value(number(row,'temperature_2m'),chr(176),0),weather_value(number(row,'precipitation'),'mm'),
                      weather_value(number(row,'wind_speed_10m'),'m/s')))
    st.html('<div class="section-title">Next hours <small>ECMWF forecast for Matatiele, hour ending (SAST)</small></div>'+dashboard_theme.hourly_html(cells))

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

# The banner and officials always use the genuine estimate; only the resident card shows the simulation.
genuine_status=resident_view.resident_status(real_prob,input_time,valid,generated_time or retrieved_time,stale,False)
if portal_mode:
    official=official_portal.sign_in(secret,failed_official_logins(),LOGIN_WINDOW_SECONDS,MAX_FAILED_LOGINS)
    if official:
        events,_=resident_alerts.load_events(secret)
        operations,operations_error=resident_alerts.operations_store(secret)
        regional_now,regional_hour=upcoming_regional(state.regional)
        official_portal.render(official,events,operations,operations_error,regional_now,regional_hour,genuine_status)
    st.stop()

def more_safety_advice() -> None:
    st.session_state.dashboard_page='🛟 Safety Advice'

# Each piece of information has one place: Home summarises; every other section adds detail not shown on Home.
if page=='🏠 Dashboard':
    events,_=resident_alerts.load_events(secret)
    active_events=[e for e in events if warning_events.is_active(e)]
    st.html(resident_alerts.status_banner_html(active_events,genuine_status))
    if active_events:
        st.button('Open the warning',key='home_open_warning',on_click=open_warning,args=(active_events[0]['key'],),type='primary',icon=':material/warning:')
    st.html(resident_view.hero_html(resident))
    left,right=st.columns([2,1],gap='medium')
    with left:
        weather_card()
        hourly_forecast()
    with right:
        st.link_button('Official weather warnings (SAWS)',resident_alerts.SAWS_URL,icon=':material/campaign:',type='primary',width='stretch')
        st.button('Get free SMS storm warnings',key='cta_sms_alerts',on_click=open_sms_alerts,icon=':material/sms:',width='stretch')
        st.html(emergency_contacts.contacts_html())
    st.html(resident_view.quick_actions_html(advice))
    st.button('More safety advice',key='home_more_safety',on_click=more_safety_advice,icon=':material/health_and_safety:')
    if simulated:
        st.markdown('**SMS preview (simulation): this is the text a warning would contain. It has NOT been sent.**')
        st.code(resident_view.sms_preview(valid.isoformat() if valid is not None else ''),language=None,wrap_lines=True)

if page=='🛟 Safety Advice':
    st.html('<div class="section-title">Safety advice <small>Before a storm, and when a storm is close</small></div>')
    st.html(resident_view.advice_cards_html(resident_view.guidance('LOW'),'Be prepared'))
    st.caption('Full advice for when a storm is close:')
    st.html(resident_view.advice_cards_html(resident_view.guidance('WARNING'),'Act now'))
    st.caption(resident_view.OFFICIAL_NOTE)

layers: list[Any]=[]
TOOLTIP_STYLE={'backgroundColor':'#0f2440','color':'white','fontFamily':'Segoe UI, Arial, sans-serif','fontSize':'12px','borderRadius':'8px','padding':'8px 10px'}
map_tooltip=cast(Any, {'html':'<b>{name}</b><br/>{detail}', 'style':TOOLTIP_STYLE})
basemap_url=SATELLITE_STYLE_URL
if page=='🗺️ Weather Map':
    with st.container(border=True,key='map_card'):
        panel_title('Storm map · forecast rain and storm risk','cloud','map-heading')
        control_basemap,control_overlay=st.columns([1.6,1],gap='small')
        with control_basemap:
            basemap=st.segmented_control('Basemap',list(BASEMAPS),default='Satellite',key='map_basemap',
                                         help='Low data draws no map tiles: only the forecast overlay and labels.')
        with control_overlay:
            show_overlay=st.toggle('Rainfall overlay',value=True,key='map_overlay',help='Interpolated ECMWF forecast rainfall for the next hour.')
        basemap_url=BASEMAPS.get(basemap or 'Satellite',SATELLITE_STYLE_URL)
        hours=regional_hours(state.regional)
        map_hour=st.select_slider('Forecast hour (SAST)',options=hours,key='map_hour',format_func=lambda hour:f'{hour.tz_convert(SAST):%a %H:%M}',
                                  help='Step through the coming hours of the ECMWF rainfall forecast to see where rain is expected and how it moves.') if len(hours)>1 else None
        regional,regional_valid=upcoming_regional(state.regional,map_hour)
        regional_retrieved=local_time(state.regional.iloc[0].get('forecast_retrieved_at')) if not state.regional.empty else None
        regional_stale=bool(state.regional_error) or regional_retrieved is None or (datetime.now(SAST)-regional_retrieved.to_pydatetime()).total_seconds()>1800
        layers=[]
        if regional_stale:st.warning('OUTDATED / UNVERIFIED regional forecast. Rainfall overlay withheld until a fresh retrieval succeeds.')
        if not regional.empty and not regional_stale:
            regional=regional.assign(detail=f'Forecast rainfall for the hour ending {regional_valid:%H:%M} SAST (ECMWF grid point). Not radar.')
            try:
                overlay_image,bounds=make_rainfall_overlay(regional)
                if show_overlay:layers.append(pdk.Layer('BitmapLayer',image=String(overlay_image),bounds=bounds,opacity=.78))
                layers.append(pdk.Layer('ScatterplotLayer',regional,get_position='[lon, lat]',get_radius=700,get_fill_color=[25,45,65,150],pickable=True))
            except (ValueError,KeyError):st.warning('Incomplete rainfall grid: overlay unavailable. No artificial values substituted.')
        matatiele=pd.DataFrame([{'lat':MATATIELE_LAT,'lon':MATATIELE_LON,'name':'Matatiele','detail':'Location of the next-hour storm-risk model'}])
        ring=[int(level_color[i:i+2],16) for i in (1,3,5)]
        model_area=matatiele.assign(name=f'Storm model: {level}',detail=f'Next-hour model estimate {prob:.0%} for Matatiele (one forecast point)' if math.isfinite(prob) else 'No current model estimate')
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
        st.pydeck_chart(pdk.Deck(map_style=basemap_url,initial_view_state=pdk.ViewState(latitude=MATATIELE_LAT,longitude=MATATIELE_LON,zoom=7.4,pitch=0),layers=layers,tooltip=map_tooltip),width='stretch',height=360)
        st.caption('Drag, zoom, or tap a point for its forecast value.')
        if not regional.empty and not regional_stale:
            st.html(f'<div class="map-legend"><div class="title">Risk of heavy rain · hour ending {regional_valid:%H:%M} SAST (forecast mm)</div><div class="rain-legend"></div>'
                    '<div class="legend-labels"><span>0</span><span>0.1</span><span>1</span><span>3</span><span>5</span><span>10</span><span>20</span><span>40+</span></div>'
                    '<div class="note">Coloured areas: rain forecast by ECMWF at 25 grid points, smoothed. Not radar or observed rainfall. Ring: storm-model level for Matatiele.'
                    +('' if show_overlay else ' Overlay hidden.')+'</div></div>')
        with st.expander('Map data and method'):
            if not regional.empty and not regional_stale:
                st.caption(f'ECMWF / Open-Meteo: hour ending {regional_valid:%d %b %Y %H:%M SAST}; retrieved {regional_retrieved:%d %b %Y %H:%M SAST}. Bilinear interpolation of 25 actual grid samples, not radar. Colour intervals are nonlinear.')
                st.caption(f'Sampled rainfall range: {regional.precipitation_mm.min():.2f} to {regional.precipitation_mm.max():.2f} mm. Dry areas are transparent; trace rainfall is faint.')
            st.caption('Town labels are geographic references. The Random Forest storm prediction applies only to Matatiele.')
        if regional.empty or regional_stale:st.info('Matatiele is shown in red. Refresh to retrieve genuine regional rainfall forecasts.')

if page=='🌦️ Live Forecast':
    st.html('<div class="section-title">Forecast <small>The next 36 hours and the storm ingredients the model uses</small></div>')
    forecast_chart()
    cape,previous=number(latest,'cape'),number(latest,'previous_cape')
    change=f'{cape-previous:+.0f} J/kg vs previous hour' if math.isfinite(cape) and math.isfinite(previous) else 'Change unavailable'
    st.html(dashboard_theme.ingredient_tiles_html([
        ('zap','Storm energy (CAPE)',weather_value(cape,'J/kg',0),change),
        ('droplets','Dew point',weather_value(number(latest,'dewpoint_c'),chr(176)+'C'),'Moisture in the air'),
        ('cloud-rain','Showers',weather_value(number(latest,'showers_mm'),'mm'),'Convective rain in the input hour'),
        ('clock','Model input hour',f'{input_time:%H:%M} SAST' if input_time is not None else 'Unknown','ECMWF forecast used by the model')]))
    st.caption('Forecast values from ECMWF via Open-Meteo, not observations.')

if page=='📈 Risk Analysis':
    st.html('<div class="section-title">Risk analysis <small>How the next-hour model estimate compares with the warning level</small></div>')
    left,right=st.columns([1,1.3],gap='medium')
    with left,st.container(border=True,key='risk_card'):
        panel_title('Next-hour prediction','risk')
        usable=math.isfinite(prob) and 0<=prob<=1
        gauge_value=prob if usable else 0.0
        value_text=f'{prob:.1%}' if usable else 'Unavailable'
        gauge=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 165" font-family="Arial, sans-serif"><path d="M25 120 A105 105 0 0 1 235 120" fill="none" stroke="#d4dce7" stroke-width="20" stroke-linecap="round"/><path d="M25 120 A105 105 0 0 1 235 120" fill="none" stroke="{level_color}" stroke-width="20" stroke-linecap="round" pathLength="100" stroke-dasharray="{gauge_value*100} 100"/></svg>'
        st.html(f'<div class="risk-status">{"OUTDATED / UNVERIFIED SAVED RESULT" if stale else "RANDOM FOREST - FIXED HOURLY TARGET"}</div><div class="risk-body single"><div class="risk-gauge">{svg_image(gauge,"Storm probability "+value_text)}<div class="gauge-value">{value_text}</div><div class="gauge-label">Storm probability</div><span class="risk-badge" style="--accent:{level_color};--tint:{level_color}25">{level} RISK</span></div></div>')
    with right:
        st.html(dashboard_theme.risk_scale_html(prob if math.isfinite(prob) else None,threshold))
        st.html(resident_view.details_html(genuine_status))
        st.caption(f'Target interval: {interval_label(valid)} · generated {generated_time.strftime("%d %b %H:%M SAST") if generated_time is not None else "unknown"} · fixed hourly target, not a rolling 60 minutes.')

if page=='🕒 Historical Data':
    st.html('<div class="section-title">Historical data <small>Saved model predictions (genuine records only)</small></div>')
    if not hist.empty and {'prediction_for','storm_probability'}.issubset(hist.columns):
        series=pd.DataFrame(hist[['prediction_for','storm_probability']]).copy()
        series['target']=pd.to_datetime(series['prediction_for'],utc=True,errors='coerce')
        series['Probability (%)']=numeric_series(pd.Series(series['storm_probability']))*100
        series=series.dropna()
        valid_probabilities=numeric_series(pd.Series(series['Probability (%)'])).between(0,100)
        series=pd.DataFrame(series.loc[valid_probabilities]).sort_values(by='target').tail(24)
        series[TARGET_LABEL]=series['target'].dt.tz_convert(SAST).dt.strftime('%d %b %Y %H:%M')
        if not series.empty:
            series['Target (SAST)']=series['target'].dt.tz_convert(SAST).dt.tz_localize(None)
            points=alt.Chart(series).mark_line(point=True,color='#1268c4').encode(x=alt.X('Target (SAST):T',title=None,axis=alt.Axis(format='%d %b %H:%M',labelAngle=0,tickCount=6)),y=alt.Y('Probability (%):Q',scale=alt.Scale(domain=[0,100])),tooltip=[alt.Tooltip('Target (SAST):T',format='%d %b %H:%M'),alt.Tooltip('Probability (%):Q',format='.2f')]).properties(height=230)
            line=alt.Chart(pd.DataFrame({'threshold':[35]})).mark_rule(color='#d93449',strokeDash=[6,4]).encode(y='threshold:Q')
            st.altair_chart(dashboard_theme.style_chart(points+line,theme_mode),width='stretch',theme=None)
        else:st.info('No valid recorded probabilities available.')
    else:st.info('Recorded predictions will appear after successful forecast updates.')
    render_history(hist)

if page=='🚨 Alerts':
    resident_alerts.render_alerts(secret,genuine_status)
    if is_admin:
        st.markdown('**Operational status (administrators)**')
        a,b,c=st.columns(3)
        with a:status_card('Dashboard warnings','OUTDATED' if stale else 'AVAILABLE','Saved forecast freshness' if stale else 'Genuine forecast risk classification','warning','amber' if stale else 'green',compact=True)
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
    st.html('<div class="section-title">About <small>How this research system works</small></div>')
    st.html(dashboard_theme.flow_html())
    a,b,c=st.columns(3)
    verified=not stale and not state.regional_error
    with a:status_card('System status','ONLINE' if verified else 'SAVED DATA','Latest retrieval verified' if verified else 'Outdated / unverified','wifi','green' if verified else 'amber')
    with b:status_card('Model','Random Forest','29 forecast features · ERA5-trained','model','blue')
    with c:status_card('Warning level',f'{threshold:.0%}','Next-hour estimate','warning','red')
    st.html('<div class="research-notice"><strong>Academic research Beta</strong> · Smart Resilient Storm Early Warning System for Low Connectivity Environments: A Case of Matatiele. Not an official warning service: follow SAWS and local disaster management.</div>')
    with st.expander('Forecast source and timestamps'):
        st.caption(f'Model forecast retrieved: {retrieved_time.strftime("%d %b %Y %H:%M:%S SAST") if retrieved_time is not None else "Unknown (legacy saved record)"} · Forecast input hour: {input_time.strftime("%d %b %Y %H:%M SAST") if input_time is not None else "Unknown"} · Forecast target (hour ending): {valid.strftime("%d %b %Y %H:%M SAST") if valid is not None else "Unknown"}')
        st.caption(f'Prediction generated: {generated_time.strftime("%d %b %Y %H:%M:%S SAST") if generated_time is not None else "Unknown (legacy saved record)"}. Target interval: {interval_label(valid)}. Fixed hourly target, not a rolling 60-minute window. Instantaneous conditions are valid at their timestamp; rainfall covers the preceding hour.')
        st.caption('ECMWF run issue time is not supplied by this API response; retrieval time is recorded separately.')

st.divider()
st.caption('Matatiele Smart Resilient Storm Early Warning System · Academic research Beta · Forecast data: Open-Meteo / ECMWF · Historical model development: ERA5 · SAST (UTC+2)')
