# app.py
"""
Streamlit-app: modulér ladeøkt-data og plott døgnbiter for analyse.

Kjør: streamlit run app.py
Krav: pandas, plotly, streamlit
"""

import io
from typing import List, Tuple, Dict, Optional
from datetime import datetime, time
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------- HJELPEFUNKTIONER ----------

def normalize_columns(df: pd.DataFrame, lower: bool = True, strip: bool = True) -> pd.DataFrame:
    """Normaliser kolonnenavn: strip og/eller lower."""
    cols = df.columns
    if strip:
        cols = [c.strip() if isinstance(c, str) else c for c in cols]
    if lower:
        cols = [c.lower() if isinstance(c, str) else c for c in cols]
    df = df.copy()
    df.columns = cols
    return df

def parse_datetimes(df: pd.DataFrame, cols: List[str], input_tz: Optional[str] = None) -> pd.DataFrame:
    """
    Parse given datetime columns robustt.
    - If timestamps include tz info, parse with utc=True and convert to UTC.
    - Else: if input_tz provided, localize to that tz then convert to UTC.
    - Return naive UTC datetimes (tz removed).
    """
    df = df.copy()
    for c in cols:
        # Try parse (allow offsets)
        parsed = pd.to_datetime(df[c], errors="coerce", utc=True)  # will set tzinfo if offset present
        # parsed is tz-aware (UTC) if original had offset, otherwise NaT
        # If parsed has many NaT, try without utc to parse naive strings
        need_localize_mask = parsed.isna() & df[c].notna()
        if need_localize_mask.any():
            # parse without forcing utc
            parsed2 = pd.to_datetime(df.loc[need_localize_mask, c], errors="coerce")
            if input_tz:
                # localize naive datetimes to input_tz then convert to UTC
                parsed2 = parsed2.dt.tz_localize(input_tz, ambiguous="NaT", nonexistent="NaT").dt.tz_convert("UTC")
            else:
                # assume naive are already UTC
                parsed2 = parsed2.dt.tz_localize("UTC")
            parsed.loc[need_localize_mask] = parsed2
        # Now parsed should be tz-aware UTC where possible; drop tzinfo to naive UTC
        parsed = parsed.dt.tz_convert("UTC").dt.tz_localize(None)
        df[c] = parsed
    return df

