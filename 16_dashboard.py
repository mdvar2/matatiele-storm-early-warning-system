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
import tempfile
import logging
import json
import numpy as np
from PIL import Image

import altair as alt
import pandas as pd
import streamlit as st
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
st.set_page_config(page_title='Matatiele | Storm Early Warning Research', page_icon='⛈️', layout='centered' if text_view else 'wide',
                   initial_sidebar_state='collapsed' if text_view else 'auto')

# Theme: sky background, cards, light/dark palettes (dashboard_theme.py). Not loaded in the text view.
if not text_view:st.html('<style>'+dashboard_theme.CSS+'</style>')

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

def upcoming_regional(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None]:
    if frame.empty:return pd.DataFrame(),None
    values=frame.copy()
    values['forecast_hour']=pd.to_datetime(values['forecast_hour'],utc=True,errors='coerce')
    target=next_complete_hour_endpoint(datetime.now(UTC))
    values=pd.DataFrame(values.loc[(values['forecast_hour']==target) & (values['sample_id']<25)])
    if values.empty:return pd.DataFrame(),None
    if len(values)!=25 or values['sample_id'].nunique()!=25:return pd.DataFrame(),None
    values['name']=values.apply(lambda row:f"ECMWF sample: {float(row['precipitation_mm']):.2f} mm",axis=1)
    valid_time=target.tz_convert(SAST)
    return values,valid_time if isinstance(valid_time,pd.Timestamp) else None

def fetch_six_hour_weather() -> pd.DataFrame:
    return six_hour_forecast(refresh_state().regional, datetime.now(SAST),complete_intervals=True)


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
    # Continuous palette: transparent for zero; blue, cyan, green, yellow, orange, red for rain.
    stops=np.array([0,0.1,1,3,5,10,20,40],dtype=float)
    colors=np.array([[95,170,230,0],[55,140,238,22],[25,120,234,115],
                     [30,180,182,160],[50,190,90,170],[249,215,50,190],
                     [250,115,32,205],[205,42,62,220]],dtype=float)
    rgba=np.stack([np.interp(rainfall,stops,colors[:,c]) for c in range(4)],axis=2)
    # The source sampling resolution is coarse; interpolation must not imply high-res radar.
    out=Image.frombytes('RGBA',(int(rgba.shape[1]),int(rgba.shape[0])),np.clip(rgba,0,255).astype('uint8').tobytes())
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


def render_forecast_chart(state: RefreshState) -> None:
    panel_title('Next 6 hourly intervals · Matatiele','clock')
    try:
        six=fetch_six_hour_weather()
        chart_retrieved=local_time(state.regional.iloc[0].get('forecast_retrieved_at')) if not state.regional.empty else None
        if state.regional_error or chart_retrieved is None or (datetime.now(SAST)-chart_retrieved.to_pydatetime()).total_seconds()>1800:
            st.warning('OUTDATED / UNVERIFIED precipitation forecast: saved samples only.')
        if not six.empty:
            six=six[six['time']>=datetime.now(SAST)].copy()
            plot=pd.DataFrame(six[['time','precipitation','cloud_cover']]).copy()
            plot['precipitation']=numeric_series(pd.Series(plot['precipitation']))
            plot=pd.DataFrame(plot.loc[np.isfinite(plot['precipitation']) & (plot['precipitation']>=0)]).copy()
            if plot.empty:raise ValueError('Cached precipitation forecast expired or has no valid samples')
            plot['Hour (SAST)']=pd.Series(plot['time']).dt.strftime('%H:%M')
            plot['Interval']=plot['time'].apply(interval_label)
            if len(plot)<6:st.warning('Incomplete six-hour forecast: missing or invalid hourly samples; gaps are not filled.')
            chart=alt.Chart(plot).mark_bar(color='#277de0',cornerRadiusTopLeft=4,cornerRadiusTopRight=4).encode(
                x=alt.X('Hour (SAST):O',title='Hour ending (SAST)',sort=forecast_axis_order(pd.Series(plot['time'])),axis=alt.Axis(labelAngle=0,labelFontSize=10)),
                y=alt.Y('precipitation:Q',title='Forecast rainfall (mm)',axis=alt.Axis(format='.1f')),
                tooltip=[alt.Tooltip('Interval:N',title='Rainfall interval (SAST)'),alt.Tooltip('precipitation:Q',title='Rainfall (mm)',format='.2f'),
                         alt.Tooltip('cloud_cover:Q',title='Cloud cover (%)',format='.0f')]).properties(height=225)
            st.altair_chart(chart,width='stretch')
            st.caption(f'ECMWF IFS 0.25{chr(176)} via Open-Meteo | Hourly endpoints {plot["time"].min():%d %b %Y %H:%M} to {plot["time"].max():%d %b %Y %H:%M} SAST. Rainfall sums cover the preceding hour; selection starts with the next complete hourly interval. {len(plot)} genuine samples, not model probabilities.')
        else:st.info('No future hourly precipitation forecast available.')
    except Exception as exc:
        st.warning('Six-hour forecast unavailable or expired. No old precipitation values are shown; saved model predictions remain accessible.')


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
        st.dataframe(display[cols],hide_index=True,width='stretch',height=330,
            column_config={'Probability (%)':st.column_config.ProgressColumn(format='%.1f%%',min_value=0,max_value=100)})
        st.caption('Only genuine saved model predictions are included; demonstration values are excluded.')
    else:st.info('Prediction history will appear after multiple successful updates.')


