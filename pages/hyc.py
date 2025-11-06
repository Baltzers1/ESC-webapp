import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import calendar

# --- KONFIG ---
st.set_page_config(page_title="Hurtiglader", layout="wide")
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
    st.info("Last opp filer")
    st.stop()

df = load_data(uploaded)
df.columns = df.columns.str.strip()

# --- Sjekk kolonner ---
required = ["Start Time", "End Time", "Average Amp (A)", "Peak Amp (A)", "Charged Energy (kWh)", "SoC Start (%)", "SoC Stop (%)"]
missing = set(required) - set(df.columns)
if missing:
    st.error(f"Manglende kolonner: {', '.join(missing)}")
    st.stop()

# --- Konverter tid og tall ---
df["start time"] = pd.to_datetime(df["Start Time"], format="%m/%d/%Y %H:%M:%S %z", utc=True).dt.tz_localize(None)
df["end time"] = pd.to_datetime(df["End Time"], format="%m/%d/%Y %H:%M:%S %z", utc=True).dt.tz_localize(None)
df["average amp (a)"] = pd.to_numeric(df["Average Amp (A)"], errors="coerce")
df["peak amp (a)"] = pd.to_numeric(df["Peak Amp (A)"], errors="coerce")
df = df.dropna(subset=["start time", "end time", "average amp (a)", "peak amp (a)"])

# --- Beregn maks per dag ---
daily_data = []
unique_dates = sorted(df["start time"].dt.date.unique())

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
        avg_kw = row["average amp (a)"] * 0.4  # Faktor for kW
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

# --- Kalender Heatmap ---
st.subheader("Kalenderbasert heatmap – Maks effekt per dag")

# Lag komplett datoperiode
start_date = daily_df['date'].min()
end_date = daily_df['date'].max()
all_dates = pd.date_range(start_date, end_date)

# Lag matriser for z (peak) og customdata (avg)
weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
z_matrix = [[None for _ in range(len(all_dates))] for _ in range(7)]
custom_matrix = [[None for _ in range(len(all_dates))] for _ in range(7)]

daily_map = {row['date']: row for _, row in daily_df.iterrows()}

for col_idx, d in enumerate(all_dates):
    wd = d.weekday()  # 0=Mon
    if d.date() in daily_map:
        z_matrix[wd][col_idx] = daily_map[d.date()]['max_peak_kw']
        custom_matrix[wd][col_idx] = daily_map[d.date()]['max_avg_kw']

# Plot heatmap
fig = go.Figure(data=go.Heatmap(
    z=z_matrix,
    x=[d.strftime('%d.%m') for d in all_dates],
    y=weekdays,
    colorscale='Greens',
    zmin=0,
    hoverongaps=False,
    customdata=custom_matrix,
    hovertemplate="<b>%{x}</b><br>%{y}<br>Peak kW: %{z:.1f}<br>Avg kW: %{customdata:.1f}<extra></extra>"
))

fig.update_layout(
    title="Makslast per dag (kalender)",
    xaxis_title="Dato",
    yaxis_title="Ukedag",
    height=600,
    margin=dict(l=50, r=20, t=80, b=50),
    xaxis=dict(tickangle=45)
)

st.plotly_chart(fig, use_container_width=True)
