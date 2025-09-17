import streamlit as st
import random
import plotly.express as px

# ---------- GUI: Antall visuelle ladepunkter ----------
NUM_SPOTS = 8  # For "+" og "−"-knapper i GUI

# ---------- SIMULERING: Brukerdefinert antall punkter ----------


# ---------- Beregn effekt basert på SOC ----------
def beregn_effekt(soc: int) -> int:
    premium = random.random() < 0.08
    if soc < 20:
        return random.randint(200, 300) if premium else random.randint(80, 150)
    elif soc < 50:
        return random.randint(150, 200) if premium else random.randint(60, 120)
    elif soc < 80:
        return random.randint(80, 150) if premium else random.randint(30, 80)
    else:
        return random.randint(30, 60) if premium else random.randint(5, 40)

# ---------- Monte Carlo-simulering ----------
def simulering_antall_ganger_over_grense(grense_kw: int, n: int, maks_ladepunkter: int):
    tell_over = 0
    totaler = []
    soc_gruppe_treff = {f"{i}-{i+9}": 0 for i in range(0, 100, 10)}  # init grupper

    for _ in range(n):
        antall_biler = random.randint(1, maks_ladepunkter)
        total_effekt = 0
        grupper_i_sim = set()

        for _ in range(antall_biler):
            soc = random.randint(3, 95)
            gruppe_nøkkel = f"{(soc // 10) * 10}-{(soc // 10) * 10 + 9}"
            grupper_i_sim.add(gruppe_nøkkel)

            effekt = beregn_effekt(soc)
            total_effekt += effekt

        # Tell hvilke grupper som var med i denne simuleringen
        for g in grupper_i_sim:
            soc_gruppe_treff[g] += 1

        totaler.append(total_effekt)
        if total_effekt > grense_kw:
            tell_over += 1

    sannsynlighet = tell_over / n
    return sannsynlighet, totaler, soc_gruppe_treff



# ---------- UI: EV Lading (manuell klikking) ----------
st.title("EV Charging Simulator")
st.subheader("Use the + button to add a car, − button to remove a car")

# Init bil-liste
if "biler" not in st.session_state:
    st.session_state.biler = [None] * NUM_SPOTS

# Rader for GUI-visning
row1 = st.columns(NUM_SPOTS)  # Knapper
row2 = st.columns(NUM_SPOTS)  # Emoji
row3 = st.columns(NUM_SPOTS)  # SoC
row4 = st.columns(NUM_SPOTS)  # Effekt

for i in range(NUM_SPOTS):
    bil = st.session_state.biler[i]

    with row1[i]:
        if bil:
            if st.button("➖", key=f"remove_{i}", use_container_width=True):
                st.session_state.biler[i] = None
                st.rerun()
        else:
            if st.button("➕", key=f"add_{i}", use_container_width=True):
                soc = random.randint(10, 90)
                effekt = beregn_effekt(soc)
                st.session_state.biler[i] = {"SoC": soc, "Effekt": effekt}
                st.rerun()

    with row2[i]:
        st.header("🚘" if bil else " ")

    with row3[i]:
        st.write(f"SoC: {bil['SoC']} %" if bil else "")

    with row4[i]:
        st.write(f"{bil['Effekt']} kW" if bil else "")

# ---------- Nullstill-knapp ----------
if st.button("🔄 Reset all"):
    st.session_state.biler = [None] * NUM_SPOTS
    st.rerun()

# ---------- Total Effekt fra GUI ----------
st.markdown("---")
total_kw_output = sum(bil["Effekt"] for bil in st.session_state.biler if bil)
st.header(f"Total output power: {total_kw_output} kW")

virkningsgrad = st.slider("Select efficiency (virkningsgrad)", min_value=0.80, max_value=1.00, value=0.8648, step=0.0001)
total_kw_input = int(total_kw_output / virkningsgrad)
st.header(f"Total input power: {total_kw_input} kW")

# ---------- Monte Carlo-simulering ----------
st.markdown("---")
st.title("📊 Monte Carlo Simulation of Load Demand")

max_antall_biler = st.number_input("Number of Charge Points available at the site", min_value=0, value=8, step=1)
grense = st.number_input("Net power capacity limit (kW)", value=800, step=50)
antall_simuleringer = st.number_input("Number of simulations", value=10000, step=1000)


if st.button("🏃‍♂️ Run simulation", key="mc_knapp"):
    # Kjør simulering
    sannsynlighet, totaler, soc_gruppe_treff = simulering_antall_ganger_over_grense(
        grense_kw=grense,
        n=antall_simuleringer,
        maks_ladepunkter=max_antall_biler
    )

    # Resultat
    st.success(f"Probability of exceeding {grense} kW: **{sannsynlighet:.2%}**")

    # ---------- Graf 1: Histogram over total effekt ----------
    fig1 = px.histogram(
        totaler,
        nbins=30,
        title="Distribution of Total Power Demand (kW)"
    )
    fig1.update_layout(
        xaxis_title="Total power (kW)",
        yaxis_title="Number of simulations",
        bargap=0.05
    )
    st.plotly_chart(fig1, use_container_width=True)

    # ---------- Graf 2: Søylediagram over SoC-grupper ----------
    fig2 = px.bar(
        x=list(soc_gruppe_treff.keys()),
        y=list(soc_gruppe_treff.values()),
        labels={"x": "SoC group (%)", "y": "Number of simulations"},
        title="Frequency of SoC Groups Across Simulations"
    )
    fig2.update_layout(
        xaxis_title="SoC range (%)",
        yaxis_title="Number of simulations",
        bargap=0.15
    )
    st.plotly_chart(fig2, use_container_width=True)
