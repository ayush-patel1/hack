"""
LandGuard AI - Streamlit Dashboard
Interactive web dashboard for industrial plot compliance monitoring.
"""

import json
import os
import io
import sys
import base64
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
from shapely.geometry import shape
import branca.colormap as cm
import numpy as np

# ──────────────────────────────────────────────
#  Page Configuration
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="LandGuard AI - Plot Compliance Monitor",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ──────────────────────────────────────────────
#  Custom CSS
# ──────────────────────────────────────────────
st.markdown("""
<style>
    /* Main header */
    .main-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        padding: 1.5rem 2rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        color: white;
        text-align: center;
    }
    .main-header h1 { margin: 0; font-size: 2rem; font-weight: 700; }
    .main-header p { margin: 0.3rem 0 0; opacity: 0.85; font-size: 0.95rem; }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0,0,0,0.15);
    }
    .metric-card.green  { background: linear-gradient(135deg, #11998e, #38ef7d); }
    .metric-card.red    { background: linear-gradient(135deg, #eb3349, #f45c43); }
    .metric-card.yellow { background: linear-gradient(135deg, #f7971e, #ffd200); }
    .metric-card.blue   { background: linear-gradient(135deg, #4facfe, #00f2fe); }
    .metric-card h3 { margin: 0; font-size: 2rem; font-weight: 800; }
    .metric-card p  { margin: 0.2rem 0 0; font-size: 0.85rem; opacity: 0.9; }

    /* Section headers */
    .section-header {
        border-left: 4px solid #667eea;
        padding-left: 12px;
        margin: 1.5rem 0 1rem;
        font-size: 1.15rem;
        font-weight: 600;
    }

    div[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    div[data-testid="stSidebar"] * { color: #e0e0e0 !important; }

    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        border-radius: 8px 8px 0 0;
    }
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
#  Data Loading
# ──────────────────────────────────────────────
@st.cache_data
def load_data():
    """Load all data files."""
    data = {}

    vio_path = os.path.join(DATA_DIR, "violations.geojson")
    ref_path = os.path.join(DATA_DIR, "reference_plots.geojson")
    cur_path = os.path.join(DATA_DIR, "current_plots.geojson")
    meta_path = os.path.join(DATA_DIR, "plot_metadata.json")
    summary_path = os.path.join(DATA_DIR, "violation_summary.json")

    for name, path in [("violations", vio_path), ("reference", ref_path),
                       ("current", cur_path), ("metadata", meta_path),
                       ("summary", summary_path)]:
        if os.path.exists(path):
            with open(path) as f:
                data[name] = json.load(f)
        else:
            data[name] = None

    # Load satellite change data if available
    sat_changes_path = os.path.join(DATA_DIR, "satellite_changes.geojson")
    sat_data_path = os.path.join(DATA_DIR, "satellite", "satellite_data.json")
    if os.path.exists(sat_changes_path):
        with open(sat_changes_path) as f:
            data["satellite_changes"] = json.load(f)
    else:
        data["satellite_changes"] = None
    if os.path.exists(sat_data_path):
        with open(sat_data_path) as f:
            data["satellite_raw"] = json.load(f)
    else:
        data["satellite_raw"] = None

    # Load CSIDC scraped plots and allotment map
    csidc_path = os.path.join(DATA_DIR, "csidc_real_plots.geojson")
    allot_path = os.path.join(DATA_DIR, "allotment_map.geojson")
    for name, path in [("csidc_plots", csidc_path), ("allotment", allot_path)]:
        if os.path.exists(path):
            with open(path) as f:
                data[name] = json.load(f)
        else:
            data[name] = None

    return data


def data_to_df(data):
    """Convert violation GeoJSON features to a DataFrame."""
    if not data.get("violations"):
        return pd.DataFrame()
    rows = []
    for feat in data["violations"]["features"]:
        p = feat["properties"]
        rows.append({
            "Plot ID": p.get("plot_id", ""),
            "Violation Type": p.get("primary_violation", ""),
            "All Violations": ", ".join(p.get("violation_types", [])),
            "Severity": p.get("severity", ""),
            "Area Ref (m²)": p.get("area_ref_sqm", 0),
            "Area Cur (m²)": p.get("area_cur_sqm", 0),
            "Area Diff (%)": p.get("area_diff_pct", 0),
            "Overlap (%)": p.get("overlap_pct", 0),
            "IoU": p.get("iou", 0),
            "Detection Date": p.get("detection_date", ""),
            "Action Required": p.get("action_required", ""),
            "Est. Cost (₹)": p.get("estimated_cost_inr", 0),
        })
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
#  Sidebar
# ──────────────────────────────────────────────
def render_sidebar(df):
    """Render sidebar with filters."""
    with st.sidebar:
        st.markdown("## 🛡️ LandGuard AI")
        st.markdown("---")
        st.markdown("### 🔍 Filters")

        # Violation type filter
        vio_types = ["All"] + sorted(df["Violation Type"].unique().tolist()) if len(df) > 0 else ["All"]
        selected_type = st.selectbox("Violation Type", vio_types)

        # Severity filter
        sev_options = ["All"] + sorted(df["Severity"].unique().tolist()) if len(df) > 0 else ["All"]
        selected_severity = st.selectbox("Severity", sev_options)

        # Plot ID search
        plot_search = st.text_input("🔎 Search Plot ID", placeholder="e.g. P001")

        st.markdown("---")
        st.markdown("### ℹ️ About")
        st.markdown(
            "Automated compliance monitoring for CSIDC industrial plots. "
            "Detects encroachments, unauthorized construction, and vacant land."
        )
        st.markdown(f"**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        # Apply filters
        filtered = df.copy()
        if selected_type != "All":
            filtered = filtered[filtered["Violation Type"] == selected_type]
        if selected_severity != "All":
            filtered = filtered[filtered["Severity"] == selected_severity]
        if plot_search:
            filtered = filtered[filtered["Plot ID"].str.contains(plot_search.upper(), na=False)]

        return filtered


# ──────────────────────────────────────────────
#  Header & Metrics
# ──────────────────────────────────────────────
def render_header():
    st.markdown("""
    <div class="main-header">
        <h1>🛡️ LandGuard AI</h1>
        <p>Automated Industrial Plot Compliance Monitor — Powered by Computer Vision & GIS</p>
    </div>
    """, unsafe_allow_html=True)


def render_metrics(data, df):
    summary = data.get("summary", {})
    total = summary.get("total_plots", 0)
    violations = summary.get("total_violations", 0)
    critical = summary.get("severity_breakdown", {}).get("CRITICAL", 0)
    cost = summary.get("total_estimated_cost_inr", 0)

    # Estimated savings from automated vs manual drone surveys
    manual_cost = total * 25000  # ₹25,000 per manual drone survey per plot
    savings = manual_cost - 50000  # Automated system fixed cost

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card blue">
            <h3>{total}</h3>
            <p>📊 Total Plots Monitored</p>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card red">
            <h3>{violations}</h3>
            <p>⚠️ Violations Detected</p>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card yellow">
            <h3>{critical}</h3>
            <p>🔴 Critical Issues</p>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""
        <div class="metric-card green">
            <h3>₹{savings:,.0f}</h3>
            <p>💰 Estimated Cost Saved</p>
        </div>""", unsafe_allow_html=True)