def render_recent_table(hist: pd.DataFrame) -> None:
    panel_title('Recent predictions','table')
    if hist.empty or 'prediction_for' not in hist:
        st.info('No saved predictions yet.');return
    frame=hist.copy()
    frame['prediction_for']=pd.to_datetime(frame['prediction_for'],utc=True,errors='coerce')
    frame=frame.dropna(subset=['prediction_for']).sort_values('prediction_for',ascending=False).head(6)
    rows=[]
    for _,row in frame.iterrows():
        timestamp=local_time(row['prediction_for'])
        probability=number(row,'storm_probability')
        label,color=risk(probability,threshold)
        percent=f'{probability:.1%}' if math.isfinite(probability) and 0<=probability<=1 else 'Unavailable'
        rainfall=weather_value(number(row,'precipitation_mm'),'',1).strip()
        time_label=timestamp.strftime('%d %b %H:%M') if timestamp is not None else 'Unknown'
        generated=html.escape(timestamp_labels({'prediction_generated_at':row.get('prediction_generated_at')})[GENERATED_LABEL])
        rows.append(f'<tr><td title="Prediction generated (SAST): {generated}">{time_label}</td><td>{percent}</td><td><span class="table-badge" style="color:{color};background:{color}20">{label}</span></td><td>{rainfall}</td></tr>')
    st.html('<table class="prediction-table"><thead><tr><th>Forecast target (SAST)</th><th>Probability</th><th>Risk</th><th>Rain (mm)</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table><div class="table-note">Target is the hour ending, not execution time. Rain is from the input hour. Actual saved model predictions · All records in Historical Data</div>')

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
    navigation = ['🏠 Dashboard','🛟 Safety Advice','🌦️ Live Forecast','🗺️ Weather Map','📈 Risk Analysis','🕒 Historical Data','📱 Alerts & Notifications','ℹ️ About']
    if 'dashboard_page' not in st.session_state:st.session_state.dashboard_page=navigation[0]
    nav_icons=['home','health_and_safety','partly_cloudy_day','public','monitoring','insert_chart','notifications','info']
    for item,nav_icon in zip(navigation,nav_icons):
        if st.button(item.split(' ',1)[1],icon=f':material/{nav_icon}:',key='nav_'+item,width='stretch',
                     type='primary' if st.session_state.dashboard_page==item else 'secondary'):
            st.session_state.dashboard_page=item
            st.rerun()
    page=st.session_state.dashboard_page
    st.divider()
    # The login is shown only via ?admin=1 (or while signed in), never in the text view;
    # the password check is unchanged.
    if not text_view and (show_admin_login or st.session_state.admin_authenticated):
        with st.expander('🔐 Administrator Access'):
            if st.session_state.admin_authenticated:
                st.success('Administrator access enabled')
                if st.button('Log Out',width='stretch'):
                    st.session_state.admin_authenticated=False;st.rerun()
            else:
                entered=st.text_input('Administrator Password',type='password')
                if st.button('Unlock Admin Controls',width='stretch'):
                    password=secret('ADMIN_PASSWORD')
                    if not password:st.error('Administrator password is not configured.')
                    elif hmac.compare_digest(entered.encode('utf-8'),password.encode('utf-8')):
                        st.session_state.admin_authenticated=True;st.rerun()
                    else:st.error('Incorrect password.')
    is_admin=bool(st.session_state.admin_authenticated) and not text_view  # text view is public-only
    st.html('<div class="sidebar-note">Next-hour storm risk for Matatiele,<br>with safety advice for residents.<br><br>Research prototype: not an official<br>SAWS warning service.<br><br><a href="?view=text" style="color:#7cc0f0">Low-data text version</a></div>')
    if is_admin:
        st.divider()
        st.markdown('**Administrator controls**')
        test_mode=st.toggle('🧪 Warning simulation (on screen only)',key='presentation_test_mode',value=False,help='Shows a clearly labelled 60% simulated model output, the warning advice and an SMS preview. Nothing is sent, saved or recorded; genuine data return when switched off.')
        if test_mode:st.html('<div style="background:#4a0f6b;color:#ffffff;border:3px solid #ffd23f;border-radius:10px;padding:10px 12px;font-weight:700;font-size:13px;line-height:1.5">Simulation on: on screen only. No SMS can be sent and no records change.</div>')
        if not test_mode and sms_is_configured() and st.button('📲 Send Test SMS',width='stretch'):
            outcome=send_test_sms()
            (st.success if outcome.get('sent') else st.error)('SMS accepted by provider.' if outcome.get('sent') else 'SMS request failed. Review private server logs.')
    else:test_mode=False
    if not is_admin:st.session_state.presentation_test_mode=False

