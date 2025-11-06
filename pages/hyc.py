import os
import random
from datetime import datetime
import streamlit as st
import pandas as pd
import plotly.graph_objects as go

# --- HJELPEFUNKSJONER ---
def _read_any(file):
    name = file.name.lower() if hasattr(file, "name") else ""
    file.seek(0)
    if name.endswith(".csv"):
        return pd.read_csv(file)
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    else:
        # Fallback: prøv begge
        try:
            file.seek(0)
            return pd.read_excel(file)
        except:
            file.seek(0)
            return pd.read_csv(file)

def _concat_valid(dfs):
    valid = [df for df in dfs if not df.empty]
    if not valid:
        st.error("🚨 Ingen gyldige data i de opplastede filene.")
        st.stop()
    return pd.concat(valid, ignore_index=True)

# --- SIDEN ---
st.title("🔋 Ladeøkt-visualisering")

uploaded_files = st.file_uploader(
    "Last opp CSV eller Excel-filer", accept_multiple_files=True
)

if not uploaded_files:
    st.info("⬆️ Last opp filer for å komme i gang.")
    st.stop()

dfs = []
for file in uploaded_files:
    try:
        df = _read_any(file)
        dfs.append(df)
    except Exception as e:
        st.warning(f"⚠️ Kunne ikke lese {file.name}: {e}")

df = _concat_valid(dfs)

# ---- TYPEKONVERTERING ----
# Konverter tid → datetime (UTC), fjern tz, sikre tall i ampere-kolonner
df["start time"] = pd.to_datetime(df["start time"], errors="coerce", utc=True)
df["end time"] = pd.to_datetime(df["end time"], errors="coerce", utc=True)

# Dropp rader med ugyldige tider
df = df.dropna(subset=["start time", "end time"])

# Fjern tidssoneinfo (naive datetimes)
df["start time"] = df["start time"].dt.tz_localize(None)
df["end time"] = df["end time"].dt.tz_localize(None)

# Konverter ampere-kolonner til tall
for col in ["average amp (a)", "peak amp (a)"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")
df = df.dropna(subset=["average amp (a)", "peak amp (a)"])

# ---- VALG AV DATO ----
chosen_date = st.date_input(
    "Velg dato",
    value=df["start time"].dt.date.min(),
    min_value=df["start time"].dt.date.min(),
    max_value=df["start time"].dt.date.max(),
    format="DD.MM.YYYY",
)

# ---- OVER-MIDNATT: SPLITT I DØGNBITER ----
day_start = pd.Timestamp.combine(chosen_date, datetime.min.time())
day_end = day_start + pd.Timedelta(days=1)

# Finn økter som overlapper valgt døgn
overlap = df[(df["start time"] < day_end) & (df["end time"] > day_start)].copy()
if overlap.empty:
    st.warning(f"🚫 Ingen økter som overlapper {chosen_date:%d.%m.%Y}.")
    st.stop()

# Splitt økter ved midnatt (24-timers biter)
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

# Dummy-dato for x-akse (klokkeslett på døgnet)
def to_day_clock(ts: pd.Timestamp) -> datetime:
    return datetime(1970, 1, 1, ts.hour, ts.minute, ts.second)

df_day["start_clock"] = df_day["clipped_start"].apply(to_day_clock)
df_day["end_clock"] = df_day["clipped_end"].apply(to_day_clock)

# ---- PLOTT ----
fig = go.Figure()

for _, row in df_day.iterrows():
    y0, y1 = row["average amp (a)"], row["peak amp (a)"]
    hover = (
        f"Start: {row['clipped_start']:%H:%M} "
        f"(oppr.: {row['start time']:%d.%m %H:%M})<br>"
        f"Slutt: {row['clipped_end']:%H:%M} "
        f"(oppr.: {row['end time']:%d.%m %H:%M})<br>"
        f"SoC Start: {row['soc start (%)']}%<br>"
        f"SoC Slutt: {row['soc stop (%)']}%<br>"
        f"Avg: {y0:.1f} A<br>"
        f"Peak: {y1:.1f} A<br>"
        f"Energi: {row['charged energy (kwh)']:.1f} kWh"
    )
    fig.add_trace(go.Scatter(
        x=[row["start_clock"], row["end_clock"]],
        y=[y0, y1],
        mode="lines+markers",
        line=dict(width=8),
        name=f"Økt {row.name}",
        hoverinfo="text",
        text=hover,
    ))

START_OF_DAY = datetime(1970, 1, 1, 0, 0, 0)
END_OF_DAY = datetime(1970, 1, 1, 23, 59, 59)

fig.update_layout(
    title=f"Ladeøkter for {chosen_date:%d.%m.%Y} (Ampere vs tid på døgnet)",
    xaxis=dict(
        title="Tid på døgnet",
        type="date",
        tickformat="%H:%M",
        tickmode="linear",
        dtick=3600000,  # 1 time i ms
        range=[START_OF_DAY, END_OF_DAY],
    ),
    yaxis=dict(title="Ampere (A)"),
    hovermode="x unified",
    height=600,
)

st.plotly_chart(fig, use_container_width=True)

# ---- TABELL ----
with st.expander("Se data for valgt dato"):
    table_df = df_day.sort_values("clipped_start")[
        ["start time", "end time", "clipped_start", "clipped_end",
         "soc start (%)", "soc stop (%)",
         "average amp (a)", "peak amp (a)", "charged energy (kwh)"]
    ].reset_index(drop=True)
    st.dataframe(table_df)
