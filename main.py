import streamlit as st
import pandas as pd
import re
from datetime import datetime
import io
import plotly.graph_objects as go


# Configure the web page
st.set_page_config(page_title="XGS Health Monitor", page_icon="📊", layout="wide")


@st.cache_data(show_spinner="Parsing logs...")
def load_data(uploaded_file):
    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8", errors='ignore'))
    content = stringio.read()

    data = []
    ts_regex = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z)')
    metric_regex = re.compile(r'([A-Za-z0-9_]+)\s*:\s*([+-]?[\d.]+)')

    for line in content.splitlines():
        line = line.strip()
        if not line: continue

        ts_match = ts_regex.match(line)
        if not ts_match: continue

        timestamp_str = ts_match.group(1)
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%SZ')
        except ValueError:
            continue

        rest = line[ts_match.end():].strip()
        match = metric_regex.match(rest)
        if match:
            data.append({'Timestamp': timestamp, 'Metric': match.group(1), 'Value': float(match.group(2))})
        elif 'NPU ping successful' in rest:
            data.append({'Timestamp': timestamp, 'Metric': 'NPU_ping', 'Value': 1.0})

    df = pd.DataFrame(data)
    if df.empty: return df, df

    df['Timestamp'] = pd.to_datetime(df['Timestamp'])
    pivot_df = df.pivot_table(index='Timestamp', columns='Metric', values='Value', aggfunc='last').sort_index()
    return df, pivot_df


# --- AUTOMATED ALERT GENERATOR ---
def generate_alerts(df):
    alerts = []

    # Define preventive thresholds
    rules = [
        ('Host_CPU_Temperature', 70.0, 80.0),
        ('NPU_CPU_Temperature', 75.0, 85.0),
        ('NPU_CPU_Usage', 88.0, 95.0),
        ('Host_Memory_Consumption', 90.0, 95.0),
        ('NPU_Memory_Consumption', 90.0, 95.0)
    ]

    for metric, warn_val, crit_val in rules:
        metric_df = df[df['Metric'] == metric]
        if metric_df.empty: continue

        crit_hits = metric_df[metric_df['Value'] >= crit_val]
        for _, row in crit_hits.head(5).iterrows():
            alerts.append({
                'Time': row['Timestamp'],
                'Severity': '🔴 CRITICAL',
                'Metric': metric,
                'Value': f"{row['Value']:.1f}",
                'Message': f"Threshold breached (> {crit_val}). Immediate action required to prevent failure."
            })

        warn_hits = metric_df[(metric_df['Value'] >= warn_val) & (metric_df['Value'] < crit_val)]
        for _, row in warn_hits.head(5).iterrows():
            alerts.append({
                'Time': row['Timestamp'],
                'Severity': '🟡 WARNING',
                'Metric': metric,
                'Value': f"{row['Value']:.1f}",
                'Message': f"Elevated levels detected (> {warn_val}). Monitor closely."
            })

    return pd.DataFrame(alerts).sort_values(by='Time', ascending=False) if alerts else pd.DataFrame()


# --- APP UI ---
# Added gap="small" to reduce horizontal space between the logo and text
col_logo, col_title = st.columns([1, 10], gap="small")

with col_logo:
    st.image("logo.png", width=80)

with col_title:
    # Use HTML markdown instead of st.title to remove the extra vertical space
    st.markdown(
        "<h1 style='margin-top: 15px; margin-bottom: 0px;'>EmpireOne SC Sophos XGS Health Monitor Dashboard</h1>",
        unsafe_allow_html=True
    )

st.markdown("---")  # Adds a clean line separating the header from the alerts

uploaded_file = st.file_uploader("Upload your log file (e.g., xgs-healthmond.txt)", type=['txt', 'log'])

