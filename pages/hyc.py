import io
import os
import random
from datetime import datetime, date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="HYC – døgnplot", layout="wide")

st.title("HYC: Ladeøkter – døgnvis rektangelplot (Avg→Peak Amp)")

# ----------------------------
# Robust innlesning (CSV/XLSX)
# ----------------------------
def _detect_delimiter_from_sample(sample: str):
    sample = sample.strip()
    if not sample:
        return None
    sc, cc, tc = sample.count(";"), sample.count(","), sample.count("\t")
    if max(sc, cc, tc) == 0:
        return None
    if sc >= cc and sc >= tc:
        return ";"
    if cc >= sc and cc >= tc:
        return ","
    return "\t"

def read_any_uploaded(file) -> pd.DataFrame:
    name = file.name.lower()
    buffer = file.read()
    bio = io.BytesIO(buffer)

    if name.endswith(".xlsx"):
        bio.seek(0)
        return pd.read_excel(bio)

    if name.endswith(".csv"):
        # Ta en liten tekstprøve for å gjette delimiter
        head_sample = buffer[:4096].decode("utf-8-sig", errors="ignore")
        delim = _detect_delimiter_from_sample(head_sample)

        # Forsøk forskjellige oppsett
        tries = []
        if delim == ";":
            tries.append(dict(sep=";", decimal=",", encoding="utf-8-sig"))
            tries.append(dict(sep=";", decimal=",", encoding="utf-8-sig",
                              engine="python", on_bad_lines="skip"))
        elif delim == ",":
            tries.append(dict(sep=",", decimal=".", encoding="utf-8-sig"))
            tries.append(dict(sep=",", decimal=".", encoding="utf-8-sig",
                              engine="python", on_bad_lines="skip"))
        elif delim == "\t":
            # tab med usikker desimal—prøv både komma og punktum
            tries.append(dict(sep="\t", decimal=",", encoding="utf-8-sig"))
            tries.append(dict(sep="\t", decimal=".", encoding="utf-8-sig"))
            tries.append(dict(sep="\t", encoding="utf-8-sig",
                              engine="python", on_bad_lines="skip"))
        # generelt fallback
        tries.append(dict(sep=None, engine="python", encoding="utf-8-sig"))
        tries.append(dict(sep=None, engine="python", encoding="utf-8-sig",
                          on_bad_lines="skip"))

        last_err = None
        for kw in tries:
            try:
                bio.seek(0)
                df = pd.read_csv(bio, **kw)
                if df.shape[1] >= 2:
                    return df
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Error reading {file.name}: {last_err}")

    raise RuntimeError(f"Ukjent filtype: {file.name}")

# ----------------------------
# Filopplasting
# ----------------------------
uploaded = st.sidebar.file_uploader(
    "Last opp én eller flere filer (.xlsx / .csv)",
    type=["xlsx", "csv"],
    accept_multiple_files=True
)

# Kolonner vi trenger (normalisert)
required_cols = [
    "start time", "end time", "charged energy (kwh)", "peak power (kw)",
    "average power (kw)", "soc start (%)", "soc stop (%)",
    "peak amp (a)", "average amp (a)",
]

if not uploaded:
    st.info("Last opp filer i sidepanelet for å starte.")
    st.stop()

# Les og slå sammen
frames = []
bad_files = []
for up in uploaded:
    try:
        df = read_any_uploaded(up)
        # normaliser kolonnenavn
        df.columns = (df.columns
                      .str.strip()
                      .str.lower()
                      .str.replace(r"[^\x00-\x7F]+", "", regex=True))
        # enkel alias-mapping (valgfritt – utvid hvis du møter variasjoner)
        aliases = {
            "avg amp (a)": "average amp (a)",
            "avg current (a)": "average amp (a)",
            "max amp (a)": "peak amp (a)",
            "max current (a)": "peak amp (a)",
            "avg power (kw)": "average power (kw)",
            "max power (kw)": "peak power (kw)",
        }
        df = df.rename(columns={c: aliases.get(c, c) for c in df.columns})

        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            bad_files.append(f"❌ {up.name} (mangler: {missing})")
            continue

        frames.append(df[required_cols])
    except Exception as e:
        bad_files.append(f"💥 {up.name}: {e}")

if bad_files:
    with st.expander("Filer som ble hoppet over / feilmeldinger"):
        for line in bad_files:
            st.code(line)

if not frames:
    st.error("No valid files/columns found.")
    st.stop()

