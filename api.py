"""
LandGuard AI — Flask REST API
Serves data and runs analysis for the React frontend.
"""

import json
import os
import io
import sys
import base64
import traceback
from datetime import datetime

import numpy as np
import cv2
import geopandas as gpd
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS
from shapely.geometry import shape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "build")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# ────────────────────────────────────────────
#  Helpers
# ────────────────────────────────────────────

def _load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _image_to_base64(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


# ────────────────────────────────────────────
#  DATA ENDPOINTS
# ────────────────────────────────────────────

@app.route("/api/data/summary")
def get_summary():
    """Return violation summary + high-level metrics."""
    summary = _load_json("violation_summary.json") or {}
    metadata = _load_json("plot_metadata.json") or []
    total_plots = summary.get("total_plots", len(metadata))
    manual_cost = total_plots * 25000
    savings = manual_cost - 50000

    return jsonify({
        "total_plots": total_plots,
        "total_violations": summary.get("total_violations", 0),
        "compliant": summary.get("compliant", 0),
        "critical": summary.get("severity_breakdown", {}).get("CRITICAL", 0),
        "severity_breakdown": summary.get("severity_breakdown", {}),
        "type_breakdown": summary.get("type_breakdown", {}),
        "total_estimated_cost_inr": summary.get("total_estimated_cost_inr", 0),
        "estimated_savings": savings,
        "satellite_data_available": summary.get("satellite_data_available", False),
        "generated_at": summary.get("generated_at", ""),
    })


@app.route("/api/data/violations")
def get_violations():
    """Return violations GeoJSON."""
    data = _load_json("violations.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/reference")
def get_reference():
    """Return reference plots GeoJSON."""
    data = _load_json("reference_plots.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/current")
def get_current():
    """Return current plots GeoJSON."""
    data = _load_json("current_plots.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/metadata")
def get_metadata():
    """Return plot metadata."""
    data = _load_json("plot_metadata.json")
    return jsonify(data or [])


@app.route("/api/data/satellite-changes")
def get_satellite_changes():
    """Return satellite change detection GeoJSON."""
    data = _load_json("satellite_changes.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/csidc-plots")
def get_csidc_plots():
    """Return CSIDC scraped plots GeoJSON."""
    data = _load_json("csidc_real_plots.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/live-plots")
def get_live_plots():
    """Return live CSIDC fetched plots."""
    data = _load_json("csidc_live_plots.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/live-boundaries")
def get_live_boundaries():
    """Return live CSIDC fetched boundaries."""
    data = _load_json("csidc_live_boundaries.geojson")
    return jsonify(data or {"type": "FeatureCollection", "features": []})


@app.route("/api/data/analysis-results")
def get_analysis_results():
    """Return CV analysis results from last run."""
    data = _load_json("live_analysis_results.json")
    return jsonify(data or [])


# ────────────────────────────────────────────
#  IMAGE ENDPOINTS
# ────────────────────────────────────────────

@app.route("/api/images/<plot_id>/<image_type>")
def get_plot_image(plot_id, image_type):
    """Serve plot images (reference or current)."""
    images_dir = os.path.join(DATA_DIR, "images")
    for ext in [".jpg", ".jpeg", ".png", ".tif"]:
        fname = f"{plot_id}_{image_type}{ext}"
        path = os.path.join(images_dir, fname)
        if os.path.exists(path):
            return send_file(path)
    return jsonify({"error": "Image not found"}), 404


@app.route("/api/images/change-masks")
def get_change_masks():
    """List available change mask images."""
    mask_dir = os.path.join(DATA_DIR, "satellite", "change_masks")
    if not os.path.exists(mask_dir):
        return jsonify([])
    masks = [f for f in os.listdir(mask_dir) if f.endswith((".png", ".jpg"))]
    return jsonify(masks)


@app.route("/api/images/change-mask/<filename>")
def get_change_mask(filename):
    mask_dir = os.path.join(DATA_DIR, "satellite", "change_masks")
    return send_from_directory(mask_dir, filename)


# ────────────────────────────────────────────
#  PLOT COMPARISON / ANALYSIS ENDPOINTS
# ────────────────────────────────────────────

@app.route("/api/analysis/run", methods=["POST"])
def run_analysis():
    """Run CV analysis on live data (or reference plots)."""
    try:
        # Determine source
        live_path = os.path.join(DATA_DIR, "csidc_live_plots.geojson")
        ref_path = os.path.join(DATA_DIR, "reference_plots.geojson")
        src = live_path if os.path.exists(live_path) else ref_path

        gdf = gpd.read_file(src)
        gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])]

        if "plot_id" not in gdf.columns:
            if "PLOT_NO" in gdf.columns:
                gdf["plot_id"] = gdf["PLOT_NO"].astype(str)
            else:
                gdf["plot_id"] = [f"PLOT_{i}" for i in range(len(gdf))]

        img_dir = os.path.join(DATA_DIR, "plot_images")
        os.makedirs(img_dir, exist_ok=True)

        # Generate sample images
        from plot_comparison.main import generate_sample_images
        generate_sample_images(gdf, img_dir, overwrite=True)

        # Run analysis
        from plot_comparison.processor import analyze_all_plots
        from plot_comparison.loader import load_image

        results = analyze_all_plots(gdf, img_dir, load_image)

        # Clean results (remove numpy arrays)
        clean = []
        for r in results:
            c = {k: v for k, v in r.items() if k != "edge_mask"}
            # Convert numpy types
            for key in c:
                if isinstance(c[key], (np.integer,)):
                    c[key] = int(c[key])
                elif isinstance(c[key], (np.floating,)):
                    c[key] = float(c[key])
                elif isinstance(c[key], np.bool_):
                    c[key] = bool(c[key])
            clean.append(c)

        # Save results
        analysis_path = os.path.join(DATA_DIR, "live_analysis_results.json")
        with open(analysis_path, "w") as f:
            json.dump(clean, f, default=str)

        return jsonify({"status": "ok", "results": clean, "count": len(clean)})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/analysis/generate-report", methods=["POST"])