# ──────────────────────────────────────────────
#  Map
# ──────────────────────────────────────────────
def render_map(data):
    st.markdown('<div class="section-header">🗺️ Interactive Compliance Map</div>',
                unsafe_allow_html=True)

    # Determine center from metadata
    meta = data.get("metadata", [])
    if meta:
        lat = np.mean([p["coordinates"][0] for p in meta])
        lon = np.mean([p["coordinates"][1] for p in meta])
    else:
        lat, lon = 21.2514, 81.6296

    m = folium.Map(location=[lat, lon], zoom_start=15,
                   tiles="CartoDB dark_matter")

    # ── Reference polygons (green, dashed) ──
    ref_group = folium.FeatureGroup(name="Reference Boundaries", show=True)
    if data.get("reference"):
        for feat in data["reference"]["features"]:
            coords = feat["geometry"]["coordinates"][0]
            latlng = [(c[1], c[0]) for c in coords]
            pid = feat["properties"].get("plot_id", "")
            folium.Polygon(
                locations=latlng,
                color="#38ef7d",
                weight=2,
                fill=True,
                fill_color="#38ef7d",
                fill_opacity=0.15,
                dash_array="6",
                tooltip=f"📐 {pid} — Reference Boundary",
            ).add_to(ref_group)
    ref_group.add_to(m)

    # ── Violation / current polygons ──
    vio_group = folium.FeatureGroup(name="Current Boundaries", show=True)

    # Compliant plots (from current that are NOT in violations)
    violated_ids = set()
    if data.get("violations"):
        for feat in data["violations"]["features"]:
            violated_ids.add(feat["properties"].get("plot_id", ""))

    if data.get("current"):
        for feat in data["current"]["features"]:
            pid = feat["properties"].get("plot_id", "")
            coords = feat["geometry"]["coordinates"][0]
            latlng = [(c[1], c[0]) for c in coords]
            if pid not in violated_ids:
                folium.Polygon(
                    locations=latlng,
                    color="#2ecc71",
                    weight=2,
                    fill=True,
                    fill_color="#2ecc71",
                    fill_opacity=0.25,
                    tooltip=f"✅ {pid} — Compliant",
                ).add_to(vio_group)

    # Violated plots
    severity_colors = {
        "CRITICAL": "#e74c3c",
        "HIGH": "#e67e22",
        "MEDIUM": "#f1c40f",
        "LOW": "#95a5a6",
    }
    if data.get("violations"):
        for feat in data["violations"]["features"]:
            p = feat["properties"]
            pid = p.get("plot_id", "")
            sev = p.get("severity", "LOW")
            vtype = p.get("primary_violation", "")
            color = severity_colors.get(sev, "#e74c3c")
            coords = feat["geometry"]["coordinates"][0]
            latlng = [(c[1], c[0]) for c in coords]

            tooltip_html = (
                f"<b>🏗️ {pid}</b><br>"
                f"<b>Type:</b> {vtype}<br>"
                f"<b>Severity:</b> {sev}<br>"
                f"<b>Area Diff:</b> {p.get('area_diff_pct', 0):.1f}%<br>"
                f"<b>Action:</b> {p.get('action_required', '')}"
            )
            folium.Polygon(
                locations=latlng,
                color=color,
                weight=3,
                fill=True,
                fill_color=color,
                fill_opacity=0.35,
                tooltip=folium.Tooltip(tooltip_html),
                popup=folium.Popup(tooltip_html, max_width=300),
            ).add_to(vio_group)

    vio_group.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # Legend
    legend_html = """
    <div style="position:fixed; bottom:50px; left:50px; z-index:1000;
         background:rgba(0,0,0,0.8); padding:12px 16px; border-radius:8px;
         color:white; font-size:12px; box-shadow:0 2px 10px rgba(0,0,0,0.3);">
      <b>Legend</b><br>
      <span style="color:#38ef7d">━━</span> Reference &nbsp;
      <span style="color:#2ecc71">■</span> Compliant &nbsp;
      <span style="color:#e74c3c">■</span> Critical &nbsp;
      <span style="color:#e67e22">■</span> High &nbsp;
      <span style="color:#f1c40f">■</span> Medium &nbsp;
      <span style="color:#95a5a6">■</span> Low
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    st_folium(m, width=None, height=520, use_container_width=True)


# ──────────────────────────────────────────────
#  Image Comparison
# ──────────────────────────────────────────────
def render_image_comparison(data):
    st.markdown('<div class="section-header">🖼️ Side-by-Side Comparison</div>',
                unsafe_allow_html=True)

    meta = data.get("metadata", [])
    if not meta:
        st.info("No plot metadata available for image comparison.")
        return

    plot_ids = [p["plot_id"] for p in meta]
    selected = st.selectbox("Select Plot for Comparison", plot_ids)
    plot = next((p for p in meta if p["plot_id"] == selected), None)

    if plot:
        c1, c2 = st.columns(2)
        ref_path = os.path.join(BASE_DIR, plot["reference_image"])
        cur_path = os.path.join(BASE_DIR, plot["current_image"])
        with c1:
            st.markdown("**📸 Reference Image**")
            if os.path.exists(ref_path):
                st.image(ref_path, use_container_width=True)
            else:
                st.warning("Reference image not found.")
        with c2:
            st.markdown("**📸 Current Image**")
            if os.path.exists(cur_path):
                st.image(cur_path, use_container_width=True)
            else:
                st.warning("Current image not found.")

        # Show plot info
        st.markdown(
            f"**Plot:** {plot['plot_id']} &nbsp;|&nbsp; "
            f"**Area:** {plot['area_sqm']:,.0f} m² &nbsp;|&nbsp; "
            f"**Status:** {plot['violation_type']} &nbsp;|&nbsp; "
            f"**Owner:** {plot.get('owner', 'N/A')}"
        )


# ──────────────────────────────────────────────
#  Violation Table
# ──────────────────────────────────────────────
def render_table(df):
    st.markdown('<div class="section-header">📋 Violation Details</div>',
                unsafe_allow_html=True)
    if df.empty:
        st.success("🎉 No violations found matching your filters.")
        return

    # Colour-code severity
    def color_severity(val):
        colors = {
            "CRITICAL": "background-color: #e74c3c; color: white;",
            "HIGH": "background-color: #e67e22; color: white;",
            "MEDIUM": "background-color: #f1c40f; color: black;",
            "LOW": "background-color: #95a5a6; color: white;",
        }
        return colors.get(val, "")

    display_cols = ["Plot ID", "Violation Type", "Severity", "Area Diff (%)",
                    "Overlap (%)", "Detection Date", "Action Required", "Est. Cost (₹)"]
    styled = (df[display_cols]
              .style.applymap(color_severity, subset=["Severity"])
              .format({"Area Diff (%)": "{:.1f}", "Overlap (%)": "{:.1f}",
                       "Est. Cost (₹)": "₹{:,.0f}"}))
    st.dataframe(styled, use_container_width=True, height=350)


# ──────────────────────────────────────────────
#  Charts
# ──────────────────────────────────────────────
def render_charts(df, data):
    st.markdown('<div class="section-header">📊 Analytics</div>',
                unsafe_allow_html=True)

    if df.empty:
        st.info("No data available for charts.")
        return

    c1, c2 = st.columns(2)

    with c1:
        type_counts = df["Violation Type"].value_counts().reset_index()
        type_counts.columns = ["Type", "Count"]
        fig_pie = px.pie(
            type_counts, names="Type", values="Count",
            title="Violation Distribution by Type",
            color_discrete_sequence=px.colors.qualitative.Set2,
            hole=0.4,
        )
        fig_pie.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            title_font_size=14,
            margin=dict(t=40, b=20, l=20, r=20),
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        sev_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
        sev_counts = df["Severity"].value_counts().reindex(sev_order).fillna(0).reset_index()
        sev_counts.columns = ["Severity", "Count"]
        sev_colors = {"CRITICAL": "#e74c3c", "HIGH": "#e67e22",
                      "MEDIUM": "#f1c40f", "LOW": "#95a5a6"}
        fig_bar = px.bar(
            sev_counts, x="Severity", y="Count",
            title="Violations by Severity",
            color="Severity",
            color_discrete_map=sev_colors,
        )
        fig_bar.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            title_font_size=14,
            showlegend=False,
            margin=dict(t=40, b=20, l=20, r=20),
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    # Cost impact chart
    if len(df) > 0:
        cost_by_type = df.groupby("Violation Type")["Est. Cost (₹)"].sum().reset_index()
        cost_by_type.columns = ["Type", "Cost"]
        fig_cost = px.bar(
            cost_by_type, x="Type", y="Cost",
            title="Estimated Cost Impact by Violation Type (₹)",
            color="Type",
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_cost.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            title_font_size=14,
            showlegend=False,
            margin=dict(t=40, b=20, l=20, r=20),
            yaxis_tickformat="₹,.0f",
        )
        st.plotly_chart(fig_cost, use_container_width=True)


# ──────────────────────────────────────────────
#  Downloads
# ──────────────────────────────────────────────
def render_downloads(df, data):
    st.markdown('<div class="section-header">📥 Export & Reports</div>',
                unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)

    with c1:
        if not df.empty:
            csv = df.to_csv(index=False)
            st.download_button(
                "📄 Download Violations CSV",
                csv,
                "landguard_violations.csv",
                "text/csv",
                use_container_width=True,
            )

    with c2:
        vio_path = os.path.join(DATA_DIR, "violations.geojson")
        if os.path.exists(vio_path):
            with open(vio_path) as f:
                geojson_str = f.read()
            st.download_button(
                "🗺️ Download Violations GeoJSON",
                geojson_str,
                "violations.geojson",
                "application/json",
                use_container_width=True,
            )

    with c3:
        report_path = os.path.join(DATA_DIR, "compliance_report.pdf")
        if os.path.exists(report_path):
            with open(report_path, "rb") as f:
                pdf_bytes = f.read()
            st.download_button(
                "📑 Download PDF Report",
                pdf_bytes,
                "landguard_compliance_report.pdf",
                "application/pdf",
                use_container_width=True,
            )
        else:
            if st.button("📑 Generate PDF Report", use_container_width=True):
                with st.spinner("Generating report..."):
                    try:
                        from generate_report import generate_pdf
                        generate_pdf()
                        st.success("✅ Report generated! Click the button again to download.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Report generation failed: {e}")


# ──────────────────────────────────────────────
#  Satellite Data Tab
# ──────────────────────────────────────────────
def render_satellite_tab(data):
    st.markdown('<div class="section-header">🛰️ Satellite Data — Google Earth Engine</div>',
                unsafe_allow_html=True)

    # ── Upload allotment map ──
    st.markdown("#### 📂 Upload Plot Allotment Map")
    uploaded = st.file_uploader(
        "Upload your plot allotment GeoJSON file",
        type=["geojson", "json"],
        help="Upload a GeoJSON file containing plot boundary polygons."
    )
    if uploaded:
        try:
            allotment = json.load(uploaded)
            out_path = os.path.join(DATA_DIR, "allotment_map.geojson")
            with open(out_path, "w") as f:
                json.dump(allotment, f, indent=2)
            num_feats = len(allotment.get("features", []))
            st.success(f"Allotment map loaded: {num_feats} plot polygons saved.")
        except Exception as e:
            st.error(f"Invalid GeoJSON: {e}")

    st.markdown("---")

    # ── Fetch controls ──
    st.markdown("#### 🛰️ Fetch Satellite Imagery")
    c1, c2, c3 = st.columns(3)
    with c1:
        ref_date = st.date_input("Reference Date",
                                 value=datetime.now() - __import__('datetime').timedelta(days=180))
    with c2:
        cur_date = st.date_input("Current Date", value=datetime.now())
    with c3:
        source = st.selectbox("Data Source", ["Sentinel-1 (SAR)", "Sentinel-2 (Optical)", "Both"])

    # Determine which plot file to use
    allotment_path = os.path.join(DATA_DIR, "allotment_map.geojson")
    if not os.path.exists(allotment_path):
        allotment_path = os.path.join(DATA_DIR, "reference_plots.geojson")

    if st.button("🚀 Fetch Satellite Data & Run Change Detection", use_container_width=True):
        with st.spinner("Connecting to Google Earth Engine..."):
            try:
                from satellite_fetch import fetch_all
                fetch_all(
                    plots_geojson=allotment_path,
                    reference_date=ref_date.strftime("%Y-%m-%d"),
                    current_date=cur_date.strftime("%Y-%m-%d"),
                )
                st.success("Satellite data fetched!")
            except Exception as e:
                st.warning(f"GEE fetch skipped: {e}")
                st.info("Falling back to local image-based change detection...")

        with st.spinner("Running polygon-based change detection..."):
            try:
                from change_detection import run as run_cd
                run_cd(plots_geojson=allotment_path)
                st.success("Change detection complete!")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Change detection failed: {e}")

    st.markdown("---")

    # ── Display satellite change results ──
    sat_changes = data.get("satellite_changes")
    if sat_changes and sat_changes.get("features"):
        st.markdown("#### 📊 Satellite Change Detection Results")

        rows = []
        for feat in sat_changes["features"]:
            p = feat["properties"]
            ev = p.get("satellite_evidence", {})
            sar = ev.get("sar", {})
            ndvi = ev.get("ndvi", {})
            ndbi = ev.get("ndbi", {})
            tile = ev.get("tile_diff", {})
            rows.append({
                "Plot ID": p.get("plot_id", ""),
                "Satellite Verdict": p.get("violation_type", ""),
                "Severity": p.get("severity", "-"),
                "Confidence": f"{p.get('confidence', 0):.0%}",
                "SAR Change (dB)": sar.get("change_db", "-"),
                "SAR Signal": sar.get("interpretation", "-"),
                "NDVI Now": ndvi.get("cur_ndvi", "-"),
                "NDVI Signal": ndvi.get("interpretation", "-"),
                "NDBI Signal": ndbi.get("interpretation", "-"),
                "Pixel Change %": tile.get("change_pct", "-"),
            })

        sat_df = pd.DataFrame(rows)

        # Summary metrics
        sat_violations = [r for r in rows if r["Satellite Verdict"] != "COMPLIANT"]
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.metric("Plots Analyzed", len(rows))
        with mc2:
            st.metric("Satellite Violations", len(sat_violations))
        with mc3:
            methods_used = []
            if any(r["SAR Change (dB)"] != "-" for r in rows):
                methods_used.append("SAR")
            if any(r["NDVI Now"] != "-" for r in rows):
                methods_used.append("NDVI")
            if any(r["Pixel Change %"] != "-" for r in rows):
                methods_used.append("Pixel")
            st.metric("Detection Methods", ", ".join(methods_used) or "N/A")

        st.dataframe(sat_df, use_container_width=True, height=350)

        # Change detection chart
        verdict_counts = sat_df["Satellite Verdict"].value_counts().reset_index()
        verdict_counts.columns = ["Verdict", "Count"]
        fig = px.pie(verdict_counts, names="Verdict", values="Count",
                     title="Satellite Change Detection Verdicts",
                     color_discrete_sequence=px.colors.qualitative.Bold,
                     hole=0.4)
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#e0e0e0",
            margin=dict(t=40, b=20, l=20, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Show change mask images if available
        change_mask_dir = os.path.join(SAT_DIR, "change_masks")
        if os.path.exists(change_mask_dir):
            masks = [f for f in os.listdir(change_mask_dir) if f.endswith(".png") or f.endswith(".jpg")]
            if masks:
                st.markdown("#### 🔍 Change Masks (Red = Changed Areas)")
                cols = st.columns(min(len(masks), 4))
                for i, mask_file in enumerate(masks[:8]):
                    with cols[i % 4]:
                        mask_path = os.path.join(change_mask_dir, mask_file)
                        st.image(mask_path, caption=mask_file, use_container_width=True)
    else:
        st.info(
            "No satellite change data available yet. "
            "Click the button above to fetch data from Google Earth Engine, "
            "or the system will use local image comparison as fallback."
        )

SAT_DIR = os.path.join(DATA_DIR, "satellite")


# ──────────────────────────────────────────────
#  Plot Comparison Tab (GeoJSON overlay)
# ──────────────────────────────────────────────
def render_plot_comparison_tab(data):
    """Interactive GeoJSON comparison: allotted boundaries vs current development."""

    st.markdown('<div class="section-header">🔍 GeoJSON Plot Comparison — Allotted vs Current</div>',
                unsafe_allow_html=True)

    # ── Section 0: Real-Time Live Fetch from CSIDC ─────────
    st.markdown("### 🔄 Fetch Live Data from CSIDC GeoServer")
    st.caption("Real-time WFS data from cggis.cgstate.gov.in — no authentication required")

    fc1, fc2 = st.columns([2, 1])
    with fc1:
        area_filter = st.text_input(
            "🏭 Industrial Area Filter",
            placeholder="e.g. URLA, SILTARA, TIFRA (leave empty for all)",
            help="Filter plots by industrial area name. Partial matches work."
        )
    with fc2:
        max_plots = st.number_input("Max Plots", min_value=50, max_value=5000,
                                    value=500, step=100)

    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        fetch_plots_btn = st.button("📥 Fetch Plots + Boundaries",
                                    use_container_width=True, key="fetch_live")
    with btn_col2:
        fetch_areas_btn = st.button("📋 List Industrial Areas",
                                    use_container_width=True, key="list_areas")
    with btn_col3:
        clear_btn = st.button("🗑️ Clear Cached Data",
                              use_container_width=True, key="clear_live")

    if fetch_areas_btn:
        with st.spinner("🔍 Querying CSIDC GeoServer for available areas..."):
            try:
                from fetch_csidc_live import list_industrial_areas
                areas = list_industrial_areas()
                st.success(f"✅ Found **{len(areas)}** industrial areas")
                # Display in columns
                cols = st.columns(3)
                for i, area in enumerate(areas):
                    with cols[i % 3]:
                        st.markdown(f"• {area}")
            except Exception as e:
                st.error(f"Failed to fetch areas: {e}")

    if fetch_plots_btn:
        progress_bar = st.progress(0, text="Connecting to CSIDC GeoServer...")
        status_text = st.empty()

        def update_progress(fetched, batch):
            pct = min(fetched / max_plots, 0.95)
            progress_bar.progress(pct, text=f"Fetched {fetched:,} features (batch {batch})...")

        try:
            from fetch_csidc_live import fetch_and_save
            with st.spinner(""):
                plots_path, bounds_path, n_plots, n_bounds = fetch_and_save(
                    industrial_area=area_filter or None,
                    progress_callback=update_progress,
                )

            progress_bar.progress(1.0, text="✅ Complete!")
            st.success(
                f"🎉 Fetched **{n_plots:,} plots** and **{n_bounds} boundaries** "
                f"from CSIDC GeoServer!"
            )

            # Clear cache so new data loads
            st.cache_data.clear()
            st.rerun()

        except Exception as e:
            progress_bar.empty()
            st.error(f"❌ Fetch failed: {e}")
            st.info("The GeoServer may be temporarily unavailable. Try again in a minute.")

    if clear_btn:
        import os as _os
        for fname in ["csidc_live_plots.geojson", "csidc_live_boundaries.geojson"]:
            fpath = os.path.join(DATA_DIR, fname)
            if _os.path.exists(fpath):
                _os.remove(fpath)
        st.success("🗑️ Live data cleared.")
        st.cache_data.clear()
        st.rerun()

    # ── Display live-fetched data if available ──
    live_plots_path = os.path.join(DATA_DIR, "csidc_live_plots.geojson")
    live_bounds_path = os.path.join(DATA_DIR, "csidc_live_boundaries.geojson")

    if os.path.exists(live_plots_path):
        with open(live_plots_path) as f:
            live_plots = json.load(f)
        live_bounds = None
        if os.path.exists(live_bounds_path):
            with open(live_bounds_path) as f:
                live_bounds = json.load(f)

        feats = live_plots.get("features", [])
        if feats:
            st.markdown("#### 🗺️ Live CSIDC Plot Data")

            # Summary metrics
            mc1, mc2, mc3, mc4 = st.columns(4)
            areas_set = set(f.get("properties", {}).get("INDUSTRIAL", "") for f in feats)
            alloted = sum(1 for f in feats
                         if "ALLOT" in (f.get("properties", {}).get("STATUS", "") or "").upper())
            vacant = sum(1 for f in feats
                        if "VACANT" in (f.get("properties", {}).get("STATUS", "") or "").upper())
            with mc1:
                st.markdown(f"""
                <div class="metric-card blue">
                    <h3>{len(feats):,}</h3>
                    <p>📊 Total Plots</p>
                </div>""", unsafe_allow_html=True)
            with mc2:
                st.markdown(f"""
                <div class="metric-card green">
                    <h3>{alloted:,}</h3>
                    <p>✅ Allotted</p>
                </div>""", unsafe_allow_html=True)
            with mc3:
                st.markdown(f"""
                <div class="metric-card yellow">
                    <h3>{vacant:,}</h3>
                    <p>⚠️ Vacant</p>
                </div>""", unsafe_allow_html=True)
            with mc4:
                st.markdown(f"""
                <div class="metric-card">
                    <h3>{len(areas_set)}</h3>
                    <p>🏭 Industrial Areas</p>
                </div>""", unsafe_allow_html=True)

            # Map
            all_lons, all_lats = [], []
            for feat in feats:
                geom = feat.get("geometry", {})
                gtype = geom.get("type", "")
                if gtype == "MultiPolygon":
                    for poly in geom["coordinates"]:
                        for ring in poly:
                            for c in ring:
                                all_lons.append(c[0])
                                all_lats.append(c[1])
                elif gtype == "Polygon":
                    for ring in geom["coordinates"]:
                        for c in ring:
                            all_lons.append(c[0])
                            all_lats.append(c[1])
            center_lat = np.mean(all_lats) if all_lats else 21.25
            center_lon = np.mean(all_lons) if all_lons else 81.63

            m_live = folium.Map(location=[center_lat, center_lon], zoom_start=14,
                                tiles="CartoDB dark_matter")

            # Status color mapping
            status_colors = {
                "ALLOTED": "#2ecc71",
                "ALLOTTED": "#2ecc71",
                "VACANT": "#e74c3c",
                "PROPOSED": "#f39c12",
                "CANCELLED": "#95a5a6",
            }

            # Add boundary polygons (thick red outline)
            if live_bounds and live_bounds.get("features"):
                bound_group = folium.FeatureGroup(name="🔴 Area Boundaries", show=True)
                for feat in live_bounds["features"]:
                    geom = feat.get("geometry", {})
                    gtype = geom.get("type", "")
                    props = feat.get("properties", {})
                    coords_list = []
                    if gtype == "MultiPolygon":
                        coords_list = [geom["coordinates"][0][0]]
                    elif gtype == "Polygon":
                        coords_list = [geom["coordinates"][0]]

                    for coords in coords_list:
                        latlng = [(c[1], c[0]) for c in coords]
                        folium.Polygon(
                            locations=latlng,
                            color="#e74c3c",
                            weight=4,
                            fill=False,
                            dash_array="10 5",
                            tooltip=f"🏭 {props.get('industrial', 'Unknown')} — Boundary",
                        ).add_to(bound_group)
                bound_group.add_to(m_live)

            # Add plot polygons
            plot_group = folium.FeatureGroup(name="📊 Plot Polygons", show=True)
            for feat in feats:
                geom = feat.get("geometry", {})
                gtype = geom.get("type", "")
                props = feat.get("properties", {})

                coords_list = []
                if gtype == "MultiPolygon":
                    coords_list = [geom["coordinates"][0][0]]
                elif gtype == "Polygon":
                    coords_list = [geom["coordinates"][0]]

                status = (props.get("STATUS", "") or "").upper()
                color = "#3498db"
                for key, c in status_colors.items():
                    if key in status:
                        color = c
                        break

                for coords in coords_list:
                    latlng = [(c[1], c[0]) for c in coords]
                    tooltip_html = (
                        f"<b>Plot {props.get('PLOT_NO', '?')}</b><br>"
                        f"Area: {props.get('INDUSTRIAL', 'N/A')}<br>"
                        f"Type: {props.get('TYPE', 'N/A')}<br>"
                        f"Status: {props.get('STATUS', 'N/A')}<br>"
                        f"Remark: {props.get('REMARK', 'N/A')}"
                    )
                    folium.Polygon(
                        locations=latlng,
                        color=color,
                        weight=2,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.25,
                        tooltip=folium.Tooltip(tooltip_html),
                    ).add_to(plot_group)

            plot_group.add_to(m_live)
            folium.LayerControl(collapsed=False).add_to(m_live)

            # Legend
            live_legend = """
            <div style="position:fixed; bottom:50px; left:50px; z-index:1000;
                 background:rgba(0,0,0,0.85); padding:14px 18px; border-radius:10px;
                 color:white; font-size:12px; box-shadow:0 2px 12px rgba(0,0,0,0.4);">
              <b>Live Data Legend</b><br>
              <span style="color:#e74c3c">━ ━</span> Area Boundary &nbsp;
              <span style="color:#2ecc71">■</span> Allotted &nbsp;
              <span style="color:#e74c3c">■</span> Vacant &nbsp;
              <span style="color:#f39c12">■</span> Proposed &nbsp;
              <span style="color:#3498db">■</span> Other
            </div>
            """
            m_live.get_root().html.add_child(folium.Element(live_legend))

            st_folium(m_live, width=None, height=550, use_container_width=True,
                      key="live_csidc_map")

            # Data table
            st.markdown("#### 📋 Plot Details")
            table_rows = []
            for feat in feats:
                p = feat.get("properties", {})
                table_rows.append({
                    "Plot No": p.get("PLOT_NO", ""),
                    "Industrial Area": p.get("INDUSTRIAL", ""),
                    "Type": p.get("TYPE", ""),
                    "Status": p.get("STATUS", ""),
                    "Remark": p.get("REMARK", ""),
                    "Label": p.get("LABEL_2", ""),
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True,
                         height=400)

    st.markdown("---")

    # ── Section 1: CSIDC Scraped Data Map ──────────────────
    csidc = data.get("csidc_plots")
    if csidc and csidc.get("features"):
        st.markdown("### 🏗️ CSIDC Scraped Plot Polygons")
        st.caption("Polygons extracted from CSIDC GeoServer WMS tiles")

        # Compute center from features
        all_lons, all_lats = [], []
        for feat in csidc["features"]:
            if feat["geometry"]["type"] == "Polygon":
                for coord in feat["geometry"]["coordinates"][0]:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])
        center_lat = np.mean(all_lats) if all_lats else 22.98
        center_lon = np.mean(all_lons) if all_lons else 82.91

        m_csidc = folium.Map(location=[center_lat, center_lon], zoom_start=16,
                             tiles="CartoDB dark_matter")

        # Color palette for CSIDC plots
        csidc_colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6",
                        "#1abc9c", "#e67e22", "#00bcd4", "#ff5722", "#607d8b"]
        for i, feat in enumerate(csidc["features"]):
            if feat["geometry"]["type"] != "Polygon":
                continue
            coords = feat["geometry"]["coordinates"][0]
            latlng = [(c[1], c[0]) for c in coords]
            pid = feat["properties"].get("plot_id", f"Plot_{i}")
            area_px = feat["properties"].get("area_px", 0)
            color = csidc_colors[i % len(csidc_colors)]

            folium.Polygon(
                locations=latlng,
                color=color,
                weight=3,
                fill=True,
                fill_color=color,
                fill_opacity=0.3,
                tooltip=f"🏗️ {pid} | Area: {area_px:,} px",
                popup=folium.Popup(
                    f"<b>{pid}</b><br>"
                    f"Source: {feat['properties'].get('source', 'CSIDC')}<br>"
                    f"Area (px): {area_px:,}",
                    max_width=250
                ),
            ).add_to(m_csidc)

        folium.LayerControl().add_to(m_csidc)
        st_folium(m_csidc, width=None, height=480, use_container_width=True,
                  key="csidc_map")

        # Summary
        st.info(f"📊 **{len(csidc['features'])} polygons** scraped from CSIDC GeoServer")
    else:
        st.warning("No CSIDC scraped data found (`data/csidc_real_plots.geojson`).")

    st.markdown("---")

    # ── Section 2: Reference vs Current Boundary Comparison ─
    ref_data = data.get("reference")
    cur_data = data.get("current")

    if ref_data and cur_data and ref_data.get("features") and cur_data.get("features"):
        st.markdown("### 📐 Allotted (Reference) vs Current Development")
        st.caption("Green dashed = allotted boundary · Solid = current development")

        # Build lookup by plot_id
        ref_by_id = {f["properties"]["plot_id"]: f for f in ref_data["features"]}
        cur_by_id = {f["properties"]["plot_id"]: f for f in cur_data["features"]}
        all_ids = sorted(set(list(ref_by_id.keys()) + list(cur_by_id.keys())))

        # Compute center
        all_lons, all_lats = [], []
        for feat in ref_data["features"] + cur_data["features"]:
            if feat["geometry"]["type"] == "Polygon":
                for coord in feat["geometry"]["coordinates"][0]:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])
        center_lat = np.mean(all_lats) if all_lats else 21.25
        center_lon = np.mean(all_lons) if all_lons else 81.63

        m_compare = folium.Map(location=[center_lat, center_lon], zoom_start=15,
                               tiles="CartoDB dark_matter")

        ref_group = folium.FeatureGroup(name="✅ Allotted Boundaries (Reference)", show=True)
        cur_group = folium.FeatureGroup(name="🏗️ Current Development", show=True)
        diff_group = folium.FeatureGroup(name="⚠️ Change Highlight", show=True)

        violation_colors = {
            "COMPLIANT": "#2ecc71",
            "ENCROACHMENT": "#e74c3c",
            "UNAUTHORIZED_CONSTRUCTION": "#e67e22",
            "VACANT_PLOT": "#95a5a6",
            "BOUNDARY_DEVIATION": "#f1c40f",
        }

        comparison_rows = []

        for pid in all_ids:
            ref_feat = ref_by_id.get(pid)
            cur_feat = cur_by_id.get(pid)

            # Reference polygon (green dashed)
            if ref_feat and ref_feat["geometry"]["type"] == "Polygon":
                coords = ref_feat["geometry"]["coordinates"][0]
                latlng = [(c[1], c[0]) for c in coords]
                folium.Polygon(
                    locations=latlng,
                    color="#38ef7d",
                    weight=2,
                    fill=True,
                    fill_color="#38ef7d",
                    fill_opacity=0.1,
                    dash_array="8 4",
                    tooltip=f"📐 {pid} — Allotted Boundary",
                ).add_to(ref_group)

            # Current polygon (color by violation type)
            if cur_feat and cur_feat["geometry"]["type"] == "Polygon":
                coords = cur_feat["geometry"]["coordinates"][0]
                latlng = [(c[1], c[0]) for c in coords]
                vtype = cur_feat["properties"].get("violation_type", "COMPLIANT")
                color = violation_colors.get(vtype, "#3498db")

                folium.Polygon(
                    locations=latlng,
                    color=color,
                    weight=3,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.3,
                    tooltip=f"🏗️ {pid} — {vtype}",
                    popup=folium.Popup(
                        f"<b>{pid}</b><br>Status: {vtype}", max_width=250
                    ),
                ).add_to(cur_group)

            # Compute area & IoU if both exist
            if ref_feat and cur_feat:
                try:
                    ref_shape = shape(ref_feat["geometry"])
                    cur_shape = shape(cur_feat["geometry"])
                    ref_area = ref_shape.area * 1e10  # rough m² at this latitude
                    cur_area = cur_shape.area * 1e10
                    intersection = ref_shape.intersection(cur_shape).area * 1e10
                    union = ref_shape.union(cur_shape).area * 1e10
                    iou = intersection / union if union > 0 else 0
                    area_diff_pct = ((cur_area - ref_area) / ref_area * 100) if ref_area > 0 else 0
                    vtype = cur_feat["properties"].get("violation_type", "COMPLIANT")

                    comparison_rows.append({
                        "Plot ID": pid,
                        "Ref Area (rel)": f"{ref_area:,.0f}",
                        "Cur Area (rel)": f"{cur_area:,.0f}",
                        "Area Change %": f"{area_diff_pct:+.1f}%",
                        "IoU": f"{iou:.3f}",
                        "Boundary Match": "✅ Good" if iou > 0.85 else ("⚠️ Deviated" if iou > 0.6 else "❌ Major"),
                        "Violation": vtype,
                    })

                    # Highlight boundary difference area
                    if iou < 0.95:
                        try:
                            sym_diff = ref_shape.symmetric_difference(cur_shape)
                            if sym_diff.geom_type == "Polygon":
                                diff_coords = list(sym_diff.exterior.coords)
                                diff_latlng = [(c[1], c[0]) for c in diff_coords]
                                folium.Polygon(
                                    locations=diff_latlng,
                                    color="#ff1744",
                                    weight=1,
                                    fill=True,
                                    fill_color="#ff1744",
                                    fill_opacity=0.4,
                                    tooltip=f"⚠️ {pid} — Boundary Difference",
                                ).add_to(diff_group)
                            elif sym_diff.geom_type == "MultiPolygon":
                                for geom in sym_diff.geoms:
                                    diff_coords = list(geom.exterior.coords)
                                    diff_latlng = [(c[1], c[0]) for c in diff_coords]
                                    folium.Polygon(
                                        locations=diff_latlng,
                                        color="#ff1744",
                                        weight=1,
                                        fill=True,
                                        fill_color="#ff1744",
                                        fill_opacity=0.4,
                                        tooltip=f"⚠️ {pid} — Boundary Difference",
                                    ).add_to(diff_group)
                        except Exception:
                            pass

                except Exception:
                    comparison_rows.append({
                        "Plot ID": pid,
                        "Ref Area (rel)": "-",
                        "Cur Area (rel)": "-",
                        "Area Change %": "-",
                        "IoU": "-",
                        "Boundary Match": "❓ Error",
                        "Violation": cur_feat["properties"].get("violation_type", "-"),
                    })

        ref_group.add_to(m_compare)
        cur_group.add_to(m_compare)
        diff_group.add_to(m_compare)
        folium.LayerControl(collapsed=False).add_to(m_compare)

        # Legend
        legend_html = """
        <div style="position:fixed; bottom:50px; left:50px; z-index:1000;
             background:rgba(0,0,0,0.85); padding:14px 18px; border-radius:10px;
             color:white; font-size:12px; box-shadow:0 2px 12px rgba(0,0,0,0.4);">
          <b>Legend</b><br>
          <span style="color:#38ef7d">━ ━</span> Allotted Boundary &nbsp;
          <span style="color:#2ecc71">■</span> Compliant &nbsp;
          <span style="color:#e74c3c">■</span> Encroachment &nbsp;
          <span style="color:#e67e22">■</span> Unauthorized &nbsp;
          <span style="color:#95a5a6">■</span> Vacant &nbsp;
          <span style="color:#f1c40f">■</span> Deviation &nbsp;
          <span style="color:#ff1744">■</span> Change Area
        </div>
        """
        m_compare.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m_compare, width=None, height=520, use_container_width=True,
                  key="compare_map")

        # ── Change Metrics Table ──
        if comparison_rows:
            st.markdown("### 📊 Per-Plot Change Metrics")
            comp_df = pd.DataFrame(comparison_rows)
            st.dataframe(comp_df, use_container_width=True, height=380)

            # Summary stats
            compliant_count = sum(1 for r in comparison_rows if r["Violation"] == "COMPLIANT")
            deviated_count = sum(1 for r in comparison_rows if "Deviated" in r["Boundary Match"] or "Major" in r["Boundary Match"])
            mc1, mc2, mc3, mc4 = st.columns(4)
            with mc1:
                st.markdown(f"""
                <div class="metric-card blue">
                    <h3>{len(comparison_rows)}</h3>
                    <p>📊 Total Plots Compared</p>
                </div>""", unsafe_allow_html=True)
            with mc2:
                st.markdown(f"""
                <div class="metric-card green">
                    <h3>{compliant_count}</h3>
                    <p>✅ Boundary Compliant</p>
                </div>""", unsafe_allow_html=True)
            with mc3:
                st.markdown(f"""
                <div class="metric-card red">
                    <h3>{deviated_count}</h3>
                    <p>⚠️ Boundary Deviated</p>
                </div>""", unsafe_allow_html=True)
            with mc4:
                encroach = sum(1 for r in comparison_rows if r["Violation"] == "ENCROACHMENT")
                st.markdown(f"""
                <div class="metric-card yellow">
                    <h3>{encroach}</h3>
                    <p>🚧 Encroachments</p>
                </div>""", unsafe_allow_html=True)
    else:
        st.info("No reference or current plot data available for comparison.")

    st.markdown("---")

    # ── Section 3: Allotment Zone Overview ──────────────────
    allotment = data.get("allotment")
    if allotment and allotment.get("features"):
        st.markdown("### 🗺️ Allotment Map — Zone Overview")
        st.caption("Official plot zones from allotment map with color-coded categories")

        # Center on allotment data
        all_lons, all_lats = [], []
        for feat in allotment["features"]:
            geom_type = feat["geometry"]["type"]
            if geom_type == "Polygon":
                for coord in feat["geometry"]["coordinates"][0]:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])
            elif geom_type == "LineString":
                for coord in feat["geometry"]["coordinates"]:
                    all_lons.append(coord[0])
                    all_lats.append(coord[1])
        center_lat = np.mean(all_lats) if all_lats else 20.877
        center_lon = np.mean(all_lons) if all_lons else 81.655

        m_allot = folium.Map(location=[center_lat, center_lon], zoom_start=16,
                             tiles="CartoDB positron")

        zone_colors = {
            "TILDA": "#3498db",
            "EXPANSION": "#9b59b6",
            "GREEN_AREA": "#27ae60",
            "PARKING": "#7f8c8d",
            "WAREHOUSE": "#e67e22",
            "WATER_BODY": "#00bcd4",
            "FOOD_PARK": "#f39c12",
            "AMENITIES": "#1abc9c",
            "ROAD": "#95a5a6",
            "BOUNDARY": "#e74c3c",
        }

        for feat in allotment["features"]:
            props = feat["properties"]
            zone = props.get("zone", "")
            color = zone_colors.get(zone, "#3498db")
            geom_type = feat["geometry"]["type"]

            if geom_type == "Polygon":
                coords = feat["geometry"]["coordinates"][0]
                latlng = [(c[1], c[0]) for c in coords]
                is_boundary = zone == "BOUNDARY"

                tooltip_text = (
                    f"<b>{props.get('plot_number', '')}</b><br>"
                    f"Zone: {zone}<br>"
                    f"Type: {props.get('industry_type', 'N/A')}<br>"
                    f"Area: {props.get('area_sqm', 0):,} m²<br>"
                    f"Status: {props.get('status', 'N/A')}"
                )
                folium.Polygon(
                    locations=latlng,
                    color=color,
                    weight=4 if is_boundary else 2,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.05 if is_boundary else 0.3,
                    dash_array="10 5" if is_boundary else None,
                    tooltip=folium.Tooltip(tooltip_text),
                ).add_to(m_allot)

            elif geom_type == "LineString":
                coords = feat["geometry"]["coordinates"]
                latlng = [(c[1], c[0]) for c in coords]
                folium.PolyLine(
                    locations=latlng,
                    color=color,
                    weight=4,
                    tooltip=f"🛣️ {props.get('plot_number', '')} — Road",
                ).add_to(m_allot)

        folium.LayerControl().add_to(m_allot)

        # Zone legend
        zone_legend = '<div style="position:fixed; bottom:50px; right:50px; z-index:1000; '
        zone_legend += 'background:rgba(255,255,255,0.95); padding:14px 18px; border-radius:10px; '
        zone_legend += 'color:#333; font-size:12px; box-shadow:0 2px 12px rgba(0,0,0,0.2);">'
        zone_legend += '<b>Zone Legend</b><br>'
        for zone, color in zone_colors.items():
            zone_legend += f'<span style="color:{color}">■</span> {zone.replace("_", " ").title()} &nbsp;'
        zone_legend += '</div>'
        m_allot.get_root().html.add_child(folium.Element(zone_legend))

        st_folium(m_allot, width=None, height=480, use_container_width=True,
                  key="allotment_map")

        # Allotment summary
        allot_df_rows = []
        for feat in allotment["features"]:
            p = feat["properties"]
            if p.get("zone") not in ("ROAD", "BOUNDARY"):
                allot_df_rows.append({
                    "Plot": p.get("plot_number", ""),
                    "Zone": p.get("zone", ""),
                    "Type": p.get("industry_type", ""),
                    "Area (m²)": p.get("area_sqm", 0),
                    "Status": p.get("status", ""),
                    "Allotment Date": p.get("allotment_date", "N/A"),
                    "Construction": "✅" if p.get("construction_allowed", True) else "❌",
                })
        if allot_df_rows:
            st.markdown("#### 📋 Allotment Details")
            st.dataframe(pd.DataFrame(allot_df_rows), use_container_width=True)
    else:
        st.info("No allotment map data available (`data/allotment_map.geojson`).")


# ──────────────────────────────────────────────
#  Main App
# ──────────────────────────────────────────────
def main():
    # Check if data exists
    if not os.path.exists(os.path.join(DATA_DIR, "violations.geojson")):
        render_header()
        st.warning("⚠️ No data found. Please run the data pipeline first:")
        st.code(
            "python generate_sample_data.py\n"
            "python detect_violations.py",
            language="bash",
        )
        if st.button("🚀 Generate Sample Data & Run Analysis"):
            with st.spinner("Generating sample data..."):
                import generate_sample_data
                generate_sample_data.generate()
            with st.spinner("Running violation detection..."):
                import detect_violations
                detect_violations.run()
            st.success("✅ Data generated! Reloading...")
            st.rerun()
        return

    data = load_data()
    df = data_to_df(data)

    # Sidebar filters
    filtered_df = render_sidebar(df)

    # Main content
    render_header()
    render_metrics(data, df)

    st.markdown("---")

    # Tabs for organised content
    tab_map, tab_plotcmp, tab_compare, tab_sat, tab_analysis, tab_table, tab_charts, tab_export = st.tabs(
        ["🗺️ Map", "🔍 Plot Comparison", "🖼️ Compare", "🛰️ Satellite", "🔬 Plot Analysis",
         "📋 Table", "📊 Charts", "📥 Export"]
    )

    with tab_map:
        render_map(data)

    with tab_plotcmp:
        render_plot_comparison_tab(data)

    with tab_compare:
        render_image_comparison(data)

    with tab_sat:
        render_satellite_tab(data)

    with tab_analysis:
        from satellite_compare import render_satellite_compare
        render_satellite_compare()

    with tab_table:
        render_table(filtered_df)

    with tab_charts:
        render_charts(filtered_df, data)

    with tab_export:
        render_downloads(filtered_df, data)


if __name__ == "__main__":
    main()