df = pd.concat(frames, ignore_index=True)

# ----------------------------
# Datavask
# ----------------------------
df["start time"] = pd.to_datetime(df["start time"], errors="coerce")
df["end time"]   = pd.to_datetime(df["end time"],   errors="coerce")
for col in ["average amp (a)", "peak amp (a)"]:
    df[col] = pd.to_numeric(df[col], errors="coerce")

df = df.dropna(subset=["start time", "end time", "average amp (a)", "peak amp (a)"])
if df.empty:
    st.error("Ingen gyldige rader etter datavask.")
    st.stop()

# ----------------------------
# Dato-valg
# ----------------------------
min_ui = date(2025, 1, 1)
max_ui = date(2025, 6, 30)

st.sidebar.subheader("Dato")
user_date = st.sidebar.date_input(
    "Velg dato (01.01.2025–30.06.2025). La stå tom for tilfeldig.",
    value=None, min_value=min_ui, max_value=max_ui
)

if user_date is None:
    # velg tilfeldig dato blant tilgjengelige innen intervallet
    candidates = df[(df["start time"].dt.date >= min_ui) &
                    (df["start time"].dt.date <= max_ui)]["start time"].dt.date.unique()
    if len(candidates) == 0:
        st.warning("Ingen data i perioden 01.01.2025–30.06.2025.")
        st.stop()
    chosen_date = random.choice(sorted(candidates))
    st.sidebar.info(f"Ingen dato valgt – bruker tilfeldig: {chosen_date.strftime('%d.%m.%Y')}")
else:
    chosen_date = user_date

day_df = df[df["start time"].dt.date == chosen_date]
if day_df.empty:
    st.warning(f"Ingen ladeøkter for {chosen_date.strftime('%d.%m.%Y')}.")
    st.stop()

# ----------------------------
# Plot: rektangler per økt (Avg→Peak Amp)
# Håndter økter som krysser midnatt
# ----------------------------
BASE = datetime(1970, 1, 1)
NEXT = BASE + timedelta(days=1)

def to_clock(ts: pd.Timestamp) -> datetime:
    return BASE.replace(hour=ts.hour, minute=ts.minute, second=ts.second)

day_df = day_df.copy()
day_df["start_clock"] = day_df["start time"].apply(to_clock)
day_df["end_clock"]   = day_df["end time"].apply(to_clock)

fig = go.Figure()

def add_rect(x0, x1, y0, y1, hover):
    fig.add_trace(go.Scatter(
        x=[x0, x1, x1, x0, x0],
        y=[y0, y0, y1, y1, y0],
        fill="toself", mode="lines",
        line=dict(width=0),
        fillcolor="rgba(100,149,237,0.5)",
        hoverinfo="text", text=hover,
        showlegend=False
    ))

for _, row in day_df.iterrows():
    x0 = row["start_clock"]
    x1 = row["end_clock"]
    y0 = row["average amp (a)"]
    y1 = row["peak amp (a)"]
    if pd.isna(y0) or pd.isna(y1):
        continue

    hover = (
        f"Start: {row['start time'].strftime('%H:%M')}<br>"
        f"Slutt: {row['end time'].strftime('%H:%M')}<br>"
        f"SoC Start: {row['soc start (%)']}%<br>"
        f"SoC Slutt: {row['soc stop (%)']}%<br>"
        f"Avg Amp: {y0:.1f} A<br>"
        f"Peak Amp: {y1:.1f} A"
    )

    if x1 >= x0:
        add_rect(x0, x1, y0, y1, hover)
    else:
        # krysser midnatt → splitt
        add_rect(x0, NEXT, y0, y1, hover)  # start → 24:00
        add_rect(BASE, x1, y0, y1, hover)  # 00:00 → slutt

fig.update_layout(
    title=f"Ladeøkter – {chosen_date.strftime('%d.%m.%Y')} (Avg→Peak Amp per økt)",
    xaxis=dict(
        title="Tid på døgnet",
        type="date",
        tickformat="%H:%M",
        range=[BASE, NEXT],
        dtick=3600000,  # 1 time
        tickmode="linear"
    ),
    yaxis=dict(title="Ampere (A)"),
    height=650,
    margin=dict(l=40, r=20, t=60, b=40)
)

st.plotly_chart(fig, use_container_width=True)

# Liten oppsummering
st.caption(f"Økter vist: {len(day_df)}  •  Filer lastet: {len(uploaded)}")
