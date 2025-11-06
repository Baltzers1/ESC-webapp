import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime

# --- KONFIG ---
st.set_page_config(page_title="Hurtiglader – Kalender Heatmap", layout="wide")
st.title("Hurtiglader – Kalender Heatmap")

# --- LAST OPP DATA ---
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
    st.info("Last opp filer for å fortsette")
    st.stop()

df = load_data(uploaded)
df.columns = df.columns.str.strip()

# --- Sjekk nødvendige kolonner ---
required = ["Start Time", "End Time", "Peak Power (kW)", "Average Power (kW)"]
missing = set(required) - set(df.columns)
if missing:
    st.error(f"Manglende kolonner: {', '.join(missing)}")
    st.stop()

# --- Konverter tid ---
df["start time"] = pd.to_datetime(df["Start Time"], utc=True).dt.tz_localize(None)
df["end time"] = pd.to_datetime(df["End Time"], utc=True).dt.tz_localize(None)

# --- Beregn maks per dag ---
daily_df = (
    df.groupby(df["start time"].dt.date)
    .agg(
        max_peak_kw=("Peak Power (kW)", "max"),
        max_avg_kw=("Average Power (kW)", "max")
    )
    .reset_index()
    .rename(columns={"start time": "date"})
)

if daily_df.empty:
    st.info("Ingen data tilgjengelig for heatmap.")
    st.stop()

# --- Kalender Heatmap ---
st.subheader("Kalenderbasert heatmap – Maks effekt per dag")

start_date = pd.Timestamp(daily_df['date'].min())
end_date = pd.Timestamp(daily_df['date'].max())
all_dates = pd.date_range(start_date, end_date)

# Lag matriser for z og customdata
weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
num_weeks = ((end_date - start_date).days // 7) + 2
z_matrix = [[None for _ in range(num_weeks)] for _ in range(7)]
custom_matrix = [[None for _ in range(num_weeks)] for _ in range(7)]

daily_map = {row['date']: row for _, row in daily_df.iterrows()}

for d in all_dates:
    week_idx = (d - start_date).days // 7
    wd = d.weekday()
    if d.date() in daily_map:
        z_matrix[wd][week_idx] = daily_map[d.date()]['max_peak_kw']
        custom_matrix[wd][week_idx] = daily_map[d.date()]['max_avg_kw']

weeks = [f"W{i+1}" for i in range(num_weeks)]

fig = go.Figure(data=go.Heatmap(
    z=z_matrix,
    x=weeks,
    y=weekdays,
    colorscale='Greens',
    zmin=0,
    hoverongaps=False,
    customdata=custom_matrix,
    hovertemplate="<b>%{y}</b> %{x}<br>Peak kW: %{z:.1f}<br>Avg kW: %{customdata:.1f}<extra></extra>"
))

fig.update_layout(
    title="Makslast per dag (kalender)",
    xaxis_title="Uker",
    yaxis_title="Ukedag",
    height=700,
    margin=dict(l=50, r=20, t=80, b=50)
)

st.plotly_chart(fig, use_container_width=True)