if not text_view:st.html(f'<div class="hero"><div class="hero-main">{ui_icon("cloud")}<div><h1>Matatiele Smart Resilient Storm Early Warning System</h1><p>Is a storm likely in Matatiele in the next hour, and what should you do?</p></div></div><div class="clock-card">{datetime.now(SAST):%d %B %Y &nbsp; %H:%M} SAST<small>Dashboard time · Research Beta</small></div></div>')
if not text_view:
    # Small screens hide the sidebar behind a menu, so the same sections are offered here too.
    st.session_state.mobile_nav_choice=page
    def _go_to_mobile_section():
        if st.session_state.get('mobile_nav_choice'):st.session_state.dashboard_page=st.session_state.mobile_nav_choice
    with st.container(key='mobile_nav'):
        st.segmented_control('Dashboard section',navigation,key='mobile_nav_choice',on_change=_go_to_mobile_section,label_visibility='collapsed')

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
    st.html(f'<div style="{SIM_BANNER_STYLE}">🧪 SIMULATION ONLY: the resident card shows a fixed 60% simulated model output, not a forecast. Genuine predictions and records are unchanged, and SMS sending is disabled.</div>')

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
    st.warning('⚠️ **Saved forecast / outdated prediction.** The latest retrieval failed, is too old, lacks a retrieval timestamp, or no longer matches the next complete hourly interval. This is NOT a current storm-risk assessment. Refresh is required.')

# GitHub Actions is the sole storm-warning sender; dashboard tests remain manual.
if is_admin and not test_mode and not stale and threshold<=real_prob<=1:
    st.error('The current prediction meets the warning threshold. Storm warning SMS is reserved for the scheduled GitHub Actions worker; this dashboard cannot send weather warnings.')

# Show real data in every chart. Do not invent a spatial rainfall/radar field.
forecast_status='OUTDATED' if stale else 'FIXED HOURLY TARGET'
model_status='FILE AVAILABLE' if (MODEL/'random_forest_live_model.pkl').exists() else 'MODEL FILE MISSING'
if page in ('🏠 Dashboard','🛟 Safety Advice'):
    st.html(resident_view.card_html(resident))
    st.html(resident_view.guidance_html(advice))
    if simulated:
        st.markdown('**SMS preview (simulation): this is the text a warning would contain. It has NOT been sent.**')
        st.code(resident_view.sms_preview(valid.isoformat() if valid is not None else ''),language=None,wrap_lines=True)
