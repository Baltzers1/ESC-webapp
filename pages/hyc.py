# README: This is a Streamlit app for uploading, merging, and analyzing charging session data.
# Required packages: pandas, streamlit
# Run with: streamlit run app.py
#
# Test scenario:
# - File1: CSV with semicolon separator and comma decimal (e.g., "1;2,5")
# - File2: CSV with comma separator and dot decimal (e.g., "1,2.5")
# Expected: App detects delimiters, previews data. For outer concat, all columns preserved with NaNs where missing. For inner, only common columns. Merged DF shows combined rows, optionally with __source_file column.

import pandas as pd
import streamlit as st
from io import BytesIO
import csv
import os
from typing import List, Optional, Dict
import numpy as np

@st.cache_data
def _detect_delimiter_from_bytes(file_bytes: bytes) -> str:
    """Detect delimiter using csv.Sniffer on a sample."""
    sample = file_bytes[:32768].decode(errors='ignore')  # 32KB sample
    try:
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample)
        return dialect.delimiter
    except:
        return ','

def _make_csv_trylist(delimiter: Optional[str] = None) -> List[Dict]:
    """Create prioritized list of read_csv configurations."""
    configs = [
        {'sep': ';', 'decimal': ','},
        {'sep': ',', 'decimal': '.'},
        {'sep': '\t', 'decimal': '.'},
        {'sep': None, 'engine': 'python'},
    ]
    if delimiter:
        configs = [{'sep': delimiter, 'decimal': ','}] + configs
    for config in configs:
        config['low_memory'] = False
        if 'engine' not in config:
            config['engine'] = 'python'
            config['on_bad_lines'] = 'skip'
    return configs

@st.cache_data
def read_any_file_from_bytes(file_name: str, file_bytes: bytes) -> Optional[pd.DataFrame]:
    """Read file (CSV/TXT/XLSX/XLS) with robust parsing."""
    ext = os.path.splitext(file_name)[1].lower()
    try:
        if ext in ['.xlsx', '.xls']:
            return pd.read_excel(BytesIO(file_bytes))
        elif ext in ['.csv', '.txt']:
            delimiter = _detect_delimiter_from_bytes(file_bytes)
            configs = _make_csv_trylist(delimiter)
            for config in configs:
                try:
                    df = pd.read_csv(BytesIO(file_bytes), **config)
                    if not df.empty:
                        return df
                except Exception:
                    continue
            raise ValueError("Failed to parse CSV/TXT")
        else:
            raise ValueError("Unsupported file type")
    except Exception as e:
        st.error(f"Error reading {file_name}: {str(e)}")
        return None

def concat_dataframes(dfs: List[pd.DataFrame], how: str = 'outer', add_source: bool = False, sources: List[str] = None, normalize_cols: bool = False) -> pd.DataFrame:
    """Concatenate DataFrames with options."""
    if normalize_cols:
        for df in dfs:
            df.columns = df.columns.str.strip().str.lower()
    if add_source and sources:
        for df, src in zip(dfs, sources):
            df['__source_file'] = src
    return pd.concat(dfs, axis=0, join=how, ignore_index=True)

