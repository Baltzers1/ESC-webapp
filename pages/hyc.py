# ====================== FEILSIKKER PLOT – STOLPER MED FILL ======================
fig = go.Figure()

max_peak = df_day["peak amp (a)"].max()
colors = px.colors.sequential.Blues_r  # Mørk = høy peak

for _, row in df_day.iterrows():
    avg = row["average amp (a)"]
    peak = row["peak amp (a)"]
    duration_min = (row["clipped_end"] - row["clipped_start"]).total_seconds() / 60

    # Farge basert på peak
    color_idx = int((peak / max_peak) * (len(colors) - 1)) if max_peak > 0 else 0
    color = colors[color_idx]

    # Hover
    hover = (
        f"<b>{row['clipped_start']:%H:%M} – {row['clipped_end']:%H:%M}</b> ({duration_min:.0f} min)<br>"
        f"<b>SoC:</b> {row['SoC Start (%)']}% → {row['SoC Stop (%)']}% (+{row['SoC Stop (%)'] - row['SoC Start (%)']}%)<br>"
        f"<b>Energi:</b> {row['Charged Energy (kWh)']:.1f} kWh<br>"
        f"<b>Gj.snitt:</b> {avg:.1f} A | <b>Topp:</b> {peak:.1f} A<br>"
        f"<b>Temp:</b> Minus {row.get('Peak Pin Temp Minus (°C)', 'N/A')}°C | Plus {row.get('Peak Pin Temp Plus (°C)', 'N/A')}°C"
    )

    # STOLPE MED FILL
    fig.add_trace(go.Scatter(
        x=[row["start_clock"], row["end_clock"], row["end_clock"], row["start_clock"]],
        y=[0, 0, avg, avg],
        fill='toself',
        mode='none',
        fillcolor=color,
        line=dict(width=1, color='black'),
        hoverinfo='text',
        text=hover,
        name="",
        showlegend=False
    ))

# ====================== LAYOUT ======================
START_OF_DAY = datetime(1970, 1, 1, 0, 0, 0)
END_OF_DAY = datetime(1970, 1, 1, 23, 59, 59)

fig.update_xaxes(
    title="Tid på døgnet",
    type="date",
    tickformat="%H:%M",
    tickmode="linear",
    dtick=3600000,
    range=[START_OF_DAY, END_OF_DAY],
)

fig.update_yaxes(
    title="Gjennomsnittlig Ampere (A)",
    range=[0, df_day["average amp (a)"].max() * 1.2],
)

fig.update_layout(
    title=f"Ladeøkter {chosen_date:%d.%m.%Y} – Ampere vs Tid på Døgnet",
    height=650,
    hovermode="x unified",
    plot_bgcolor='white',
    margin=dict(l=70, r=30, t=80, b=60),
    font=dict(size=12)
)

st.plotly_chart(fig, use_container_width=True)