if page=='🛟 Safety Advice':
    st.caption('The advice above matches the current status. Full advice for when a storm is close:')
    st.html(resident_view.guidance_html(resident_view.guidance('WARNING')))
layers: list[Any]=[]
TOOLTIP_STYLE={'backgroundColor':'#0f2440','color':'white','fontFamily':'Segoe UI, Arial, sans-serif','fontSize':'12px','borderRadius':'8px','padding':'8px 10px'}
map_tooltip=cast(Any, {'html':'<b>{name}</b><br/>{detail}', 'style':TOOLTIP_STYLE})
basemap_url=SATELLITE_STYLE_URL
if page in ('🏠 Dashboard','🗺️ Weather Map'):
    st.html('<div class="section-title">Next-hour forecast for Matatiele <small>ECMWF forecast data and the research model, not observations</small></div>')
    left,right=st.columns([2.15,1],gap='small')
    with left,st.container(border=True,key='map_card'):
        panel_title('Rainfall forecast map (next hour)','cloud','map-heading')
        control_basemap,control_overlay=st.columns([1.6,1],gap='small')
        with control_basemap:
            basemap=st.segmented_control('Basemap',list(BASEMAPS),default='Satellite',key='map_basemap',
                                         help='Low data draws no map tiles: only the forecast overlay and labels.')
        with control_overlay:
            show_overlay=st.toggle('Rainfall overlay',value=True,key='map_overlay',help='Interpolated ECMWF forecast rainfall for the next hour.')
        basemap_url=BASEMAPS.get(basemap or 'Satellite',SATELLITE_STYLE_URL)
        regional,regional_valid=upcoming_regional(state.regional)
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
        st.caption('Drag to pan, scroll or pinch to zoom, hover or tap a point for its forecast value.')
        if not regional.empty and not regional_stale:
            st.html('<div class="map-legend"><div class="title">Forecast rainfall in the next hour (mm)</div><div class="rain-legend"></div>'
                    '<div class="legend-labels"><span>0</span><span>0.1</span><span>1</span><span>3</span><span>5</span><span>10</span><span>20</span><span>40+</span></div>'
                    '<div class="note">Interpolated from 25 ECMWF forecast grid points. This is a forecast, not radar or observed rainfall.'
                    +('' if show_overlay else ' Overlay hidden.')+'</div></div>')
            st.caption(f'ECMWF / Open-Meteo: hour ending {regional_valid:%d %b %Y %H:%M SAST}; retrieved {regional_retrieved:%d %b %Y %H:%M SAST}. Bilinear interpolation of 25 actual grid samples, not radar. Colour intervals are nonlinear.')
            st.caption(f'Sampled rainfall range: {regional.precipitation_mm.min():.2f} to {regional.precipitation_mm.max():.2f} mm. Dry areas are transparent; trace rainfall is faint.')
        st.caption('Town labels are geographic references. The Random Forest storm prediction applies only to Matatiele.')
        if regional.empty or regional_stale:st.info('Matatiele is shown in red. Refresh to retrieve genuine regional rainfall forecasts.')
    with right:
        with st.container(border=True,key='weather_card'):
            panel_title('Forecast weather - Matatiele','cloud')
            condition_kind,condition_label=dashboard_theme.weather_condition(number(latest,'precipitation_mm'),number(latest,'cloud_cover_percent'),input_time.hour if input_time is not None else None)
            details=[('Cloud cover',weather_value(number(latest,'cloud_cover_percent'),'%',0)),('Wind speed',weather_value(number(latest,'wind_speed_ms'),'m/s')),('Wind gust',weather_value(number(latest,'wind_gust_ms'),'m/s')),('Pressure',weather_value(number(latest,'pressure_msl_hpa'),'hPa',0))]
            detail_html=''.join(f'<div class="weather-detail"><span>{label}</span><strong>{value}</strong></div>' for label,value in details)
            forecast_hour=f'{input_time:%H:%M} SAST' if input_time is not None else 'unknown hour'
            st.html(f'<div class="weather-body"><div class="weather-primary">{svg_image(dashboard_theme.weather_icon_svg(condition_kind),condition_label)}<div class="temperature">{weather_value(number(latest,"temperature_c"),chr(176)+"C")}</div><div class="condition">{html.escape(condition_label)}<small>Rainfall {weather_value(number(latest,"precipitation_mm"),"mm")} in the hour</small></div></div><div>{detail_html}</div></div><div class="weather-status">{"OUTDATED SAVED CONDITIONS" if stale else f"ECMWF forecast for {forecast_hour} - not an observation"}</div>')
        with st.container(border=True,key='risk_card'):
            panel_title('Next-hour prediction','risk')
            usable=math.isfinite(prob) and 0<=prob<=1
            gauge_value=prob if usable else 0.0
            value_text=f'{prob:.1%}' if usable else 'Unavailable'
            gauge=f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 165" font-family="Arial, sans-serif"><path d="M25 120 A105 105 0 0 1 235 120" fill="none" stroke="#d4dce7" stroke-width="20" stroke-linecap="round"/><path d="M25 120 A105 105 0 0 1 235 120" fill="none" stroke="{level_color}" stroke-width="20" stroke-linecap="round" pathLength="100" stroke-dasharray="{gauge_value*100} 100"/></svg>'
            keys=''.join(f'<div class="risk-key"><i style="background:{color}"></i>{label}</div>' for color,label in [('#30b262','Low (below 10%)'),('#ffc32d','Elevated (10-19%)'),('#fa782b','Moderate (20-34%)'),('#ed394b','Warning (35%+)')])
            st.html(f'<div class="risk-status">{"OUTDATED / UNVERIFIED SAVED RESULT" if stale else "RANDOM FOREST - FIXED HOURLY TARGET"}</div><div class="risk-body"><div class="risk-gauge">{svg_image(gauge,"Storm probability "+value_text)}<div class="gauge-value">{value_text}</div><div class="gauge-label">Storm probability</div><span class="risk-badge" style="--accent:{level_color};--tint:{level_color}25">{level} RISK</span></div><div>{keys}</div></div>')


