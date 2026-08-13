import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io

# Configure the web page
st.set_page_config(page_title="XGS Health Monitor", page_icon="📊", layout="wide")


# 1. Move file reading and parsing INSIDE the cache to prevent re-reading the 29MB file
@st.cache_data(show_spinner="Parsing logs...")
def load_data(uploaded_file):
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8", errors='ignore'))
    content = stringio.read()

    data = []
    # Pre-compile regex for maximum speed
    ts_regex = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z)')
    metric_regex = re.compile(r'([A-Za-z0-9_]+)\s*:\s*([+-]?[\d.]+)')

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue

        ts_match = ts_regex.match(line)
        if not ts_match:
            continue

        timestamp_str = ts_match.group(1)
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%SZ')
        except ValueError:
            continue

        rest = line[ts_match.end():].strip()

        match = metric_regex.match(rest)
        if match:
            data.append({
                'Timestamp': timestamp,
                'Metric': match.group(1),
                'Value': float(match.group(2))
            })
            continue

        if 'NPU ping successful' in rest:
            data.append({
                'Timestamp': timestamp,
                'Metric': 'NPU_ping',
                'Value': 1.0
            })

    df = pd.DataFrame(data)
    if df.empty:
        return df, df

    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    # Pivot and sort
    pivot_df = df.pivot_table(index='Timestamp', columns='Metric', values='Value', aggfunc='last').sort_index()
    return df, pivot_df


# App UI
st.title("📊 XGS Health Monitor Dashboard")

uploaded_file = st.file_uploader("Upload your log file (e.g., xgs-healthmond.txt)", type=['txt', 'log'])

if uploaded_file is not None:
    df, pivot_df = load_data(uploaded_file)

    if not df.empty:
        st.success(f"Successfully parsed {len(df)} log entries!")

        st.sidebar.header("Filter Data")
        all_metrics = pivot_df.columns.tolist()
        default_metrics = [m for m in ['NPU_CPU_Temperature', 'Host_CPU_Temperature', 'Fan_Speed', 'NPU_CPU_Usage'] if
                           m in all_metrics]
        selected_metrics = st.sidebar.multiselect("Select metrics to chart", all_metrics, default=default_metrics)

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("📈 Time Series Charts")
            if selected_metrics:
                # 2. Aggressive downsampling (every 20th row) to prevent browser freeze
                chart_data = pivot_df[selected_metrics].iloc[::20].reset_index()
                st.line_chart(chart_data, x='Timestamp', y=selected_metrics)
            else:
                st.info("👈 Select metrics from the sidebar to view charts.")

        with col2:
            st.subheader("📊 Latest Stats")
            if selected_metrics:
                latest_data = pivot_df[selected_metrics].tail(1).T
                latest_data.columns = ['Latest Value']
                st.dataframe(latest_data, width='stretch')
            else:
                st.info("Select metrics to view stats.")

        st.markdown("---")
        st.subheader("📋 Raw Data Table")
        st.caption("Showing the latest 500 records for performance.")

        table_metric = st.selectbox("Filter table by metric", ["All"] + all_metrics)

        if table_metric != "All":
            display_df = df[df['Metric'] == table_metric].sort_values(by='Timestamp', ascending=False)
        else:
            display_df = df.sort_values(by='Timestamp', ascending=False)

        # 3. Limit to 500 rows and set a fixed height so the browser doesn't lag
        st.dataframe(display_df.head(500), height=400, width='stretch')

    else:
        st.warning("No valid metrics found in the uploaded file. Please check the file format.")
else:
    st.info("👈 Upload a log file to view the dashboard.")