if uploaded_file is not None:
    df, pivot_df = load_data(uploaded_file)

    if not df.empty:
        st.success(f"Successfully parsed {len(df)} log entries!")

        # ==========================================
        # 1. AUTOMATED ALERTS SECTION (GENERATOR)
        # ==========================================
        st.markdown("---")
        st.subheader("🚨 Preventive Alerts & Anomaly Detection")
        st.caption(
            "Automated scanner checking for high temperatures, memory spikes, and usage limits to prevent firewall failures.")

        alerts_df = generate_alerts(df)

        if not alerts_df.empty:
            # Calculate alert counts (These variables are used in the Executive Summary below)
            crit_count = len(alerts_df[alerts_df['Severity'] == '🔴 CRITICAL'])
            warn_count = len(alerts_df[alerts_df['Severity'] == '🟡 WARNING'])

            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Total Alerts", len(alerts_df))
            col_b.metric("Critical Issues", crit_count)
            col_c.metric("Warnings", warn_count)

            st.dataframe(
                alerts_df,
                use_container_width=True,
                height=300,
                column_config={
                    "Severity": st.column_config.TextColumn("Severity", width="small"),
                    "Time": st.column_config.DatetimeColumn("Time", format="YYYY-MM-DD HH:mm:ss")
                }
            )
        else:
            # Define 0 counts if no alerts exist so the Executive Summary doesn't break
            crit_count = 0
            warn_count = 0
            st.success("✅ All systems nominal. No preventive thresholds breached.")

        # ==========================================
        # 2. EXECUTIVE SUMMARY (PLAIN ENGLISH)
        # ==========================================
        st.markdown("---")
        st.subheader("💼 Executive Summary")

        # Calculate stats for the summary
        max_host_temp = df[df['Metric'] == 'Host_CPU_Temperature']['Value'].max()
        max_npu_usage = df[df['Metric'] == 'NPU_CPU_Usage']['Value'].max()
        max_mem_usage = df[df['Metric'] == 'Host_Memory_Consumption']['Value'].max()
        total_pings = len(df[df['Metric'] == 'NPU_ping'])

        # Generate dynamic text
        if crit_count > 0:
            status_text = f"⚠️ **ATTENTION REQUIRED:** System experienced {crit_count} critical alerts. Peak Host CPU temp reached {max_host_temp:.1f}°C."
            st.error(status_text)
        elif warn_count > 0:
            status_text = f"🟡 **Stable but Elevated:** System is operational but recorded {warn_count} warnings. Peak NPU usage hit {max_npu_usage:.1f}%."
            st.warning(status_text)
        else:
            status_text = f"✅ **All Systems Nominal:** Network is fully operational. Peak Host CPU temp was only {max_host_temp:.1f}°C across {total_pings} health checks."
            st.success(status_text)

        # ==========================================
        # 3. KPI METRICS & PEAK CAPACITY
        # ==========================================
        st.markdown("---")
        st.subheader("📊 System Capacity & Uptime")

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)

        with kpi1:
            st.metric("System Uptime", f"{total_pings} Checks", delta="100% Success", delta_color="off")
        with kpi2:
            st.metric("Peak Host CPU Temp", f"{max_host_temp:.1f} °C")
        with kpi3:
            st.metric("Peak NPU Usage", f"{max_npu_usage:.1f} %")
        with kpi4:
            st.metric("Peak Memory Usage", f"{max_mem_usage:.1f} %")

        st.caption("Overview of maximum thresholds reached during the entire log period. Useful for capacity planning.")

        # ==========================================
        # 4. CHARTS & FILTERS
        # ==========================================
        st.markdown("---")
        st.sidebar.header("Filter Data")
        all_metrics = pivot_df.columns.tolist()
        default_metrics = [m for m in ['NPU_CPU_Temperature', 'Host_CPU_Temperature', 'Fan_Speed', 'NPU_CPU_Usage'] if
                           m in all_metrics]
        selected_metrics = st.sidebar.multiselect("Select metrics to chart", all_metrics, default=default_metrics)

        col1, col2 = st.columns([2, 1])

        with col1:
            st.subheader("📈 Time Series Charts")
            if selected_metrics:
                # Downsample data slightly for performance
                chart_data = pivot_df[selected_metrics].iloc[::10].reset_index()

                # Create strict Plotly Figure
                fig = go.Figure()

                # Add each metric as a separate trace
                for metric in selected_metrics:
                    y_data = chart_data[metric].dropna()
                    x_data = chart_data.loc[y_data.index, 'Timestamp']

                    # DYNAMIC DUAL Y-AXIS: If values are over 1000, put on right axis
                    y_axis_ref = 'y1'
                    if y_data.max() > 1000:
                        y_axis_ref = 'y2'

                    fig.add_trace(go.Scatter(
                        x=x_data,
                        y=y_data,
                        mode='lines',
                        name=metric,
                        yaxis=y_axis_ref,
                        line=dict(width=2)
                    ))

                # Configure the dual layout
                fig.update_layout(
                    template='plotly_dark',
                    yaxis1=dict(title="Temp (°C) / Usage (%)", side="left"),
                    yaxis2=dict(title="Speed (RPM)", side="right", overlaying="y"),
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=20, r=20, t=40, b=20)
                )

                # Render the interactive chart (use_container_width is still standard for plotly)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("👈 Select metrics from the sidebar to view charts.")

        with col2:
            st.subheader("📊 Latest Stats")
            if selected_metrics:
                latest_values = {}
                for metric in selected_metrics:
                    series = pivot_df[metric].dropna()
                    if not series.empty:
                        latest_values[metric] = series.iloc[-1]

                if latest_values:
                    latest_data = pd.DataFrame.from_dict(latest_values, orient='index', columns=['Latest Value'])
                    # FIX: Replaced use_container_width with width='stretch'
                    st.dataframe(latest_data, width='stretch')
                else:
                    st.info("No data available for selected metrics.")
            else:
                st.info("Select metrics to view stats.")

        # ==========================================
        # 5. RAW DATA
        # ==========================================
        st.markdown("---")
        st.subheader("📋 Raw Data Table")
        st.caption("Showing the latest 500 records for performance.")

        table_metric = st.selectbox("Filter table by metric", ["All"] + all_metrics)

        if table_metric != "All":
            display_df = df[df['Metric'] == table_metric].sort_values(by='Timestamp', ascending=False)
        else:
            display_df = df.sort_values(by='Timestamp', ascending=False)

        # FIX: Replaced use_container_width with width='stretch'
        st.dataframe(display_df.head(500), height=400, width='stretch')

    else:
        st.warning("No valid metrics found in the uploaded file. Please check the file format.")
else:
    st.info("👈 Upload a log file to view the dashboard.")

    # ==========================================
    # FOOTER
    # ==========================================
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; color: #888; font-size: 14px;'>"
        "🛡️ Developed by <b>San Carlos Network Security Team</b>"
        "</div>",
        unsafe_allow_html=True
    )