def generate_report():
    """Generate PDF report from latest analysis, including map images."""
    try:
        analysis_path = os.path.join(DATA_DIR, "live_analysis_results.json")
        if not os.path.exists(analysis_path):
            return jsonify({"error": "Run analysis first"}), 400

        with open(analysis_path) as f:
            results = json.load(f)

        # Decode map images from request body (base64 PNGs from html2canvas)
        body = request.json or {}
        map_images = []
        maps_dir = os.path.join(DATA_DIR, "report_maps")
        os.makedirs(maps_dir, exist_ok=True)

        for key, title in [
            ("original_map", "Original CSIDC Plot Data"),
            ("comparison_map", "Allotted (Reference) vs Current Development"),
        ]:
            img_b64 = body.get(key)
            if img_b64:
                try:
                    img_bytes = base64.b64decode(img_b64)
                    img_path = os.path.join(maps_dir, f"{key}.png")
                    with open(img_path, "wb") as f:
                        f.write(img_bytes)
                    map_images.append({"title": title, "path": img_path})
                except Exception as img_err:
                    print(f"[Report] Warning: Could not decode {key}: {img_err}")

        from plot_comparison.report import generate_pdf_report
        report_name = f"Analysis_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        report_path = os.path.join(DATA_DIR, report_name)
        viz_dir = os.path.join(DATA_DIR, "visualizations")
        os.makedirs(viz_dir, exist_ok=True)

        generate_pdf_report(results, report_path, viz_dir=viz_dir, map_images=map_images)

        return send_file(report_path, as_attachment=True, download_name=report_name)

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/api/analysis/compliance-report", methods=["POST"])
def generate_compliance_report():
    """Generate compliance PDF report from violation data."""
    try:
        from generate_report import generate_pdf
        path = generate_pdf()
        return send_file(path, as_attachment=True, download_name="compliance_report.pdf")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────
#  CSIDC LIVE FETCH
# ────────────────────────────────────────────

@app.route("/api/csidc/areas")
def list_csidc_areas():
    """List industrial areas from CSIDC GeoServer."""
    try:
        from fetch_csidc_live import list_industrial_areas
        areas = list_industrial_areas()
        return jsonify({"areas": areas})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/csidc/fetch", methods=["POST"])
def fetch_csidc():
    """Fetch live plots from CSIDC GeoServer."""
    try:
        body = request.json or {}
        area = body.get("area")
        max_plots = body.get("max_plots", 500)

        from fetch_csidc_live import fetch_and_save
        plots_path, bounds_path, n_plots, n_bounds = fetch_and_save(
            industrial_area=area or None,
        )

        return jsonify({
            "status": "ok",
            "plots_count": n_plots,
            "boundaries_count": n_bounds,
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────
#  EXPORT ENDPOINTS
# ────────────────────────────────────────────

@app.route("/api/export/csv")
def export_csv():
    """Export violations as CSV."""
    import pandas as pd
    data = _load_json("violations.geojson")
    if not data or not data.get("features"):
        return jsonify({"error": "No data"}), 404

    rows = []
    for feat in data["features"]:
        p = feat["properties"]
        rows.append({
            "Plot ID": p.get("plot_id", ""),
            "Violation Type": p.get("primary_violation", ""),
            "Severity": p.get("severity", ""),
            "Area Ref (sqm)": p.get("area_ref_sqm", 0),
            "Area Cur (sqm)": p.get("area_cur_sqm", 0),
            "Area Diff (%)": p.get("area_diff_pct", 0),
            "Overlap (%)": p.get("overlap_pct", 0),
            "IoU": p.get("iou", 0),
            "Detection Date": p.get("detection_date", ""),
            "Action Required": p.get("action_required", ""),
            "Est. Cost (INR)": p.get("estimated_cost_inr", 0),
        })

    df = pd.DataFrame(rows)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)
    return send_file(buffer, mimetype="text/csv", as_attachment=True,
                     download_name="landguard_violations.csv")


@app.route("/api/export/geojson")
def export_geojson():
    vio_path = os.path.join(DATA_DIR, "violations.geojson")
    if os.path.exists(vio_path):
        return send_file(vio_path, as_attachment=True, download_name="violations.geojson")
    return jsonify({"error": "No data"}), 404


# ────────────────────────────────────────────
#  PIPELINE ACTIONS
# ────────────────────────────────────────────

@app.route("/api/pipeline/generate-data", methods=["POST"])
def pipeline_generate():
    """Generate sample data and run violation detection."""
    try:
        import generate_sample_data
        generate_sample_data.generate()

        import detect_violations
        detect_violations.run()

        return jsonify({"status": "ok", "message": "Data generated and violations detected."})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ────────────────────────────────────────────
#  Serve React Frontend
# ────────────────────────────────────────────

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    if path and os.path.exists(os.path.join(FRONTEND_DIR, path)):
        return send_from_directory(FRONTEND_DIR, path)
    if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({"message": "LandGuard AI API running. Build React frontend to serve UI."}), 200


if __name__ == "__main__":
    print("=" * 50)
    print("  LandGuard AI — API Server")
    print("  http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, host="0.0.0.0", port=5000)
