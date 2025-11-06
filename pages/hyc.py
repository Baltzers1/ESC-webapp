import os
import random
from datetime import datetime

@@ -34,6 +33,7 @@ def _read_any(file):
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file)
    else:
        # Fallback: prøv begge
        try:
            file.seek(0)
            return pd.read_excel(file)
@@ -84,18 +84,13 @@ def _concat_valid(dfs):
    st.stop()

# ---- TYPEKONVERTERING ----
# Konverter til datetime (UTC) og fjern tidssone
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
@@ -118,26 +113,41 @@ def _concat_valid(dfs):
    format="DD.MM.YYYY",
)

# ---- OVER-MIDNATT HÅNDTERING ----
# ---- OVER-MIDNATT: SPLITT I DØGNBITER (Alternativ C) ----
day_start = pd.Timestamp.combine(chosen_date, datetime.min.time())
day_end = day_start + pd.Timedelta(days=1)
day_end   = day_start + pd.Timedelta(days=1)

mask = (df["start time"] < day_end) & (df["end time"] > day_start)
df_day = df.loc[mask].copy()
if df_day.empty:
# Finn økter som overlapper valgt døgn
overlap = df[(df["start time"] < day_end) & (df["end time"] > day_start)].copy()
if overlap.empty:
    st.warning(f"🚫 Ingen økter som overlapper {chosen_date:%d.%m.%Y}.")
    st.stop()

# Klipp økter til dagens tidsvindu
df_day["clipped_start"] = df_day["start time"].clip(lower=day_start, upper=day_end)
df_day["clipped_end"] = df_day["end time"].clip(lower=day_start, upper=day_end)

# Konverter til dummy-dato for x-aksen
rows = []
for _, r in overlap.iterrows():
    # Klipp først til dette døgnets vindu
    s = max(r["start time"], day_start)
    e = min(r["end time"], day_end)

    # Hvis original økt strekker seg over flere døgn, del ved midnatt (24t-biter)
    # (I praksis, innenfor ett døgn blir det som regel én bit; men vi lar koden støtte flere cut points.)
    while s < e:
        next_midnight = s.normalize() + pd.Timedelta(days=1)  # neste 00:00
        chunk_end = min(next_midnight, e)
        rr = r.copy()
        rr["clipped_start"] = s
        rr["clipped_end"] = chunk_end
        rows.append(rr)
        s = chunk_end

df_day = pd.DataFrame(rows)

# Dummy-dato for x-akse
def to_day_clock(ts: pd.Timestamp) -> datetime:
    return datetime(1970, 1, 1, ts.hour, ts.minute, ts.second)

df_day["start_clock"] = df_day["clipped_start"].apply(to_day_clock)
df_day["end_clock"] = df_day["clipped_end"].apply(to_day_clock)
df_day["end_clock"]   = df_day["clipped_end"].apply(to_day_clock)

# ---- PLOTT ----
fig = go.Figure()
@@ -147,8 +157,10 @@ def to_day_clock(ts: pd.Timestamp) -> datetime:
    y0, y1 = row["average amp (a)"], row["peak amp (a)"]

    hover = (
        f"Start: {row['clipped_start']:%H:%M} (oppr.: {row['start time']:%d.%m %H:%M})<br>"
        f"Slutt: {row['clipped_end']:%H:%M} (oppr.: {row['end time']:%d.%m %H:%M})<br>"
        f"Start: {row['clipped_start']:%H:%M} "
        f"(oppr.: {row['start time']:%d.%m %H:%M})<br>"
        f"Slutt: {row['clipped_end']:%H:%M} "
        f"(oppr.: {row['end time']:%d.%m %H:%M})<br>"
        f"SoC Start: {row['soc start (%)']}%<br>"
        f"SoC Slutt: {row['soc stop (%)']}%<br>"
        f"Avg: {y0:.1f} A<br>"
@@ -168,7 +180,7 @@ def to_day_clock(ts: pd.Timestamp) -> datetime:
    ))

START_OF_DAY = datetime(1970, 1, 1, 0, 0, 0)
END_OF_DAY = datetime(1970, 1, 1, 23, 59, 59)
END_OF_DAY   = datetime(1970, 1, 1, 23, 59, 59)

fig.update_layout(
    title=f"Ladeøkter for {chosen_date:%d.%m.%Y} (Ampere vs tid på døgnet)",
@@ -177,7 +189,7 @@ def to_day_clock(ts: pd.Timestamp) -> datetime:
        type="date",
        tickformat="%H:%M",
        tickmode="linear",
        dtick=3600000,
        dtick=3600000,  # 1 time i ms
        range=[START_OF_DAY, END_OF_DAY],
    ),
    yaxis=dict(title="Ampere (A)"),
@@ -190,8 +202,8 @@ def to_day_clock(ts: pd.Timestamp) -> datetime:
# ---- TABELL ----
with st.expander("Se data for valgt dato"):
    table_df = df_day.sort_values("clipped_start")[
        ["start time", "end time", "soc start (%)", "soc stop (%)",
        ["start time", "end time", "clipped_start", "clipped_end",
         "soc start (%)", "soc stop (%)",
         "average amp (a)", "peak amp (a)", "charged energy (kwh)"]
    ].reset_index(drop=True)
    st.dataframe(table_df)