if page=='🏠 Dashboard':
    chart_column,sample_column,table_column=st.columns([1.15,.9,1.1],gap='small')
    with chart_column,st.container(border=True,key='six_card'):
        render_forecast_chart(state)
    with sample_column,st.container(border=True,key='sample_card'):
        panel_title('Regional forecast detail','map')
        st.pydeck_chart(pdk.Deck(map_style=basemap_url,
            initial_view_state=pdk.ViewState(latitude=-30.39,longitude=MATATIELE_LON,zoom=7.4,pitch=0),
            layers=layers,tooltip=map_tooltip),width='stretch',height=215)
        st.caption('Same genuine ECMWF precipitation forecast. Spatial interpolation, not radar.')
    with table_column,st.container(border=True,key='predictions_card'):
        render_recent_table(hist)

if page=='🏠 Dashboard':
    st.html('<div class="section-title">System and model status <small>Technical details for researchers and administrators</small></div>')
    cards=st.columns(5,gap='small')
    verified=not stale and not state.regional_error
    with cards[0]:status_card('System status','ONLINE' if verified else 'SAVED DATA','Latest retrieval verified' if verified else 'Outdated / unverified','wifi','green' if verified else 'amber')
    with cards[1]:status_card('Model status','READY' if not stale and level!='UNAVAILABLE' else 'SAVED','Random Forest (29 features)','model','blue')
    with cards[2]:status_card('Current risk level',level,f'{prob:.1%} probability' if math.isfinite(prob) and 0<=prob<=1 else 'No valid probability','risk',{'LOW':'green','ELEVATED':'amber','MODERATE':'amber','WARNING':'red'}.get(level,'gray'))
    with cards[3]:status_card('Alert threshold',f'{threshold:.0%}','For the next hour','warning','red')
    horizon=f'{input_time:%H:%M} – {valid:%H:%M} SAST' if input_time is not None and valid is not None else 'Target time unavailable'
    with cards[4]:status_card('Forecast horizon','Next 1 hour',horizon,'clock','blue',True)
    st.caption(f'Target interval: {interval_label(valid)}. Next complete hourly interval, not a rolling 60-minute forecast. Prediction generated: {generated_time.strftime("%d %b %Y %H:%M:%S SAST") if generated_time is not None else "Unknown (legacy saved record)"}.')

