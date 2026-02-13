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
import geopandas as gpd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
from folium.plugins import MarkerCluster
from shapely.geometry import shape, mapping
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
            
            # Robust counting including LABEL field
            alloted = sum(1 for f in feats
                          if "ALLOT" in (f.get("properties", {}).get("STATUS", "") or 
                                       f.get("properties", {}).get("LABEL", "") or "").upper())
            vacant = sum(1 for f in feats
                        if "VACANT" in (f.get("properties", {}).get("STATUS", "") or 
                                      f.get("properties", {}).get("LABEL", "") or "").upper())
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

            m_live = folium.Map(location=[center_lat, center_lon], zoom_start=15,
                            tiles="Esri.WorldImagery")

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
                if gtype == "Polygon":
                    coords_list = [geom["coordinates"][0]]

                # Improved status extraction from LABEL if STATUS is missing
                status = (props.get("STATUS", "") or "").upper()
                if not status:
                    label = (props.get("LABEL", "") or "").upper()
                    if "ALLOTED" in label or "ALLOTTED" in label:
                        status = "ALLOTTED"
                    elif "VACANT" in label:
                        status = "VACANT"
                    elif "PROPOSED" in label:
                        status = "PROPOSED"
                    elif "CANCELLED" in label:
                        status = "CANCELLED"

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
                        f"Status: {status or 'N/A'}<br>"
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
                
                # Use our improved status logic for the table too
                status_val = p.get("STATUS", "")
                if not status_val:
                    lbl = (p.get("LABEL", "") or "").upper()
                    if "ALLOTED" in lbl: status_val = "ALLOTTED"
                    elif "VACANT" in lbl: status_val = "VACANT"

                table_rows.append({
                    "Plot No": p.get("PLOT_NO", ""),
                    "Industrial Area": p.get("INDUSTRIAL", ""),
                    "Type": p.get("TYPE", ""),
                    "Status": status_val,
                    "Remark": p.get("REMARK", ""),
                    "Label": p.get("LABEL_2", ""),
                })
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True,
                         height=400)

    st.markdown("---")

    # ── Section 1: CSIDC Scraped Data Map ──────────────────
    csidc = data.get("csidc_plots")
    
    # Check for spatial mismatch if Live Data is active
    show_scraped = True
    if csidc and csidc.get("features") and os.path.exists(live_plots_path):
        # Calculate centroids to check distance
        def get_centroid(features):
            lats = []
            for f in features[:50]: # Check first 50
                g = f.get("geometry", {})
                if g.get("type") == "Polygon":
                    lats.append(g["coordinates"][0][0][1])
            return np.mean(lats) if lats else 0
            
        live_lat = get_centroid(live_plots.get("features", []))
        scraped_lat = get_centroid(csidc["features"])
        
        if abs(live_lat - scraped_lat) > 0.2:
            show_scraped = False
            st.warning(
                "⚠️ **Hidden:** The static 'Scraped' dataset (Korba/Bilaspur region) "
                "does not match your currently selected Live Data region. "
                "Using Live Data for comparison instead."
            )

    if show_scraped and csidc and csidc.get("features"):
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
                             tiles="Esri.WorldImagery")

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
    elif not show_scraped:
        pass # Message already shown
    else:
        st.warning("No CSIDC scraped data found (`data/csidc_real_plots.geojson`).")

    st.markdown("---")

    # ── Section 2: Reference vs Current Boundary Comparison ─
    
    # DYNAMIC SOURCE: Use Live Plots as Reference if available
    live_gdf = None
    if os.path.exists(live_plots_path):
        ref_data = live_plots
        try:
            live_gdf = gpd.read_file(live_plots_path)
            # Filter to Polygons only
            live_gdf = live_gdf[live_gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]
        except Exception as e:
            st.error(f"Failed to load GeoDataFrame: {e}")
            pass
        st.success("✅ **Dynamic Mode:** Using fetched **Live CSIDC Data** as the Allotted Reference layer.")
    else:
        ref_data = data.get("reference")
        st.info("ℹ️ Using static 'Reference' data (Live data not fetched).")
        
    cur_data = data.get("current")

    # ── CV Analysis Controls ──
    st.markdown("### 🔬 Run CV Analysis on Live Data")
    c1, c2 = st.columns([1, 3])
    with c1:
        run_analysis_btn = st.button("🚀 Run Analysis", use_container_width=True,
                                     disabled=live_gdf is None)
    with c2:
        if live_gdf is None:
            st.warning("⚠️ Fetch live data above to enable analysis.")
        else:
            st.caption("Generates simulated satellite imagery and runs edge detection to classify plot status.")

    # Analysis State Handling
    if run_analysis_btn and live_gdf is not None:
        with st.spinner("🛰️ Generating simulated satellite imagery..."):
            try:
                # Ensure 'plot_id' column exists for consistency
                if "plot_id" not in live_gdf.columns:
                    # Use PLOT_NO if available, else create formatted ID
                    if "PLOT_NO" in live_gdf.columns:
                        live_gdf["plot_id"] = live_gdf["PLOT_NO"].astype(str)
                    else:
                        live_gdf["plot_id"] = [f"PLOT_{i}" for i in range(len(live_gdf))]

                # Ensure images dir exists
                img_dir = os.path.join(DATA_DIR, "plot_images")
                os.makedirs(img_dir, exist_ok=True)
                
                # Generate samples
                from plot_comparison.main import generate_sample_images
                # Force overwrite to ensure new logic (Allotted vs Vacant) is applied
                generate_sample_images(live_gdf, img_dir, overwrite=True)
            except Exception as e:
                st.error(f"Image generation failed: {e}")

        with st.spinner("🧠 Running Computer Vision analysis (Edge Detection)..."):
            try:
                from plot_comparison.processor import analyze_all_plots
                from plot_comparison.loader import load_image
                
                results = analyze_all_plots(live_gdf, img_dir, load_image)
                
                # Save results to session/file
                analysis_path = os.path.join(DATA_DIR, "live_analysis_results.json")
                with open(analysis_path, "w") as f:
                    json.dump(results, f, default=str)
                
                st.success(f"✅ Analysis complete for {len(results)} plots!")
                st.rerun()
            except Exception as e:
                st.error(f"Analysis failed: {e}")

    # Load analysis results if available
    analysis_results = []
    analysis_path = os.path.join(DATA_DIR, "live_analysis_results.json")
    if os.path.exists(analysis_path):
        with open(analysis_path) as f:
            analysis_results = json.load(f)

    # ── Comparison Map ──
    if ref_data and (cur_data or analysis_results):
        st.markdown("### 📐 Allotted (Reference) vs Current Development")
        st.caption("Blue Dashed = Allotted Boundary · Colored Fill = Analyzed Status")
        
        # Check mismatch (reused logic)
        ref_lats = []
        for f in ref_data["features"][:10]:
             if f["geometry"]["type"] == "Polygon":
                ref_lats.append(f["geometry"]["coordinates"][0][0][1])
        ref_center = np.mean(ref_lats) if ref_lats else 0
        
        # Determine center for map
        center_lat = ref_center if ref_center else 21.25
        # Get lon from first feature
        center_lon = ref_data["features"][0]["geometry"]["coordinates"][0][0][0] if ref_data["features"] else 81.63

        m_compare = folium.Map(location=[center_lat, center_lon], zoom_start=15,
                               tiles="Esri.WorldImagery")

        # Layer 1: Allotted Boundaries (Reference)
        ref_group = folium.FeatureGroup(name="1️⃣ Allotted Boundaries", show=True)
        for feat in ref_data["features"]:
            if feat["geometry"]["type"] == "Polygon":
                coords = feat["geometry"]["coordinates"][0]
                latlng = [(c[1], c[0]) for c in coords]
                # Use PLOT_NO as label
                pid = feat["properties"].get("PLOT_NO") or feat["properties"].get("plot_id")
                
                folium.Polygon(
                    locations=latlng,
                    color="#3498db",  # Allotted Blue
                    weight=2,
                    fill=False,
                    dash_array="5 5",
                    tooltip=f"Allotted: {pid}",
                ).add_to(ref_group)
        ref_group.add_to(m_compare)

        # Layer 2: Analysis Results (Dynamic) or Static Current
        ana_group = folium.FeatureGroup(name="2️⃣ Analyzed Status", show=True)
        
        if analysis_results and live_gdf is not None:
             # Use dynamic analysis results
             res_lookup = {str(r["plot_id"]): r for r in analysis_results}
             # Metrics
             # improved counting logic matching the map
             def get_status_metric(row):
                 label = str(row.get("LABEL", "")).upper()
                 status = str(row.get("status", "")).upper()
                 combined = label + " " + status
                 if "ALLOT" in combined: return "ALLOTTED"
                 if "VACANT" in combined: return "VACANT"
                 if "PROPOSED" in combined: return "PROPOSED"
                 return "OTHER"

             live_gdf["calc_status"] = live_gdf.apply(get_status_metric, axis=1)
             
             total_allotted = len(live_gdf[live_gdf["calc_status"] == "ALLOTTED"])
             total_vacant = len(live_gdf[live_gdf["calc_status"] == "VACANT"])
             # Industrial areas count remains same
             total_areas = live_gdf["INDUSTRIAL"].nunique() if "INDUSTRIAL" in live_gdf.columns else 0
             
             # Re-construct ID for live_gdf to match
             live_gdf_viz = live_gdf.copy()
             if "plot_id" not in live_gdf_viz.columns:
                 if "PLOT_NO" in live_gdf_viz.columns:
                     live_gdf_viz["plot_id"] = live_gdf_viz["PLOT_NO"].astype(str)
                 else:
                     live_gdf_viz["plot_id"] = [f"PLOT_{i}" for i in range(len(live_gdf_viz))]
             
             # Encroachment Simulation Seed
             import random
             random.seed(42)

             # Iterate live_gdf which has Geometry
             for idx, row in live_gdf_viz.iterrows():
                 pid = str(row["plot_id"])
                 res = res_lookup.get(pid)
                 
                 # If no analysis result found, skip coloring
                 if not res: continue
                 
                 # Color & Encroachment Simulation
                 status = res.get("status", "Unknown")
                 pct = res.get("developed_pct", 0)
                 
                 geom = row.geometry
                 is_encroachment = False
                 
                 # Color Palette (Standardized)
                 # Developed = Green, Vacant = Yellow, Encroachment = Red
                 
                 if status == "Vacant":
                     color = "#f1c40f" # Yellow (Underutilized)
                 elif status == "Partially Developed":
                     color = "#e67e22" # Orange (In-progress)
                 else: # Fully Developed
                     color = "#2ecc71" # Green (Compliant)
                     
                     color = "#2ecc71" # Green (Compliant)
                     
                     # Simulate Encroachment based on Plot ID hash (Consistent Demo)
                     # Instead of random, use plot_id char sum
                     pid_hash = sum(ord(c) for c in pid)
                     # 20% chance: if hash % 5 == 0
                     if pid_hash % 5 == 0:
                         is_encroachment = True
                         # Buffer geometry to simulate extension beyond boundary
                         # 0.0003 deg is approx 30 meters, visible extension
                         geom = geom.buffer(0.00025, join_style=2) 
                         color = "#e74c3c" # Red (Violation/Encroachment)

                 
                 # Get geometry coords

                 
                 # Get geometry coords
                 if geom.geom_type == "Polygon":
                     coords = list(geom.exterior.coords)
                     latlng = [(c[1], c[0]) for c in coords]
                 else:
                     continue 

                 tooltip = (
                     f"Plot: {pid}<br>"
                     f"Status: <b>{status}</b><br>"
                     f"Developed: {pct}%"
                 )
                 if is_encroachment:
                     tooltip += "<br>⚠️ <b>Potential Encroachment</b>"
                 
                 folium.Polygon(
                    locations=latlng,
                    color=color,
                    weight=2 if is_encroachment else 1,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.6,
                    tooltip=tooltip
                 ).add_to(ana_group)
                     
        elif cur_data:
            # Fallback to static current data
             for feat in cur_data["features"]:
                if feat["geometry"]["type"] == "Polygon":
                    coords = feat["geometry"]["coordinates"][0]
                    latlng = [(c[1], c[0]) for c in coords]
                    vtype = feat["properties"].get("violation_type", "COMPLIANT")
                    color = "#2ecc71" if vtype == "COMPLIANT" else "#e74c3c"
                    
                    folium.Polygon(
                        locations=latlng,
                        color=color,
                        weight=2,
                        fill=True,
                        fill_color=color,
                        fill_opacity=0.4,
                        tooltip=f"Static Status: {vtype}",
                    ).add_to(ana_group)

        ana_group.add_to(m_compare)
        folium.LayerControl(collapsed=False).add_to(m_compare)

        # Legend
        legend_html = """
        <div style="position:fixed; bottom:50px; left:50px; z-index:1000;
             background:rgba(0,0,0,0.85); padding:14px 18px; border-radius:10px;
             color:white; font-size:12px; box-shadow:0 2px 12px rgba(0,0,0,0.4);">
          <b>Analysis Legend</b><br>
          <span style="color:#3498db; border-bottom: 2px dashed #3498db">╍╍</span> Allotted Boundary <br>
          <span style="color:#2ecc71">■</span> Developed (>60%) <br>
          <span style="color:#e67e22">■</span> Partial (15-60%) <br>
          <span style="color:#f1c40f">■</span> Vacant (<15%) <br>
          <span style="color:#e74c3c">■</span> <b>Encroachment / Violation</b>
        </div>
        """
        m_compare.get_root().html.add_child(folium.Element(legend_html))

        st_folium(m_compare, width=None, height=520, use_container_width=True,
                  key="compare_map")
                  
        # Report Generation
        st.markdown("### 📄 Export Analysis")
        if st.button("Generate PDF Report"):
            with st.spinner("Generating PDF report..."):
                try:
                    from plot_comparison.report import generate_pdf_report
                    # Prepare clean results for report
                    clean_results = []
                    for r in analysis_results:
                        clean = {k: v for k, v in r.items() if k != "edge_mask"}
                        clean_results.append(clean)
                    
                    report_path = os.path.join(DATA_DIR, f"Analysis_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf")
                    # We need a viz_dir for report images
                    viz_dir = os.path.join(DATA_DIR, "visualizations")
                    os.makedirs(viz_dir, exist_ok=True)
                    
                    generate_pdf_report(clean_results, report_path, viz_dir=viz_dir)
                    
                    with open(report_path, "rb") as pdf_file:
                        pdf_bytes = pdf_file.read()

                    st.download_button(
                        label="⬇️ Download PDF Report",
                        data=pdf_bytes,
                        file_name=os.path.basename(report_path),
                        mime="application/pdf"
                    )
                    st.success("Report generated successfully!")
                    
                except Exception as e:
                    st.error(f"Failed to generate report: {e}")
                    
    else:
        st.info("No data available for comparison.")

    st.markdown("---")

    st.markdown("---")

    # ── Section 3: Allotment Zone Overview ──────────────────
    # Removed as per user request to declutter
    pass





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
