import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# ====================== KONFIG ======================
st.set_page_config(page_title="Hurtiglader Analyse", layout="wide")
st.title("Hurtiglader – Ampere vs Tid på Døgnet")

# ====================== LESE DATA ======================
@st.cache_data
def load_data(uploaded_files):
    dfs = []
    for file in uploaded_files:
        try:
            # Les med semikolon og latin1 (norsk format)
            df = pd.read_csv(file, sep=";", encoding="latin1", on_bad_lines="warn")
            dfs.append(df)
            st.success(f"✓ {file.name}")
        except Exception as e:
            st.error(f"✗ {file.name}: {e}")
    if not dfs:
        st.stop()
    return pd.concat(dfs, ignore_index=True)

uploaded_files = st.file_uploader("Last opp eksport-filer (CSV)", accept_multiple_files=True)
if not uploaded_files:
    st.info("Last opp en eller flere CSV-filer fra HYC.")
    st.stop()

df = load_data(uploaded_files)

# Normaliser kolonnenavn
df.columns = df.columns.str.strip()

# Sjekk nødvendige kolonner
required = ["Start Time", "End Time", "Average Amp (A)", "Peak Amp (A)", "Charged Energy (kWh)", "SoC Start (%)", "SoC Stop (%)"]
missing = [col for col in required if col not in df.columns]
if missing:
    st.error(f"Manglende kolonner: {', '.join(missing)}")
    st.stop()

# ====================== TIDSHÅNDTERING ======================
df["start time"] = pd.to_datetime(df["Start Time"], format="%m/%d/%Y %H:%M:%S %z", utc=True, errors="coerce")
df["end time"] = pd.to_datetime(df["End Time"], format="%m/%d/%Y %H:%M:%S %z", utc=True, errors="coerce")
df = df.dropna(subset=["start time", "end time"])

# Fjern tidssone
df["start time"] = df["start time"].dt.tz_localize(None)
df["end time"] = df["end time"].dt.tz_localize(None)

# Konverter ampere til tall
df["average amp (a)"] = pd.to_numeric(df["Average Amp (A)"], errors="coerce")
df["peak amp (a)"] = pd.to_numeric(df["Peak Amp (A)"], errors="coerce")
df = df.dropna(subset=["average amp (a)", "peak amp (a)"])

# ====================== DATO-VALG ======================
all_dates = pd.to_datetime(df["start time"]).dt.date.unique()
chosen_date = st.date_input("Velg dato", value=all_dates[0], min_value=min(all_dates), max_value=max(all_dates))

# ====================== OVER-MIDNATT SPLIT ======================
day_start = pd.Timestamp.combine(chosen_date, datetime.min.time())
day_end = day_start + pd.Timedelta(days=1)

overlap = df[(df["start time"] < day_end) & (df["end time"] > day_start)].copy()
if overlap.empty:
    st.warning(f"Ingen ladeøkter på {chosen_date:%d.%m.%Y}")
    st.stop()

rows = []
for _, r in overlap.iterrows():
    s = max(r["start time"], day_start)
    e = min(r["end time"], day_end)
    while s < e:
        next_midnight = s.normalize() + pd.Timedelta(days=1)
        chunk_end = min(next_midnight, e)
        rr = r.copy()
        rr["clipped_start"] = s
        rr["clipped_end"] = chunk_end
        rows.append(rr)
        s = chunk_end

df_day = pd.DataFrame(rows)

# Dummy-klokkeslett
def to_day_clock(ts):
    return datetime(1970, 1, 1, ts.hour, ts.minute, ts.second)

df_day["start_clock"] = df_day["clipped_start"].apply(to_day_clock)
df_day["end_clock"] = df_day["clipped_end"].apply(to_day_clock)

# ====================== PLOTT ======================
fig = go.Figure()

for _, row in df_day.iterrows():
    y0, y1 = row["average amp (a)"], row["peak amp (a)"]
    hover = (
        f"<b>{row['clipped_start']:%H:%M} – {row['clipped_end']:%H:%M}</b><br>"
        f"Opprinnelig: {row['start time']:%d.%m %H:%M} – {row['end time']:%d.%m %H:%M}<br>"
        f"SoC: {row['SoC Start (%)']}% → {row['SoC Stop (%)']}% (+{row['SoC Stop (%)'] - row['SoC Start (%)']}%)<br>"
        f"Energi: {row['Charged Energy (kWh)']:.1f} kWh<br>"
        f"Gj.snitt: {y0:.1f} A | Topp: {y1:.1f} A<br>"
        f"Temp Minus: {row.get('Peak Pin Temp Minus (°C)', 'N/A')} °C | Plus: {row.get('Peak Pin Temp Plus (°C)', 'N/A')} °C"
    )
    fig.add_trace(go.Scatter(
        x=[row["start_clock"], row["end_clock"]],
        y=[y0, y1],
        mode="lines+markers",
        line=dict(width=10, color="#1f77b4"),
        marker=dict(size=8),
        hoverinfo="text",
        text=hover,
        name=f"Økt {row.name}"
    ))

START_OF_DAY = datetime(1970, 1, 1, 0, 0, 0)
END_OF_DAY = datetime(1970, 1, 1, 23, 59, 59)

fig.update_layout(
    title=f"Ladeøkter {chosen_date:%d.%m.%Y} – Ampere vs Klokkeslett",
    xaxis=dict(
        title="Tid på døgnet",
        type="date",
        tickformat="%H:%M",
        tickmode="linear",
        dtick=3600000,
        range=[START_OF_DAY, END_OF_DAY],
    ),
    yaxis=dict(title="Ampere (A)", range=[0, df_day["peak amp (a)"].max() * 1.1]),
    hovermode="x unified",
    height=600,
    showlegend=False
)

st.plotly_chart(fig, use_container_width=True)

# ====================== TABELL ======================
with st.expander("Vis rådata for valgt dato"):
    table_cols = [
        "start time", "end time", "clipped_start", "clipped_end",
        "SoC Start (%)", "SoC Stop (%)",
        "Charged Energy (kWh)",
        "Average Amp (A)", "Peak Amp (A)",
        "Peak Pin Temp Minus (°C)", "Peak Pin Temp Plus (°C)"
    ]
    display_df = df_day[table_cols].copy()
    display_df["Varighet"] = (display_df["clipped_end"] - display_df["clipped_start"]).dt.total_seconds() / 60
    display_df = display_df.sort_values("clipped_start").reset_index(drop=True)
    st.dataframe(display_df.style.format({
        "start time": "%H:%M", "end time": "%H:%M",
        "clipped_start": "%H:%M", "clipped_end": "%H:%M",
        "Charged Energy (kWh)": "{:.1f}", "Varighet": "{:.0f} min"
    }))