if page=='🕒 Historical Data':
    panel_title('Historical predictions','table')
    render_history(hist)

if page in ('🌦️ Live Forecast','📈 Risk Analysis'):
    panel_title('Forecast inputs and next-hour validity','clock')
    a,b,c,d=st.columns(4)
    with a:information_card('Forecast input (SAST)',input_time.strftime('%H:%M') if input_time is not None else 'Unknown',input_time.strftime('%d %b %Y') if input_time is not None else 'No input timestamp')
    with b:information_card('Target hour ending (SAST)',valid.strftime('%H:%M') if valid is not None else 'Unknown',valid.strftime('%d %b %Y') if valid is not None else 'No prediction timestamp')
    with c:information_card('CAPE',weather_value(number(latest,'cape'),'J/kg',0),'Genuine ECMWF forecast input')
    with d:information_card('Dew point',weather_value(number(latest,'dewpoint_c'),chr(176)+'C'),'Genuine ECMWF forecast input')
    st.caption(f'Target interval: {interval_label(valid)}. Next complete hourly interval, one hour ahead of the ECMWF input timestamp; not a rolling 60-minute forecast. Generated: {generated_time.strftime("%d %b %Y %H:%M:%S SAST") if generated_time is not None else "Unknown (legacy saved record)"}.')
    if 'Live Forecast' in page:
        with st.container(border=True,key='live_six_card'):render_forecast_chart(state)
        st.caption('Six-hour precipitation and next-hour Random Forest probability are separate outputs.')
    else:
        a,b=st.columns([1.2,1])
        with a:
            information_card('Saved next-hour result' if stale else 'Next-hour Random Forest result',f'{prob:.1%} - {level}' if math.isfinite(prob) and 0<=prob<=1 else 'Unavailable','29 live-compatible features; warning threshold 35%')
            if math.isfinite(prob) and 0<=prob<=1:
                comparison=pd.DataFrame({'Output':['Next-hour storm probability'],'Probability (%)':[prob*100]})
                bars=alt.Chart(comparison).mark_bar(color=level_color,size=35).encode(x=alt.X('Probability (%):Q',scale=alt.Scale(domain=[0,100])),y=alt.Y('Output:N',title=None),tooltip=[alt.Tooltip('Probability (%):Q',format='.2f')])
                rule=alt.Chart(pd.DataFrame({'Warning threshold (%)':[35]})).mark_rule(color='#d93449',strokeDash=[6,4]).encode(x='Warning threshold (%):Q',tooltip=['Warning threshold (%):Q'])
                st.altair_chart((bars+rule).properties(height=100),width='stretch')
                st.caption(f'{abs(prob*100-35):.1f} percentage points {"above" if prob>=threshold else "below"} the warning threshold. Dashed line: 35%.')
        with b:
            information_card('Forecast conditions at the input hour',weather_value(number(latest,'precipitation_mm'),'mm')+' rainfall',f'Temperature {weather_value(number(latest,"temperature_c"),chr(176)+"C")} / Gust {weather_value(number(latest,"wind_gust_ms"),"m/s")} / Cloud {weather_value(number(latest,"cloud_cover_percent"),"%",0)}')
            st.info('These forecast conditions provide context, not a causal explanation or feature importance. Rainfall millimetres and storm probability are separate outputs.')
        panel_title('Recorded prediction history - not future probabilities','risk')
        if not hist.empty and {'prediction_for','storm_probability'}.issubset(hist.columns):
            series=pd.DataFrame(hist[['prediction_for','storm_probability']]).copy()
            series['target']=pd.to_datetime(series['prediction_for'],utc=True,errors='coerce')
            series['Probability (%)']=numeric_series(pd.Series(series['storm_probability']))*100
            series=series.dropna()
            valid_probabilities=numeric_series(pd.Series(series['Probability (%)'])).between(0,100)
            series=pd.DataFrame(series.loc[valid_probabilities]).sort_values(by='target').tail(24)
            series[TARGET_LABEL]=series['target'].dt.tz_convert(SAST).dt.strftime('%d %b %Y %H:%M')
            if not series.empty:
                points=alt.Chart(series).mark_line(point=True,color='#1268c4').encode(x=alt.X('Forecast target (SAST):O',title='Recorded prediction target (SAST)',sort=None,axis=alt.Axis(labelAngle=-35)),y=alt.Y('Probability (%):Q',scale=alt.Scale(domain=[0,100])),tooltip=['Forecast target (SAST):O',alt.Tooltip('Probability (%):Q',format='.2f')]).properties(height=230)
                line=alt.Chart(pd.DataFrame({'threshold':[35]})).mark_rule(color='#d93449',strokeDash=[6,4]).encode(y='threshold:Q')
                st.altair_chart(points+line,width='stretch')
            else:st.info('No valid recorded probabilities available.')
        else:st.info('Recorded predictions will appear after successful forecast updates.')
        st.caption('Low <10%; Elevated 10% to <20%; Moderate 20% to <35%; Warning >=35%. History contains saved predictions, not a six-hour model forecast.')


