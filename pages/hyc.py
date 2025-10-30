import pandas as pd
import tkinter as tk
from tkinter import filedialog, simpledialog
import plotly.graph_objects as go
from datetime import datetime, timedelta
import random
import os

# ----------------------------
# ROBUST FILLESER FUNKSJONER
# ----------------------------

def _detect_delimiter(path):
    """Prøv å gjette separator for CSV-filer."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
            for _ in range(10):
                line = f.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                sc, cc, tc = line.count(";"), line.count(","), line.count("\t")
                if max(sc, cc, tc) == 0:
                    continue
                if sc >= cc and sc >= tc: return ";"
                if cc >= sc and cc >= tc: return ","
                return "\t"
    except Exception:
        pass
    return None

def read_any_file(path: str) -> pd.DataFrame:
    """Les CSV/XLSX med automatisk separator- og encoding-håndtering."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xlsx":
        return pd.read_excel(path)

    if ext == ".csv":
        delim = _detect_delimiter(path)
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
            tries.append(dict(sep="\t", decimal=",", encoding="utf-8-sig"))
            tries.append(dict(sep="\t", decimal=".", encoding="utf-8-sig",
                              engine="python", on_bad_lines="skip"))
        # fallback
        tries.append(dict(sep=None, engine="python", encoding="utf-8-sig"))
        tries.append(dict(sep=None, engine="python", encoding="utf-8-sig",
                          on_bad_lines="skip"))

        last_err = None
        for kw in tries:
            try:
                df = pd.read_csv(path, **kw)
                if df.shape[1] >= 2:
                    return df
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Error reading {os.path.basename(path)}: {last_err}")

    raise RuntimeError(f"Ukjent filtype: {path}")

# ----------------------------
# HOVEDSCRIPT
# ----------------------------

root = tk.Tk()
root.withdraw()

filstier = filedialog.askopenfilenames(
    title="Velg én eller flere CSV eller Excel-filer",
    filetypes=[("Excel filer", "*.xlsx"), ("CSV filer", "*.csv"), ("Alle filer", "*.*")]
)

kolonner = [
    "start time", "end time", "charged energy (kwh)", "peak power (kw)",
    "average power (kw)", "soc start (%)", "soc stop (%)", "peak amp (a)",
    "average amp (a)"
]

alle_data = []

for sti in filstier:
    print(f"\n▶ Leser fil: {sti}")
    try:
        # 🎯 Bruk den robuste funksjonen her
        df = read_any_file(sti)

        # Standardiser kolonnenavn
        df.columns = (
            df.columns.str.strip()
                      .str.lower()
                      .str.replace(r"[^\x00-\x7F]+", "", regex=True)
        )

        # Sjekk manglende kolonner
        manglende = [kol for kol in kolonner if kol not in df.columns]
        if manglende:
            print(f"❌ Mangler kolonner i '{os.path.basename(sti)}': {manglende}")
            print(f"📃 Tilgjengelige kolonner: {df.columns.tolist()}")
            continue

        df = df[kolonner]
        alle_data.append(df)
        print(f"✅ Fil lastet inn med {len(df)} rader.")
    except Exception as e:
        print(f"💥 Feil ved lesing av {sti}: {e}")

if not alle_data:
    print("\n🚫 Ingen gyldige filer ble lastet inn.")
    exit()

# ... (resten av koden din som konverterer tid, filtrerer dato, og plotter)
