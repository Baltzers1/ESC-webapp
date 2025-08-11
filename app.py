# webapp 

import streamlit as st
import io


# Page Setup
home_page = st.Page(
    page="pages/home.py",
    title="Home page",
    icon=":material/home:",
    default=True,
)
calc_page = st.Page(
    page="pages/amps_kva.py",
    title="Amps to kVA Calculator",
    icon=":material/calculate:",
)
kemp_page = st.Page(
    page="pages/plotting_utilization.py",
    title="Kempower Peak kW",
     icon=":material/bolt:",
)
batt_page = st.Page(
    page="pages/battery_heatmap.py",
    title="Battery Sizing Heatmap",
    icon=":material/battery_android_question:",
)
sim_page = st.Page(
    page="pages/simulator.py",
    title="EV Charging Simulator",
    icon=":material/electric_car:",
)
hyc_page = st.Page(
    page="pages/hyc.py",
    title="Alpitronic Data Plotting",
    icon=":material/monitoring", 
)

#Sidebar def
pg = st.navigation(pages=[home_page,kemp_page,hyc_page,batt_page,calc_page,sim_page])
#Run sidebar
pg.run()