def analyze_charging_data(df: pd.DataFrame) -> Dict:
    """Perform comprehensive analysis on charging session data."""
    analysis = {}

    # Parse datetime
    df['Start Time'] = pd.to_datetime(df['Start Time'], errors='coerce', utc=True)
    df['End Time'] = pd.to_datetime(df['End Time'], errors='coerce', utc=True)
    df['Duration'] = (df['End Time'] - df['Start Time']).dt.total_seconds() / 60  # minutes

    # Basic stats
    analysis['total_sessions'] = len(df)
    analysis['total_energy_kwh'] = df['Charged Energy (kWh)'].sum()
    analysis['avg_energy_kwh'] = df['Charged Energy (kWh)'].mean()
    analysis['avg_duration_min'] = df['Duration'].mean()
    analysis['avg_power_kw'] = df['Average Power (kW)'].mean()

    # Charger utilization
    charger_counts = df['Charger Serial Number'].value_counts()
    analysis['unique_chargers'] = len(charger_counts)
    analysis['sessions_per_charger'] = charger_counts.to_dict()

    # Time-based
    df['date'] = df['Start Time'].dt.date
    daily_sessions = df['date'].value_counts().sort_index()
    analysis['daily_sessions'] = daily_sessions.to_dict()

    # Connector types
    analysis['connector_distribution'] = df['Connector'].value_counts().to_dict()

    # Error analysis
    error_cols = ['Stop Reason', 'OCPP Errorcode', 'HYC Errorcode']
    analysis['error_summary'] = {}
    for col in error_cols:
        if col in df.columns:
            analysis['error_summary'][col] = df[col].value_counts().head(10).to_dict()

    # Car models
    analysis['top_cars'] = df['Car'].value_counts().head(10).to_dict()

    return analysis, df

def plot_analysis(analysis: Dict, df: pd.DataFrame):
    """Display plots for analysis."""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Daily Charging Sessions")
        if 'daily_sessions' in analysis:
            dates = list(analysis['daily_sessions'].keys())
            counts = list(analysis['daily_sessions'].values())
            chart_df = pd.DataFrame({'Date': dates, 'Sessions': counts})
            st.line_chart(chart_df.set_index('Date'))

    with col2:
        st.subheader("Energy per Session (kWh)")
        hist_data = df['Charged Energy (kWh)'].dropna()
        if len(hist_data) > 0:
            st.bar_chart(pd.cut(hist_data, bins=30).value_counts().sort_index())

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Connector Type Distribution")
        if 'connector_distribution' in analysis:
            st.bar_chart(pd.Series(analysis['connector_distribution']))

    with col4:
        st.subheader("Top 10 Car Models")
        if 'top_cars' in analysis:
            st.bar_chart(pd.Series(analysis['top_cars']))

    # Error heat map
    if 'error_summary' in analysis and analysis['error_summary']:
        st.subheader("Top Stop Reasons")
        stop_reasons = analysis['error_summary'].get('Stop Reason', {})
        if stop_reasons:
            st.bar_chart(pd.Series(stop_reasons))

