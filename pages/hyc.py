uploaded = st.file_uploader("Velg fil (CSV eller Excel)", type=["csv", "xlsx", "xls"], accept_multiple_files=False)

st.subheader("Analyseinnstillinger")
normalize_names = True
input_tz = None  # antatt UTC
chosen_date = st.date_input("Velg dato for analyse (døgn)", value=pd.Timestamp.utcnow().date())
preview_rows = 20

if uploaded is not None:
    try:
        b = uploaded.getvalue()
        if uploaded.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(b))
        else:
            # CSV: la pandas sniffe, fjern low_memory
            df = pd.read_csv(io.BytesIO(b), sep=None, engine="python", encoding="utf-8-sig")
    except Exception as e:
        st.error(f"Kunne ikke lese fil: {e}")
        st.stop()

    if normalize_names:
        df = normalize_columns(df)

    # Finn kolonner
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

    # Parse datetimes
    df = parse_datetimes(df, [start_col, end_col], input_tz=input_tz)
    df = numeric_cols(df, [avg_col, peak_col])
    df = filter_valid_rows(df, [start_col, end_col], [avg_col, peak_col])

    if df.empty:
        st.warning("Ingen gyldige økter etter rensing.")
        st.stop()

    st.success(f"Lest {uploaded.name} — {len(df)} gyldige økter")

    df_day = split_rows_over_day(df, start_col, end_col, chosen_date)
    if df_day.empty:
        st.warning(f"🚫 Ingen økter som overlapper {chosen_date:%d.%m.%Y}.")
        st.stop()

    # Rename til canonical names for plotting
    df_day = df_day.rename(columns={
        start_col: "start time",
        end_col: "end time",
        avg_col: "average amp (a)",
        peak_col: "peak amp (a)",
        soc_start: "soc start (%)" if soc_start else "soc start (%)",
        soc_stop: "soc stop (%)" if soc_stop else "soc stop (%)",
        energy_col: "charged energy (kwh)" if energy_col else "charged energy (kwh)",
    })

    # Plot
    fig = build_plot(df_day, avg_col="average amp (a)", peak_col="peak amp (a)",
                     start_col="clipped_start", end_col="clipped_end")
    st.plotly_chart(fig, use_container_width=True)

    # Tabell
    table_cols = ["start time", "end time", "clipped_start", "clipped_end",
                  "soc start (%)", "soc stop (%)", "average amp (a)", "peak amp (a)", "charged energy (kwh)"]
    table_cols = [c for c in table_cols if c in df_day.columns]
    table_df = df_day.sort_values("clipped_start")[table_cols].reset_index(drop=True)
    st.dataframe(table_df.head(preview_rows), use_container_width=True)

    # Nedlasting
    csv_bytes = table_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Last ned klippet data (CSV)", csv_bytes,
                       file_name=f"clipped_{chosen_date}.csv", mime="text/csv")
    try:
        buf = io.BytesIO()
        table_df.to_excel(buf, index=False)
        st.download_button("Last ned klippet data (Excel)", buf.getvalue(),
                           file_name=f"clipped_{chosen_date}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        pass

else:
    st.info("Last opp en fil for å komme i gang.")