if page=='📱 Alerts & Notifications':
    panel_title('How storm warnings reach you','warning')
    st.html('<div class="resident-guidance"><ul>'
            '<li><b>Every hour</b> the system checks the next-hour storm risk for Matatiele automatically, even when nobody has this page open.</li>'
            '<li><b>If the model estimate reaches the warning level</b>, a short SMS warning is sent to the phone numbers registered for this research trial. An SMS needs only mobile signal: no data or smartphone.</li>'
            '<li><b>During the research trial</b>, only registered numbers receive SMS. Use this page or the low-data text version to check the current status.</li>'
            '<li><b>This is a research prototype.</b> Always follow official warnings from the South African Weather Service (SAWS).</li></ul></div>')
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
                if cols:st.dataframe(log[cols].tail(20),hide_index=True,width='stretch')
            except Exception:st.info('SMS log is currently unavailable.')
        st.info('Automatic storm-warning checks are handled by an independent GitHub Actions scheduled worker. The dashboard does not need to remain open.')

if page=='ℹ️ About':
    panel_title('About this research system','model')
    information_card('Academic research project','Smart Resilient Storm Early Warning System for Low Connectivity Environments: A Case of Matatiele.','Research Beta serving Matatiele, Eastern Cape')
    a,b=st.columns(2)
    with a:information_card('Prediction model','Random Forest','Historical ERA5 training; 29 live-compatible predictors; next-hour target; 35% warning threshold.')
    with b:information_card('Weather forecast source','ECMWF via Open-Meteo','Regional rainfall uses real grid samples and labelled spatial interpolation. The six-hour weather forecast is separate from model probability.')
    st.caption('Future research considers local sensors, edge processing and resilient communication.')
    st.html('<div class="research-notice"><strong>Academic research Beta</strong><br>This prototype is not an official meteorological warning service. Consult SAWS and local disaster-management guidance for safety decisions.</div>')

with st.expander('Forecast source and timestamps'):
    st.caption(f'Model forecast retrieved: {retrieved_time.strftime("%d %b %Y %H:%M:%S SAST") if retrieved_time is not None else "Unknown (legacy saved record)"} · Forecast input hour: {input_time.strftime("%d %b %Y %H:%M SAST") if input_time is not None else "Unknown"} · Forecast target (hour ending): {valid.strftime("%d %b %Y %H:%M SAST") if valid is not None else "Unknown"}')
    st.caption(f'Prediction generated: {generated_time.strftime("%d %b %Y %H:%M:%S SAST") if generated_time is not None else "Unknown (legacy saved record)"}. Target interval: {interval_label(valid)}. Fixed hourly target, not a rolling 60-minute window. Instantaneous conditions are valid at their timestamp; rainfall covers the preceding hour.')
    st.caption('ECMWF run issue time is not supplied by this API response; retrieval time is recorded separately.')
st.divider()
st.caption('Matatiele Smart Resilient Storm Early Warning System · Academic research Beta · Forecast data: Open-Meteo / ECMWF · Historical model development: ERA5 · SAST (UTC+2)')