def main():
    st.set_page_config(page_title="Charging Data Analyzer", layout="wide")
    st.title("EV Charging Session Analyzer")

    # All controls in main area
    st.markdown("### Configuration")
    col1, col2 = st.columns(2)
    with col1:
        how = st.selectbox("Merge Type", ['outer', 'inner'], index=0)
        add_source = st.checkbox("Add __source_file Column", value=True)
        normalize_cols = st.checkbox("Normalize Column Names (strip & lower)", value=True)
    with col2:
        preview_rows = st.number_input("Preview Rows", min_value=5, max_value=100, value=10, step=5)

    st.markdown("### Filters (applied after merge)")
    col3, col4 = st.columns(2)
    with col3:
        min_energy = st.slider("Min Energy (kWh)", 0.0, 100.0, 0.0, 0.5)
        max_energy = st.slider("Max Energy (kWh)", 0.0, 200.0, 200.0, 0.5)
    with col4:
        st.write("Charger filter available after first merge")

    # File uploader
    st.markdown("### Upload Files")
    uploaded_files = st.file_uploader(
        "Upload Charging Session Files (CSV, TXT, XLSX, XLS)",
        accept_multiple_files=True,
        type=['csv', 'txt', 'xlsx', 'xls'],
        help="Drag and drop multiple files"
    )

    if not uploaded_files:
        st.info("Upload one or more files to start analysis.")
        st.stop()

    # Process files
    successful_dfs = []
    successful_names = []
    failed_names = []

    st.markdown("### File Previews")
    tabs = st.tabs([f.name for f in uploaded_files])

    for i, file in enumerate(uploaded_files):
        with tabs[i]:
            st.subheader(f"File: {file.name}")
            file_bytes = file.read()
            df = read_any_file_from_bytes(file.name, file_bytes)
            if df is not None:
                st.success(f"Loaded {len(df)} rows")
                st.dataframe(df.head(5), use_container_width=True)

                # Single file download
                csv_bytes = df.to_csv(index=False, encoding='utf-8-sig').encode()
                st.download_button(
                    f"Download {file.name}",
                    csv_bytes,
                    file_name=file.name,
                    mime='text/csv',
                    use_container_width=True
                )

                successful_dfs.append(df)
                successful_names.append(file.name)
            else:
                st.error(f"Failed to read {file.name}")
                failed_names.append(file.name)

    if not successful_dfs:
        st.error("No files were successfully loaded.")
        st.stop()

    # Merge
    st.markdown("### Merge & Analyze")
    if st.button("Merge & Analyze All Files", type="primary", use_container_width=True):
        with st.spinner("Merging and analyzing..."):
            merged_df = concat_dataframes(
                successful_dfs,
                how=how,
                add_source=add_source,
                sources=successful_names,
                normalize_cols=normalize_cols
            )

            # Apply energy filters
            filtered_df = merged_df.copy()
            if min_energy > 0:
                filtered_df = filtered_df[filtered_df['Charged Energy (kWh)'] >= min_energy]
            if max_energy < 200:
                filtered_df = filtered_df[filtered_df['Charged Energy (kWh)'] <= max_energy]

            st.session_state.merged_df = filtered_df
            st.session_state.charger_options = sorted(filtered_df['Charger Serial Number'].unique())

    if 'merged_df' in st.session_state:
        df = st.session_state.merged_df

        # Charger filter (now available)
        if 'charger_options' in st.session_state:
            selected_chargers = st.multiselect(
                "Filter by Charger Serial Number",
                options=st.session_state.charger_options,
                default=[]
            )
            if selected_chargers:
                df = df[df['Charger Serial Number'].isin(selected_chargers)]

        st.markdown(f"### Analysis Results ({len(df)} sessions)")

        # Key metrics
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Energy", f"{df['Charged Energy (kWh)'].sum():.1f} kWh")
        with col2:
            st.metric("Avg Energy", f"{df['Charged Energy (kWh)'].mean():.2f} kWh")
        with col3:
            st.metric("Total Sessions", len(df))
        with col4:
            st.metric("Unique Chargers", df['Charger Serial Number'].nunique())

        # Perform analysis
        analysis, analyzed_df = analyze_charging_data(df.copy())

        # Plots
        plot_analysis(analysis, analyzed_df)

        # Detailed tables
        with st.expander("Detailed Statistics"):
            st.write("### Energy Distribution")
            st.dataframe(df['Charged Energy (kWh)'].describe())

            st.write("### Duration Distribution (minutes)")
            duration_stats = analyzed_df['Duration'].describe()
            st.dataframe(duration_stats)

            st.write("### Charger Utilization")
            utilization = df['Charger Serial Number'].value_counts().head(20)
            st.dataframe(utilization)

        # Download merged
        st.markdown("### Download Merged Data")
        col1, col2 = st.columns(2)
        with col1:
            csv_merged = '\ufeff' + df.to_csv(index=False, encoding='utf-8')
            st.download_button(
                "Download as CSV (UTF-8 BOM)",
                csv_merged.encode('utf-8'),
                "merged_charging_data.csv",
                "text/csv",
                use_container_width=True
            )
        with col2:
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False, sheet_name='Charging Sessions')
            excel_buffer.seek(0)
            st.download_button(
                "Download as Excel",
                excel_buffer,
                "merged_charging_data.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        # Raw data
        with st.expander("View Raw Merged Data"):
            st.dataframe(df.head(preview_rows), use_container_width=True)

        # Summary
        st.info(f"""
        **Summary**: {len(df)} sessions from {len(successful_names)} files. 
        Failed: {len(failed_names)} ({', '.join(failed_names) if failed_names else 'none'}).
        Time range: {df['Start Time'].min().date()} to {df['End Time'].max().date()}.
        """)

if __name__ == "__main__":
    main()
