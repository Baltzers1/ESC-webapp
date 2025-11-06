import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# --- KONFIG ---
st.set_page_config(page_title="Hurtiglader", layout="wide")
st.title("Hurtiglader – Ampere vs Tid på Døgnet")

# --- LESE DATA ---
@st.cache_data
def load_data(files):
    dfs = []
    for f in files:
        try:
            df = pd.read_csv(f, sep=";", encoding="latin1", on_bad_lines="warn")
            dfs.append(df)
            st.success(f"✓ {f.name}")
        except Exception as e:
            st.error(f"✗ {f.name}: {e}")
    return pd.concat(dfs, ignore_index=True) if dfs else None

uploaded = st.file_uploader("Last opp CSV-filer", accept_multiple_files=True)
if not uploaded:
    st.info("Last opp filer")
    st.stop()

df = load_data(uploaded)
df.columns = df.columns.str.strip()

# Sjekk kolonner
required = ["Start Time", "End Time", "Average Amp (A)", "Peak Amp (A)", "Charged Energy (kWh)", "SoC Start (%)", "SoC Stop (%)"]
if any(col not in df.columns for col in required):
    st.error(f"Manglende kolonner: {', '.join([c for c in required if c not in df.columns])}")
    st.stop()

# --- TID ---
df["start time"] = pd.to_datetime(df["Start Time"], format="%m/%d/%Y %H:%M:%S %z", utc=True).dt.tz_localize(None)
df["end time"] = pd.to_datetime(df["End Time"], format="%m/%d/%Y %H:%M:%S %z", utc=True).dt.tz_localize(None)
df = df.dropna(subset=["start time", "end time"])

df["average amp (a)"] = pd.to_numeric(df["Average Amp (A)"], errors="coerce")
df["peak amp (a)"] = pd.to_numeric(df["Peak Amp (A)"], errors="coerce")
df = df.dropna(subset=["average amp (a)", "peak amp (a)"])

# --- DATO ---
dates = df["start time"].dt.date.unique()
chosen = st.date_input("Velg dato", value=dates[0], min_value=min(dates), max_value=max(dates))

# --- SPLIT OVER MIDNATT ---
day_start = pd.Timestamp.combine(chosen, datetime.min.time())
day_end = day_start + pd.Timedelta(days=1)
overlap = df[(df["start time"] < day_end) & (df["end time"] > day_start)].copy()

if overlap.empty:
    st.warning(f"Ingen ladeøkter på {chosen:%d.%m.%Y}")
    st.stop()

rows = []
for _, r in overlap.iterrows():
    s = max(r["start time"], day_start)
    e = min(r["end time"], day_end)
    while s < e:
        nxt = s.normalize() + pd.Timedelta(days=1)
        chunk_end = min(nxt, e)
        rr = r.copy()
        rr["clipped_start"] = s
        rr["clipped_end"] = chunk_end
        rows.append(rr)
        s = chunk_end
df_day = pd.DataFrame(rows)

def to_clock(ts):
    return datetime(1970, 1, 1, ts.hour, ts.minute, ts.second)

df_day["start_clock"] = df_day["clipped_start"].apply(to_clock)
df_day["end_clock"] = df_day["clipped_end"].apply(to_clock)

# --- PLOT 3: Heatmap per dag ---
st.subheader("Samlet effekt (kW) per dag – heatmap")

daily_data = []
unique_dates = sorted(df["start time"].dt.date.unique())

if len(unique_dates) == 0:
    st.info("Ingen data tilgjengelig for heatmap.")
else:
    for date in unique_dates:
        day_start = pd.Timestamp.combine(date, datetime.min.time())
        day_end = day_start + pd.Timedelta(days=1)

        overlap = df[(df["start time"] < day_end) & (df["end time"] > day_start)].copy()
        if overlap.empty:
            daily_data.append({'date': date, 'max_avg_kw': 0, 'max_peak_kw': 0})
            continue

        rows = []
        for _, r in overlap.iterrows():
            s = max(r["start time"], day_start)
            e = min(r["end time"], day_end)
            while s < e:
                nxt = s.normalize() + pd.Timedelta(days=1)
                chunk_end = min(nxt, e)
                rr = r.copy()
                rr["clipped_start"] = s
                rr["clipped_end"] = chunk_end
                rows.append(rr)
                s = chunk_end
        day_df = pd.DataFrame(rows)

        time_index = pd.date_range(day_start, day_end - pd.Timedelta(seconds=1), freq='1min')
        temp = pd.DataFrame(index=time_index, columns=['avg_kw', 'peak_kw']).fillna(0)

        for _, row in day_df.iterrows():
            mask = (time_index >= row["clipped_start"]) & (time_index <= row["clipped_end"])
            avg_kw = row["average amp (a)"] * 0.4
            peak_kw = row["peak amp (a)"] * 0.4
            temp.loc[mask, 'avg_kw'] += avg_kw
            temp.loc[mask, 'peak_kw'] += peak_kw

        daily_data.append({
            'date': date,
            'max_avg_kw': temp['avg_kw'].max(),
            'max_peak_kw': temp['peak_kw'].max()
        })

    daily_df = pd.DataFrame(daily_data)

if daily_df.empty:
    st.info("Ingen data tilgjengelig for heatmap.")
    st.stop()

# VIS HEATMAP
fig3 = go.Figure()
fig3.add_trace(go.Heatmap(
    z=daily_df['max_peak_kw'],
    x=[d.strftime('%d.%m') for d in daily_df['date']],
    y=['Topp kW'],
    colorscale='Blues',
    zmin=0,
    hoverongaps=False,
    hovertemplate="<b>%{x}</b><br>Topp kW: <b>%{z:.1f}</b><br>Gj.snitt kW: <b>%{customdata[0]:.1f}</b><extra></extra>",
    customdata=daily_df[['max_avg_kw']].values
))

fig3.add_trace(go.Heatmap(
    z=daily_df['max_avg_kw'],
    x=[d.strftime('%d.%m') for d in daily_df['date']],
    y=['Gj.snitt kW'],
    colorscale='Blues',
    opacity=0.7,
    zmin=0,
    hoverongaps=False,
    showscale=False,
    hovertemplate="<b>%{x}</b><br>Gj.snitt kW: <b>%{z:.1f}</b><br>Topp kW: <b>%{customdata[0]:.1f}</b><extra></extra>",
    customdata=daily_df[['max_peak_kw']].values
))

fig3.update_layout(
    title="Maks samlet effekt per dag",
    xaxis_title="Dato",
    yaxis_title="",
    height=400,
    margin=dict(l=50, r=20, t=60, b=50),
    xaxis=dict(tickangle=45)
)

st.plotly_chart(fig3, use_container_width=True)

