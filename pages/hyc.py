import os
import random
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="Ladeøkter – Ampere vs Tid", layout="wide")

st.title("📊 Ladeøkter (Ampere vs tid på døgnet)")
st.caption("Last opp én eller flere CSV/XLSX-filer og velg dato for å plotte.")

# --- SIDEBAR ---
with st.sidebar:
    st.header("Innstillinger")
    files = st.file_uploader(
        "Velg én eller flere filer",
        type=["csv", "xlsx", "xls"],
        accept_multiple_files=True,
    )

# Relevante kolonner
KOLONNER = [
    "start time", "end time", "charged energy (kwh)", "peak power (kw)",
    "average power (kw)", "soc start (%)", "soc stop (%)", "peak amp (a)",
    "average amp (a)"
]

def _read_any(file):
    name = file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    else:
        try:
            file.seek(0)
            return pd.read_excel(file)
        except Exception:
            file.seek(0)
            return pd.read_csv(file)

def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.str.strip()
                  .str.lower()
                  .str.replace(r"[^\x00-\x7F]+", "", regex=True)
    )
    return df

def _concat_valid(dfs):
    valids = []
    msgs = []
    for i, df in enumerate(dfs, start=1):
        df = _clean_columns(df)
        missing = [k for k in KOLONNER if k not in df.columns]
        if missing:
            msgs.append(f"❌ Fil {i}: mangler kolonner: {missing}")
            continue
        valids.append(df[KOLONNER].copy())
        msgs.append(f"✅ Fil {i}: {len(df)} rader OK")
    return (pd.concat(valids, ignore_index=True) if valids else None), msgs

if not files:
    st.info("👆 Last opp CSV/XLSX-filer for å komme i gang.")
    st.stop()

raw_dfs = []
for f in files:
    try:
        raw_dfs.append(_read_any(f))
    except Exception as e:
        st.error(f"💥 Feil ved lesing av **{f.name}**: {e}")

df, status_msgs = _concat_valid(raw_dfs)
with st.expander("Importlogg"):
    for m in status_msgs:
        st.write(m)

if df is None or df.empty:
    st.error("🚫 Ingen gyldige filer/kolonner ble funnet.")
    st.stop()

# ---- TYPEKONVERTERING ----
# Konverter til datetime (UTC) og fjern tidssone
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
if df.empty:
    st.error("🚫 Alle rader hadde mangler etter rensing.")
    st.stop()

# Tilgjengelige datoer
available_dates = sorted(pd.Series(df["start time"].dt.date.unique()).dropna())
if not available_dates:
    st.error("🚫 Fant ingen datoer i dataene.")
    st.stop()

default_date = random.choice(available_dates)
chosen_date = st.date_input(
    "Velg dato (fra tilgjengelige):",
    value=default_date,
    min_value=available_dates[0],
    max_value=available_dates[-1],
    format="DD.MM.YYYY",
)

# ---- OVER-MIDNATT HÅNDTERING ----
day_start = pd.Timestamp.combine(chosen_date, datetime.min.time())
day_end = day_start + pd.Timedelta(days=1)

mask = (df["start time"] < day_end) & (df["end time"] > day_start)
df_day = df.loc[mask].copy()
if df_day.empty:
    st.warning(f"🚫 Ingen økter som overlapper {chosen_date:%d.%m.%Y}.")
    st.stop()

# Klipp økter til dagens tidsvindu
df_day["clipped_start"] = df_day["start time"].clip(lower=day_start, upper=day_end)
df_day["clipped_end"] = df_day["end time"].clip(lower=day_start, upper=day_end)

# Konverter til dummy-dato for x-aksen
def to_day_clock(ts: pd.Timestamp) -> datetime:
    return datetime(1970, 1, 1, ts.hour, ts.minute, ts.second)

df_day["start_clock"] = df_day["clipped_start"].apply(to_day_clock)
df_day["end_clock"] = df_day["clipped_end"].apply(to_day_clock)

# ---- PLOTT ----
fig = go.Figure()

for _, row in df_day.iterrows():
    x0, x1 = row["start_clock"], row["end_clock"]
    y0, y1 = row["average amp (a)"], row["peak amp (a)"]

    hover = (
        f"Start: {row['clipped_start']:%H:%M} (oppr.: {row['start time']:%d.%m %H:%M})<br>"
        f"Slutt: {row['clipped_end']:%H:%M} (oppr.: {row['end time']:%d.%m %H:%M})<br>"
        f"SoC Start: {row['soc start (%)']}%<br>"
        f"SoC Slutt: {row['soc stop (%)']}%<br>"
        f"Avg: {y0:.1f} A<br>"
        f"Peak: {y1:.1f} A"
    )

    fig.add_trace(go.Scatter(
        x=[x0, x1, x1, x0, x0],
        y=[y0, y0, y1, y1, y0],
        fill="toself",
        mode="lines",
        line=dict(width=0),
        fillcolor="rgba(100, 149, 237, 0.5)",
        hoverinfo="text",
        text=hover,
        showlegend=False,
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
        dtick=3600000,
        range=[START_OF_DAY, END_OF_DAY],
    ),
    yaxis=dict(title="Ampere (A)"),
    height=650,
    margin=dict(l=40, r=20, t=60, b=40),
)

st.plotly_chart(fig, use_container_width=True)

# ---- TABELL ----
with st.expander("Se data for valgt dato"):
    st.dataframe(
        df_day[
            ["start time", "end time", "soc start (%)", "soc stop (%)",
             "average amp (a)", "peak amp (a)", "charged energy (kwh)"]
        ].sort_values("clipped_start").reset_index(drop=True)
    )
