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

# --- PLOT 1: Økter ---
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
        y=[avg, avg, peak, peak],
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
fig.update_layout(title=f"Ladeøkter {chosen:%d.%m.%Y}", height=650, hovermode="x unified", plot_bgcolor='white', margin=dict(l=70, r=30, t=80, b=60))
st.plotly_chart(fig, use_container_width=True)

# --- PLOT 2: Samlet effekt ---
st.subheader("Samlet effekt (kW) – alle samtidige økter")

time_index = pd.date_range(START_OF_DAY, END_OF_DAY, freq='1min')
overlap_df = pd.DataFrame(index=time_index, columns=['avg_kw', 'peak_kw', 'count']).fillna(0)

for _, row in df_day.iterrows():
    mask = (time_index >= row["start_clock"]) & (time_index <= row["end_clock"])
    avg_kw = row["average amp (a)"] * 0.4
    peak_kw = row["peak amp (a)"] * 0.4
    overlap_df.loc[mask, 'avg_kw'] += avg_kw
    overlap_df.loc[mask, 'peak_kw'] += peak_kw
    overlap_df.loc[mask, 'count'] += 1

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=overlap_df.index, y=overlap_df['avg_kw'], fill='tozeroy', mode='lines', name='Gj.snitt kW', line=dict(color='lightblue'), fillcolor='rgba(100, 180, 255, 0.4)'))
fig2.add_trace(go.Scatter(x=overlap_df.index, y=overlap_df['peak_kw'], mode='lines', name='Topp kW', line=dict(color='darkblue', width=2)))
fig2.add_trace(go.Scatter(x=overlap_df.index, y=overlap_df['count'], mode='lines', name='Antall økter', yaxis='y2', line=dict(color='gray', dash='dot')))

fig2.update_layout(
    title=f"Samlet effekt {chosen:%d.%m.%Y}",
    xaxis=dict(title="Tid på døgnet", tickformat="%H:%M"),
    yaxis=dict(title="Effekt (kW)", range=[0, overlap_df['peak_kw'].max() * 1.1]),
    yaxis2=dict(title="Antall økter", overlaying='y', side='right', range=[0, overlap_df['count'].max() * 1.2]),
    hovermode="x unified", height=500, legend=dict(x=0, y=1.1, orientation='h')
)
st.plotly_chart(fig2, use_container_width=True)

# --- PLOT 3: Heatmap per dag (VISER ALTID NOE) ---
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

    # VIS HEATMAP (selv med 1 dag)
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
        height=300,
        margin=dict(l=50, r=20, t=60, b=50),
        xaxis=dict(tickangle=45)
    )

    st.plotly_chart(fig3, use_container_width=True)