def numeric_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Konverter oppgitte kolonner til numerisk med errors->NaN."""
    df = df.copy()
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def filter_valid_rows(df: pd.DataFrame, datetime_cols: List[str], numeric_cols_list: List[str]) -> pd.DataFrame:
    """Fjern rader som mangler viktige datetime eller numeric-verdier."""
    df = df.copy()
    df = df.dropna(subset=datetime_cols + numeric_cols_list)
    return df

def split_rows_over_day(df: pd.DataFrame, start_col: str, end_col: str, day: datetime.date) -> pd.DataFrame:
    """
    For hver rad som overlaps 'day' (midnight..midnight+1), split i biter som ikke går over midnatt.
    Returns DataFrame with added columns:
      - clipped_start, clipped_end (naive UTC datetimes within chosen day window)
      - start_time_orig, end_time_orig (original start/end)
    """
    # day window in UTC naive (we assume df's datetimes are naive UTC after parse_datetimes)
    day_start = pd.Timestamp.combine(day, time.min)
    day_end = day_start + pd.Timedelta(days=1)

    mask = (df[start_col] < day_end) & (df[end_col] > day_start)
    overlap = df.loc[mask].copy()
    if overlap.empty:
        return pd.DataFrame([])  # caller will handle empty

    rows = []
    for _, r in overlap.iterrows():
        s = max(r[start_col], day_start)
        e = min(r[end_col], day_end)
        # split chunks at midnight boundaries within s..e
        while s < e:
            next_midnight = (s.normalize() + pd.Timedelta(days=1))
            chunk_end = min(next_midnight, e)
            rr = r.copy()
            rr["clipped_start"] = s
            rr["clipped_end"] = chunk_end
            # keep original for hover
            rr["start_time_orig"] = r[start_col]
            rr["end_time_orig"] = r[end_col]
            rows.append(rr)
            s = chunk_end
    if not rows:
        return pd.DataFrame([])
    df_day = pd.DataFrame(rows)
    return df_day.reset_index(drop=True)

def to_day_clock(ts: pd.Timestamp) -> datetime:
    """Convert timestamp to dummy-date clock for x-axis (1970-01-01 hh:mm:ss)."""
    return datetime(1970, 1, 1, ts.hour, ts.minute, ts.second, ts.microsecond // 1000)

def build_plot(df_day: pd.DataFrame,
               avg_col: str = "average amp (a)",
               peak_col: str = "peak amp (a)",
               start_col: str = "clipped_start",
               end_col: str = "clipped_end") -> go.Figure:
    """
    Build a Plotly figure where each clipped row is drawn as a horizontal strip
    from clipped_start -> clipped_end with y between avg and peak.
    """
    fig = go.Figure()
    if df_day.empty:
        fig.update_layout(title="Ingen data å vise")
        return fig

    # Prepare dummy-clock datetimes for x-axis
    df_day = df_day.copy()
    df_day["x0"] = df_day[start_col].apply(to_day_clock)
    df_day["x1"] = df_day[end_col].apply(to_day_clock)

    # Add a shape (rectangle) per row to represent avg->peak band
    for i, row in df_day.iterrows():
        x0, x1 = row["x0"], row["x1"]
        y0, y1 = float(row[avg_col]), float(row[peak_col])
        hover = (
            f"Start (klipp): {row['clipped_start']:%H:%M} (oppr.: {row['start_time_orig']:%d.%m %H:%M})<br>"
            f"Slutt (klipp): {row['clipped_end']:%H:%M} (oppr.: {row['end_time_orig']:%d.%m %H:%M})<br>"
            f"SoC start: {row.get('soc start (%)','NA')}%<br>"
            f"SoC slutt: {row.get('soc stop (%)','NA')}%<br>"
            f"Avg: {y0:.1f} A<br>"
            f"Peak: {y1:.1f} A<br>"
        )
        # rectangle as shape
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1,
            y0=y0, y1=y1,
            line=dict(width=0),
            fillcolor="LightSkyBlue",
            opacity=0.45,
            layer="below",
        )
        # invisible scatter for hover
        fig.add_trace(go.Scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            hoverinfo="text",
            text=[hover, hover],
            showlegend=False,
            line=dict(width=0.5),
        ))

    # layout x-axis range from 00:00 to 23:59:59 on dummy date
    START_OF_DAY = datetime(1970, 1, 1, 0, 0, 0)
    END_OF_DAY = datetime(1970, 1, 1, 23, 59, 59)
    fig.update_layout(
        title="Ladeøkter (Ampere vs tid på døgnet)",
        xaxis=dict(
            title="Tid på døgnet",
            type="date",
            tickformat="%H:%M",
            tickmode="linear",
            dtick=3600000,  # 1 time i ms
            range=[START_OF_DAY, END_OF_DAY],
        ),
        yaxis=dict(title="Ampere (A)"),
        margin=dict(l=50, r=20, t=60, b=50),
        height=450,
    )
    return fig

# ---------- STREAMLIT UI ----------

st.set_page_config(page_title="Analyse: ladeøkter per døgn", layout="wide")
st.title("Analyse: del opp ladeøkter per døgn og visualiser")

st.markdown("Last opp en CSV/XLSX med kolonner: `start time`, `end time`, `average amp (a)`, `peak amp (a)` og evt. `soc start (%)`, `soc stop (%)`, `charged energy (kwh)`.")

uploaded = st.file_uploader("Velg fil (CSV eller Excel)", type=["csv", "xlsx", "xls"], accept_multiple_files=False)

with st.sidebar:
    st.header("Innstillinger")
    normalize_names = st.checkbox("Normaliser kolonnenavn (strip + lower)", value=True)
    input_tz = st.selectbox("Input tidssone (hvis timestamps uten offset)", options=["(antatt UTC)", "Europe/Oslo", "UTC", "America/New_York"], index=0)
    chosen_date = st.date_input("Velg dato for analyse (døgn)", value=pd.Timestamp.utcnow().date())
    preview_rows = st.number_input("Antall rader i tabell-forhåndsvisning", value=20, min_value=5, max_value=500)

if uploaded is not None:
    try:
        b = uploaded.getvalue()
        # enkel leser: la pandas sniffe
        if uploaded.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(b))
        else:
            # csv: la pandas auto-sniffe (sep=None via engine='python')
            df = pd.read_csv(io.BytesIO(b), sep=None, engine="python", encoding="utf-8-sig", low_memory=False)
    except Exception as e:
        st.error(f"Kunne ikke lese fil: {e}")
        st.stop()

    if normalize_names:
        df = normalize_columns(df)

    # For consistency, map expected column names if user didn't normalize
    # Define canonical names we'll use in code
    def find_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    start_col = find_col(df, ["start time", "start_time", "start"])
    end_col = find_col(df, ["end time", "end_time", "end"])
    avg_col = find_col(df, ["average amp (a)", "average_amp_a", "avg_amp", "avg_amp(a)"])
    peak_col = find_col(df, ["peak amp (a)", "peak_amp_a", "peak_amp(a)"])
    soc_start = find_col(df, ["soc start (%)", "soc_start", "soc_start (%)"])
    soc_stop = find_col(df, ["soc stop (%)", "soc_stop", "soc_stop (%)"])
    energy_col = find_col(df, ["charged energy (kwh)", "charged_energy_kwh", "charged energy"])

    missing = []
    for name, val in [("start time", start_col), ("end time", end_col), ("average amp", avg_col), ("peak amp", peak_col)]:
        if val is None:
            missing.append(name)
    if missing:
        st.error(f"Kan ikke finne nødvendige kolonner: {missing}")
        st.stop()

    # Parse datetimes robustly
    tz_option = None if input_tz == "(antatt UTC)" else input_tz
    df = parse_datetimes(df, [start_col, end_col], input_tz=tz_option)

    # numeric
    df = numeric_cols(df, [avg_col, peak_col])

    # drop invalid rows
    df = filter_valid_rows(df, [start_col, end_col], [avg_col, peak_col])

    if df.empty:
        st.warning("Ingen gyldige økter etter rensing.")
        st.stop()

    st.success(f"Lest {uploaded.name} — {len(df)} gyldige økter")

    # Split into day clips
    df_day = split_rows_over_day(df, start_col, end_col, chosen_date)
    if df_day.empty:
        st.warning(f"🚫 Ingen økter som overlapper {chosen_date:%d.%m.%Y}.")
        st.stop()

    # Ensure expected columns exist for plotting/hover
    # Rename our discovered columns to canonical keys used in plot function
    df_day = df_day.rename(columns={
        start_col: "start time",
        end_col: "end time",
        avg_col: "average amp (a)",
        peak_col: "peak amp (a)",
        soc_start: "soc start (%)" if soc_start else "soc start (%)",
        soc_stop: "soc stop (%)" if soc_stop else "soc stop (%)",
        energy_col: "charged energy (kwh)" if energy_col else "charged energy (kwh)",
    })

    # Build plot
    fig = build_plot(df_day,
                     avg_col="average amp (a)",
                     peak_col="peak amp (a)",
                     start_col="clipped_start",
                     end_col="clipped_end")

    st.plotly_chart(fig, use_container_width=True)

    # Table preview
    st.subheader("Se data for valgt dato (klippede økter)")
    table_cols = ["start time", "end time", "clipped_start", "clipped_end",
                  "soc start (%)", "soc stop (%)", "average amp (a)", "peak amp (a)", "charged energy (kwh)"]
    # filter available columns
    table_cols = [c for c in table_cols if c in df_day.columns]
    table_df = df_day.sort_values("clipped_start")[table_cols].reset_index(drop=True)
    st.dataframe(table_df.head(preview_rows), use_container_width=True)

    # Downloads
    csv_bytes = table_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Last ned klippet data (CSV)", csv_bytes, file_name=f"clipped_{chosen_date}.csv", mime="text/csv")
    try:
        buf = io.BytesIO()
        table_df.to_excel(buf, index=False)
        st.download_button("Last ned klippet data (Excel)", buf.getvalue(), file_name=f"clipped_{chosen_date}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        pass

else:
    st.info("Last opp en fil for å komme i gang.")
