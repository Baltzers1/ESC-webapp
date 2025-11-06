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

# --- PLOT ---
fig = go.Figure()
max_peak = df_day["peak amp (a)"].max()
colors = px.colors.sequential.Blues_r

for _, row in df_day.iterrows():
    avg = row["average amp (a)"]
    peak = row["peak amp (a)"]
    dur = (row["clipped_end"] - row["clipped_start"]).total_seconds() / 60
    color_idx = int((peak / max_peak) * (len(colors) - 1)) if max_peak > 0 else 0
    color = colors[color_idx]

    hover = (
        f"<b>{row['clipped_start']:%H:%M} – {row['clipped_end']:%H:%M}</b> ({dur:.0f} min)<br>"
        f"<b>SoC:</b> {row['SoC Start (%)']}% → {row['SoC Stop (%)']}% (+{row['SoC Stop (%)'] - row['SoC Start (%)']}%)<br>"
        f"<b>Energi:</b> {row['Charged Energy (kWh)']:.1f} kWh<br>"
        f"<b>Gj.snitt:</b> {avg:.1f} A | <b>Topp:</b> {peak:.1f} A"
    )

    fig.add_trace(go.Scatter(
        x=[row["start_clock"], row["end_clock"], row["end_clock"], row["start_clock"]],
        y=[0, 0, avg, avg],
        fill='toself',
        mode='none',
        fillcolor=color,
        line=dict(width=1, color='black'),
        hoverinfo='text',
        text=hover,
        showlegend=False
    ))

START_OF_DAY = datetime(1970, 1, 1, 0, 0, 0)
END_OF_DAY = datetime(1970, 1, 1, 23, 59, 59)

fig.update_xaxes(title="Tid på døgnet", type="date", tickformat="%H:%M", dtick=3600000, range=[START_OF_DAY, END_OF_DAY])
fig.update_yaxes(title="Gjennomsnittlig Ampere (A)", range=[0, df_day["average amp (a)"].max() * 1.2])
fig.update_layout(
    title=f"Ladeøkter {chosen:%d.%m.%Y}",
    height=650,
    hovermode="x unified",
    plot_bgcolor='white',
    margin=dict(l=70, r=30, t=80, b=60)
)

st.plotly_chart(fig, use_container_width=True)
