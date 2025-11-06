import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import plotly.express as px

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

# ====================== NY PLOT – ENKEL STOLPE-STIL ======================
fig = go.Figure()

# Fargekart for peak ampere (jo høyere peak, jo mørkere)
max_peak = df_day["peak amp (a)"].max()
colors = px.colors.sequential.Blues

for _, row in df_day.iterrows():
    avg = row["average amp (a)"]
    peak = row["peak amp (a)"]
    duration_min = (row["clipped_end"] - row["clipped_start"]).total_seconds() / 60

    # Farge basert på peak (normalisert)
    color_idx = int((peak / max_peak) * (len(colors) - 1)) if max_peak > 0 else 0
    color = colors[color_idx]

    # Hover-tekst
    hover = (
        f"<b>{row['clipped_start']:%H:%M} – {row['clipped_end']:%H:%M}</b> ({duration_min:.0f} min)<br>"
        f"<b>SoC:</b> {row['SoC Start (%)']}% → {row['SoC Stop (%)']}% <b>(+{row['SoC Stop (%)'] - row['SoC Start (%)']} %)</b><br>"
        f"<b>Energi:</b> {row['Charged Energy (kWh)']:.1f} kWh<br>"
        f"<b>Gj.snitt:</b> {avg:.1f} A | <b>Topp:</b> {peak:.1f} A<br>"
        f"<b>Temp:</b> Minus {row.get('Peak Pin Temp Minus (°C)', 'N/A')}°C | Plus {row.get('Peak Pin Temp Plus (°C)', 'N/A')}°C"
    )

    # Legg til stolpe (horisontal bar)
    fig.add_trace(go.Bar(
        y=[avg],
        x=[row["clipped_end"] - row["clipped_start"]],  # varighet
        orientation='h',
        base=row["start_clock"],
        name="",
        marker=dict(color=color, line=dict(width=1, color='black')),
        hoverinfo="text",
        text=hover,
        textposition="none",
        width=avg * 0.8,  # Tykkelse = gjennomsnitt (skalerer med ampere)
        offset=0,
        showlegend=False
    ))

# Dummy for x-akse (klokkeslett)
fig.update_xaxes(
    title="Tid på døgnet",
    type="date",
    tickformat="%H:%M",
    tickmode="linear",
    dtick=3600000,  # 1 time
    range=[START_OF_DAY, END_OF_DAY],
    fixedrange=True
)

fig.update_yaxes(
    title="Gjennomsnittlig Ampere (A)",
    range=[0, df_day["average amp (a)"].max() * 1.2],
    fixedrange=True
)

fig.update_layout(
    title=f"Ladeøkter {chosen_date:%d.%m.%Y} – Ampere vs Tid",
    barmode='stack',
    bargap=0.4,
    bargroupgap=0.1,
    height=600,
    hovermode="x unified",
    plot_bgcolor='white',
    margin=dict(l=60, r=20, t=80, b=60)
)

st.plotly_chart(fig, use_container_width=True)
