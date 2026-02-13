"""
satellite_compare.py - Streamlit page for real-time satellite plot comparison.

Flow:
  1. Upload GeoJSON with plot polygons
  2. Show plots on interactive satellite map
  3. Fetch live satellite imagery (GEE Sentinel-2 or tile-based)
  4. Run CV-based change detection per plot
  5. Show results in real-time
  6. Generate and download PDF report
"""

import json
import os
import io
import tempfile
from datetime import datetime, timedelta

import streamlit as st
import pandas as pd
import numpy as np
import cv2
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import shape

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")


# ──────────────────────────────────────────────
#  Utility Functions
# ──────────────────────────────────────────────

def parse_geojson(uploaded_file):
    """Parse uploaded GeoJSON file and return GeoDataFrame."""
    content = uploaded_file.read().decode("utf-8")
    geojson_data = json.loads(content)
    uploaded_file.seek(0)  # Reset for re-reads

    gdf = gpd.GeoDataFrame.from_features(geojson_data["features"], crs="EPSG:4326")

    # Filter only Polygon/MultiPolygon features
    polygon_mask = gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
    gdf = gdf[polygon_mask].copy()

    return gdf, geojson_data


def get_bounds_center(gdf):
    """Get center and bounds of all geometries."""
    bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    return center_lat, center_lon, bounds


def fetch_satellite_thumbnail_gee(geojson_data, plot_feature, output_dir):
    """
    Try to fetch satellite thumbnail from Google Earth Engine.
    Returns path to downloaded image or None.
    """
    try:
        import ee

        # Try to initialize GEE
        try:
            ee.Initialize(project='landguard-ai')
        except Exception:
            try:
                ee.Authenticate()
                ee.Initialize(project='landguard-ai')
            except Exception:
                return None

        geom = ee.Geometry(plot_feature["geometry"])
        pid = plot_feature["properties"].get("plot_id", "unknown")

        # Fetch recent Sentinel-2 imagery
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")

        s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
              .filterBounds(geom)
              .filterDate(start_date, end_date)
              .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
              .select(["B4", "B3", "B2"])
              .median()
              .clip(geom))

        # Get thumbnail URL
        url = s2.getThumbURL({
            "min": 0,
            "max": 3000,
            "dimensions": 512,
            "format": "png",
        })

        # Download
        import urllib.request
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{pid}_satellite.png")
        urllib.request.urlretrieve(url, out_path)
        return out_path

    except Exception as e:
        return None


def _lonlat_to_tile(lon, lat, zoom):
    """Convert lon/lat to tile x/y at given zoom level."""
    import math
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.log(math.tan(lat_rad) +
              1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def _tile_to_lonlat(x, y, zoom):
    """Convert tile x/y to the lon/lat of the tile's NW corner."""
    import math
    n = 2 ** zoom
    lon = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat = math.degrees(lat_rad)
    return lon, lat


def generate_satellite_tile_image(plot_feature, output_dir):
    """
    Fetch satellite tiles that cover the plot's bounding box, stitch them,
    and crop to the exact geographic extent of the plot coordinates.
    Falls back to a placeholder if tiles cannot be fetched.
    """
    pid = plot_feature["properties"].get("plot_id", "unknown")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{pid}_satellite.png")

    if os.path.exists(out_path):
        return out_path

    try:
        import urllib.request

        coords = plot_feature["geometry"]["coordinates"][0]
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]

        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)

        # Add ~10% padding around the bbox
        lon_pad = max((max_lon - min_lon) * 0.15, 0.0003)
        lat_pad = max((max_lat - min_lat) * 0.15, 0.0003)
        min_lon -= lon_pad
        max_lon += lon_pad
        min_lat -= lat_pad
        max_lat += lat_pad

        # Use zoom 18 for high detail
        zoom = 18
        x_min, y_max_tile = _lonlat_to_tile(min_lon, min_lat, zoom)
        x_max, y_min_tile = _lonlat_to_tile(max_lon, max_lat, zoom)

        # Ensure at least a 2×2 tile grid for small plots
        if x_max <= x_min:
            x_max = x_min + 1
        if y_max_tile <= y_min_tile:
            y_max_tile = y_min_tile + 1

        # Cap to max 4×4 tiles (prevent huge downloads)
        x_max = min(x_max, x_min + 3)
        y_max_tile = min(y_max_tile, y_min_tile + 3)

        tile_size = 256
        n_x = x_max - x_min + 1
        n_y = y_max_tile - y_min_tile + 1

        # Stitch tiles
        stitched = np.zeros((n_y * tile_size, n_x * tile_size, 3), dtype=np.uint8)

        for ty in range(y_min_tile, y_max_tile + 1):
            for tx in range(x_min, x_max + 1):
                tile_url = (
                    f"https://server.arcgisonline.com/ArcGIS/rest/services/"
                    f"World_Imagery/MapServer/tile/{zoom}/{ty}/{tx}"
                )
                try:
                    tmp_path = os.path.join(output_dir, f"_tile_{zoom}_{ty}_{tx}.jpg")
                    if not os.path.exists(tmp_path):
                        urllib.request.urlretrieve(tile_url, tmp_path)
                    tile_img = cv2.imread(tmp_path)
                    if tile_img is not None:
                        row = (ty - y_min_tile) * tile_size
                        col = (tx - x_min) * tile_size
                        h, w = tile_img.shape[:2]
                        stitched[row:row+h, col:col+w] = tile_img
                except Exception:
                    pass

        # Crop stitched image to the exact plot bounding box
        # Convert bbox corners to pixel coordinates in the stitched image
        nw_lon, nw_lat = _tile_to_lonlat(x_min, y_min_tile, zoom)
        se_lon, se_lat = _tile_to_lonlat(x_max + 1, y_max_tile + 1, zoom)

        total_h, total_w = stitched.shape[:2]
        px_min_lon = int((min_lon - nw_lon) / (se_lon - nw_lon) * total_w)
        px_max_lon = int((max_lon - nw_lon) / (se_lon - nw_lon) * total_w)
        px_min_lat = int((nw_lat - max_lat) / (nw_lat - se_lat) * total_h)
        px_max_lat = int((nw_lat - min_lat) / (nw_lat - se_lat) * total_h)

        # Clamp
        px_min_lon = max(0, min(px_min_lon, total_w - 1))
        px_max_lon = max(px_min_lon + 1, min(px_max_lon, total_w))
        px_min_lat = max(0, min(px_min_lat, total_h - 1))
        px_max_lat = max(px_min_lat + 1, min(px_max_lat, total_h))

        cropped = stitched[px_min_lat:px_max_lat, px_min_lon:px_max_lon]

        # Resize to consistent output size
        if cropped.shape[0] > 0 and cropped.shape[1] > 0:
            cropped = cv2.resize(cropped, (512, 512), interpolation=cv2.INTER_LANCZOS4)
            cv2.imwrite(out_path, cropped)
            return out_path

    except Exception:
        pass

    # Fallback: simple solid placeholder
    img = np.full((512, 512, 3), (128, 128, 128), dtype=np.uint8)
    cv2.putText(img, f"{pid}", (20, 260), cv2.FONT_HERSHEY_SIMPLEX,
                1.5, (255, 255, 255), 2)
    cv2.putText(img, "Tile fetch failed", (20, 310), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (200, 200, 200), 1)
    cv2.imwrite(out_path, img)
    return out_path


def analyse_color_segmentation(image):
    """
    Segment image into built-up, vegetation, bare soil, and water using
    HSV color space analysis. Returns per-class pixel percentages.
    """
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    total = image.shape[0] * image.shape[1]

    # ── Vegetation mask: green hues with moderate saturation ──
    veg_mask = cv2.inRange(hsv, (25, 30, 30), (95, 255, 230))
    veg_pct = np.count_nonzero(veg_mask) / total * 100

    # ── Built-up mask: low saturation + high value (concrete, metal roofs) ──
    gray_mask = (s < 40) & (v > 120)
    # Also catch reddish/brownish roofs and paved surfaces
    roof_mask = cv2.inRange(hsv, (0, 20, 100), (25, 180, 255))
    built_combined = gray_mask.astype(np.uint8) * 255
    built_combined = cv2.bitwise_or(built_combined, roof_mask)
    built_pct = np.count_nonzero(built_combined) / total * 100

    # ── Bare soil: brownish, low saturation, medium brightness ──
    soil_mask = cv2.inRange(hsv, (10, 30, 60), (30, 150, 200))
    # Remove vegetation overlap
    soil_mask = cv2.bitwise_and(soil_mask, cv2.bitwise_not(veg_mask))
    soil_pct = np.count_nonzero(soil_mask) / total * 100

    # ── Water: dark blue or very dark areas ──
    water_mask = cv2.inRange(hsv, (90, 30, 20), (140, 255, 180))
    water_pct = np.count_nonzero(water_mask) / total * 100

    return {
        "vegetation_pct": round(veg_pct, 2),
        "built_up_pct": round(built_pct, 2),
        "bare_soil_pct": round(soil_pct, 2),
        "water_pct": round(water_pct, 2),
        "built_mask": built_combined,
        "veg_mask": veg_mask,
    }


def compute_pseudo_ndvi(image):
    """
    Compute pseudo-NDVI from RGB channels.
    Uses (Green - Red) / (Green + Red) as an approximation.
    Values > 0.1 indicate vegetation; < -0.1 indicate built-up or bare.
    """
    b, g, r = cv2.split(image.astype(np.float32))
    denom = g + r + 1e-6  # avoid division by zero
    ndvi = (g - r) / denom
    mean_ndvi = float(np.mean(ndvi))
    # Percentage of pixels with NDVI > 0.1 (vegetated)
    veg_pixels = np.count_nonzero(ndvi > 0.1) / ndvi.size * 100
    built_pixels = np.count_nonzero(ndvi < -0.05) / ndvi.size * 100

    return {
        "mean_ndvi": round(mean_ndvi, 4),
        "vegetation_pct": round(veg_pixels, 2),
        "built_up_pct": round(built_pixels, 2),
        "ndvi_map": ndvi,
    }


def analyse_texture(image):
    """
    Measure texture complexity using Laplacian variance and local
    standard deviation. High texture = more structures; low = open land.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Laplacian variance (overall texture energy)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    lap_var = float(np.var(lap))

    # Local standard deviation in 15×15 windows
    gray_f = gray.astype(np.float64)
    mean_local = cv2.blur(gray_f, (15, 15))
    sqmean_local = cv2.blur(gray_f ** 2, (15, 15))
    local_std = np.sqrt(np.maximum(sqmean_local - mean_local ** 2, 0))
    mean_std = float(np.mean(local_std))

    # Threshold: Laplacian var > 200 or local std > 25 suggests structures
    has_structures = lap_var > 200 or mean_std > 25

    return {
        "laplacian_var": round(lap_var, 2),
        "mean_local_std": round(mean_std, 2),
        "has_structures": has_structures,
    }


def detect_structures_contours(image, min_area_ratio=0.005):
    """
    Detect rectangular building-like structures using adaptive thresholding
    and contour analysis. Returns structure count and area coverage.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    total_area = image.shape[0] * image.shape[1]
    min_area = total_area * min_area_ratio

    # Adaptive thresholding handles lighting variation
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 15, 4
    )

    # Clean up with morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    structures = []
    structure_area = 0
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        # Approximate polygon — buildings tend to be 4-sided
        epsilon = 0.03 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        # Rectangularity check: fill ratio in bounding rect
        x, y, w, h = cv2.boundingRect(cnt)
        rect_area = w * h
        fill_ratio = area / rect_area if rect_area > 0 else 0

        # Accept if reasonably rectangular (fill ratio > 0.5) or large enough
        if fill_ratio > 0.45 or area > total_area * 0.02:
            structures.append({
                "vertices": len(approx),
                "area": area,
                "fill_ratio": round(fill_ratio, 3),
            })
            structure_area += area

    coverage_pct = (structure_area / total_area) * 100

    return {
        "structure_count": len(structures),
        "coverage_pct": round(coverage_pct, 2),
        "structures": structures,
        "threshold_mask": thresh,
    }


def detect_development(image):
    """
    Multi-signal development analysis combining:
      1. Color segmentation (HSV-based built-up vs vegetation)
      2. Pseudo-NDVI from RGB
      3. Texture analysis (Laplacian + local std)
      4. Structure detection (contour-based)

    Returns (development_pct, analysis_dict).
    """
    if image is None:
        return 0.0, None, {}

    # Run all four analysis methods
    color = analyse_color_segmentation(image)
    ndvi = compute_pseudo_ndvi(image)
    texture = analyse_texture(image)
    structures = detect_structures_contours(image)

    # Weighted combination for final development score
    # Built-up from color analysis (weight 0.30)
    color_score = min(color["built_up_pct"], 100)

    # Inverse of vegetation from pseudo-NDVI (weight 0.25)
    ndvi_score = max(0, 100 - ndvi["vegetation_pct"])

    # Texture score normalised to 0-100 (weight 0.20)
    texture_score = min(100, texture["laplacian_var"] / 10.0)

    # Structure coverage (weight 0.25)
    structure_score = min(100, structures["coverage_pct"] * 2.5)

    development_pct = (
        0.30 * color_score +
        0.25 * ndvi_score +
        0.20 * texture_score +
        0.25 * structure_score
    )
    development_pct = round(min(100, max(0, development_pct)), 2)

    # Build composite overlay for visualization
    h, w = image.shape[:2]
    overlay = np.zeros((h, w, 3), dtype=np.uint8)

    # Red = built-up, Green = vegetation, Blue = structures
    if color.get("built_mask") is not None:
        built_resized = cv2.resize(color["built_mask"], (w, h))
        overlay[:, :, 2] = built_resized  # Red channel
    if color.get("veg_mask") is not None:
        veg_resized = cv2.resize(color["veg_mask"], (w, h))
        overlay[:, :, 1] = veg_resized   # Green channel
    if structures.get("threshold_mask") is not None:
        struct_resized = cv2.resize(structures["threshold_mask"], (w, h))
        overlay[:, :, 0] = struct_resized  # Blue channel

    analysis = {
        "color": {k: v for k, v in color.items()
                  if k not in ("built_mask", "veg_mask")},
        "ndvi": {k: v for k, v in ndvi.items() if k != "ndvi_map"},
        "texture": texture,
        "structures": {k: v for k, v in structures.items()
                       if k not in ("threshold_mask", "structures")},
        "weights": {
            "color_score": round(color_score, 1),
            "ndvi_score": round(ndvi_score, 1),
            "texture_score": round(texture_score, 1),
            "structure_score": round(structure_score, 1),
        },
    }

    return development_pct, overlay, analysis


def classify_status(pct, analysis=None):
    """
    Classify development status using the combined development percentage
    and optional analysis details for better accuracy.
    """
    # Use analysis details to refine if available
    if analysis:
        veg = analysis.get("color", {}).get("vegetation_pct", 0)
        built = analysis.get("color", {}).get("built_up_pct", 0)
        structs = analysis.get("structures", {}).get("structure_count", 0)

        # Strong vegetation signal → likely vacant even if edges detected
        if veg > 60 and built < 15 and structs == 0:
            return "Vacant"

        # Many structures + high built-up → fully developed
        if structs >= 5 and built > 40:
            return "Fully Developed"

    if pct < 20:
        return "Vacant"
    elif pct <= 55:
        return "Partially Developed"
    else:
        return "Fully Developed"


def check_deviation(props, status, analysis=None):
    """Check for deviations with improved context awareness."""
    plot_status = props.get("status", "").lower()
    construction = props.get("construction_allowed", True)
    zone = props.get("zone", "").upper()

    # Zone-specific rules
    restricted_zones = {"GREEN_AREA", "WATER_BODY", "PARKING", "BOUNDARY"}

    if zone in restricted_zones and status != "Vacant":
        return True, f"Development detected in restricted zone ({zone})"

    if not construction and status != "Vacant":
        return True, f"Construction in no-build zone ({zone})"

    if plot_status == "reserved" and status in ("Partially Developed", "Fully Developed"):
        return True, "Construction on reserved plot"

    if plot_status == "allotted" and status == "Vacant":
        # Check if analysis says truly vacant (not just poor detection)
        if analysis:
            veg = analysis.get("color", {}).get("vegetation_pct", 0)
            if veg > 50:
                return True, "Allotted plot appears unused — high vegetation detected"
        else:
            return True, "Allotted plot appears unused"

    return False, "No deviation"


# ──────────────────────────────────────────────
#  Main Render Function
# ──────────────────────────────────────────────

def render_satellite_compare():
    """Main function to render the satellite comparison page."""

    st.markdown("""
    <div style="background: linear-gradient(135deg, #0f3460 0%, #16213e 50%, #1a1a2e 100%);
         padding: 1.2rem 1.8rem; border-radius: 12px; margin-bottom: 1.5rem; color: white;">
        <h2 style="margin:0;">🔬 Satellite Plot Comparison</h2>
        <p style="margin:0.3rem 0 0; opacity:0.85; font-size:0.9rem;">
            Upload GeoJSON → View on satellite map → Detect changes → Generate report
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════
    #  Step 1: Load & Search Plot Data
    # ════════════════════════════════════════════
    st.markdown("### 📤 Step 1: Load & Search Plot Data")

    csidc_path = os.path.join(DATA_DIR, "csidc_real_plots.geojson")
    boundary_path = os.path.join(DATA_DIR, "csidc_outer_boundary.geojson")
    allotment_path = os.path.join(DATA_DIR, "allotment_map.geojson")

    # ── Data source selector ──
    available_sources = []
    if os.path.exists(csidc_path):
        available_sources.append("🏗️ CSIDC Industrial Plots")
    if os.path.exists(allotment_path):
        available_sources.append("📂 Sample Allotment Map")
    available_sources.append("📤 Upload GeoJSON")

    source = st.radio("Select data source:", available_sources, horizontal=True,
                      key="plot_data_source")

    # ── Handle Upload source ──
    if source == "📤 Upload GeoJSON":
        uploaded = st.file_uploader(
            "Upload a GeoJSON file with plot polygons",
            type=["geojson", "json"],
            key="sat_compare_upload"
        )
        if uploaded is None:
            st.info("👆 Upload a GeoJSON file to get started.")
            return
        try:
            gdf, geojson_data = parse_geojson(uploaded)
            st.session_state["compare_gdf"] = gdf
            st.session_state["compare_geojson"] = geojson_data
            st.session_state["is_csidc_data"] = False
        except Exception as e:
            st.error(f"❌ Failed to parse GeoJSON: {e}")
            return

    # ── Handle Sample Allotment source ──
    elif source == "📂 Sample Allotment Map":
        if "compare_geojson" not in st.session_state or st.session_state.get("_loaded_source") != source:
            with open(allotment_path) as f:
                geojson_data = json.load(f)
            gdf = gpd.GeoDataFrame.from_features(geojson_data["features"], crs="EPSG:4326")
            polygon_mask = gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
            gdf = gdf[polygon_mask].copy()
            st.session_state["compare_gdf"] = gdf
            st.session_state["compare_geojson"] = geojson_data
            st.session_state["is_csidc_data"] = False
            st.session_state["_loaded_source"] = source

    # ── Handle CSIDC source (main path with search/filter) ──
    elif source == "🏗️ CSIDC Industrial Plots":
        # Load full dataset once
        if "csidc_full_gdf" not in st.session_state or st.session_state.get("_loaded_source") != source:
            with open(csidc_path) as f:
                full_geojson = json.load(f)
            full_gdf = gpd.GeoDataFrame.from_features(full_geojson["features"], crs="EPSG:4326")
            polygon_mask = full_gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
            full_gdf = full_gdf[polygon_mask].copy()
            st.session_state["csidc_full_gdf"] = full_gdf
            st.session_state["csidc_full_geojson"] = full_geojson
            st.session_state["is_csidc_data"] = True
            st.session_state["_loaded_source"] = source

        full_gdf = st.session_state["csidc_full_gdf"]

        # ── Search & Filter Panel ──
        st.markdown("""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
             padding: 1rem 1.5rem; border-radius: 12px; margin-bottom: 1rem;">
            <h4 style="color: white; margin: 0;">🔍 Search & Filter Industrial Areas</h4>
            <p style="color: rgba(255,255,255,0.8); margin: 0.3rem 0 0 0; font-size: 0.85rem;">
                Browse {total} plots across {areas} industrial areas
            </p>
        </div>
        """.format(
            total=len(full_gdf),
            areas=full_gdf["INDUSTRIAL"].nunique() if "INDUSTRIAL" in full_gdf.columns else "?"
        ), unsafe_allow_html=True)

        # Filter controls in columns
        fc1, fc2, fc3 = st.columns([2, 1, 1])

        with fc1:
            # Industrial area dropdown
            all_areas = sorted(full_gdf["INDUSTRIAL"].dropna().unique().tolist()) if "INDUSTRIAL" in full_gdf.columns else []
            selected_area = st.selectbox(
                "🏭 Industrial Area",
                options=["— All Areas —"] + all_areas,
                key="csidc_area_filter",
                help="Select a specific industrial area to view its plots"
            )

        with fc2:
            # Type filter
            all_types = sorted(full_gdf["TYPE"].dropna().unique().tolist()) if "TYPE" in full_gdf.columns else []
            selected_type = st.selectbox(
                "📋 Plot Type",
                options=["All"] + all_types,
                key="csidc_type_filter"
            )

        with fc3:
            # Label filter
            all_labels = sorted(full_gdf["LABEL"].dropna().unique().tolist()) if "LABEL" in full_gdf.columns else []
            selected_label = st.selectbox(
                "🏷️ Label / Status",
                options=["All"] + all_labels,
                key="csidc_label_filter"
            )

        # Plot number search
        plot_search = st.text_input(
            "🔎 Search Plot Number (e.g. 5E, 16A, T3)",
            key="csidc_plot_search",
            placeholder="Type a plot number to find it..."
        )

        # Apply filters
        filtered_gdf = full_gdf.copy()
        if selected_area != "— All Areas —":
            filtered_gdf = filtered_gdf[filtered_gdf["INDUSTRIAL"] == selected_area]
        if selected_type != "All" and "TYPE" in filtered_gdf.columns:
            filtered_gdf = filtered_gdf[filtered_gdf["TYPE"] == selected_type]
        if selected_label != "All" and "LABEL" in filtered_gdf.columns:
            filtered_gdf = filtered_gdf[filtered_gdf["LABEL"] == selected_label]
        if plot_search.strip():
            search_term = plot_search.strip().upper()
            filtered_gdf = filtered_gdf[
                filtered_gdf["PLOT_NO"].fillna("").str.upper().str.contains(search_term, na=False)
            ]

        # Show filter results summary
        if filtered_gdf.empty:
            st.warning("⚠️ No plots match your filters. Try adjusting your search criteria.")
            return

        # Stats row
        sc1, sc2, sc3, sc4 = st.columns(4)
        with sc1:
            st.metric("Matching Plots", len(filtered_gdf))
        with sc2:
            n_areas = filtered_gdf["INDUSTRIAL"].nunique() if "INDUSTRIAL" in filtered_gdf.columns else 0
            st.metric("Industrial Areas", n_areas)
        with sc3:
            n_allotted = (filtered_gdf["LABEL"] == "INDUSTRIAL PLOT - ALLOTED").sum() if "LABEL" in filtered_gdf.columns else 0
            st.metric("Allotted Plots", n_allotted)
        with sc4:
            n_other = (filtered_gdf["TYPE"] == "OTHER").sum() if "TYPE" in filtered_gdf.columns else 0
            st.metric("Other Land", n_other)

        # Show filterable data table
        show_cols = [c for c in ["PLOT_NO", "INDUSTRIAL", "TYPE", "LABEL", "REMARK"] if c in filtered_gdf.columns]
        if show_cols:
            with st.expander(f"📊 View Data Table ({len(filtered_gdf)} plots)", expanded=False):
                st.dataframe(filtered_gdf[show_cols].reset_index(drop=True), use_container_width=True, height=250)

        # Build filtered geojson for downstream steps
        filtered_features = []
        full_geojson = st.session_state["csidc_full_geojson"]
        filtered_indices = set(filtered_gdf.index.tolist())
        all_feats = full_geojson["features"]
        # Map gdf index back to geojson features
        orig_gdf = st.session_state["csidc_full_gdf"]
        for i in filtered_indices:
            if i < len(all_feats):
                filtered_features.append(all_feats[i])

        geojson_data = {
            "type": "FeatureCollection",
            "features": filtered_features
        }
        st.session_state["compare_gdf"] = filtered_gdf.reset_index(drop=True)
        st.session_state["compare_geojson"] = geojson_data

        st.markdown("---")

    # Retrieve loaded data
    gdf = st.session_state.get("compare_gdf")
    geojson_data = st.session_state.get("compare_geojson")
    is_csidc = st.session_state.get("is_csidc_data", False)

    if gdf is None or gdf.empty:
        st.warning("No polygon plots found.")
        return

    st.success(f"✅ Loaded **{len(gdf)} plot polygons** ready for satellite comparison.")

    # ════════════════════════════════════════════
    #  Step 2: Interactive Satellite Map
    # ════════════════════════════════════════════
    st.markdown("### 🗺️ Step 2: View Plots on Satellite Map")

    center_lat, center_lon, bounds = get_bounds_center(gdf)

    # Create folium map with satellite basemap
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=16,
        tiles=None,
    )

    # Add satellite tile layer (Esri World Imagery)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri",
        name="🛰️ Satellite",
        overlay=False,
        control=True,
    ).add_to(m)

    # Add OpenStreetMap as alternative
    folium.TileLayer("OpenStreetMap", name="🗺️ Street Map").add_to(m)

    # CSIDC label color mapping
    label_colors = {
        "INDUSTRIAL PLOT - ALLOTED": "#00ff88",
        "INDUSTRIAL PLOT - UNALLOTED": "#ff6b6b",
        "OTHER LAND": "#ffd93d",
        "ROAD": "#a8edea",
        "GREEN BELT": "#38ef7d",
    }
    zone_colors = {
        "TILDA": "#4facfe",
        "EXPANSION": "#00f2fe",
        "GREEN_AREA": "#38ef7d",
        "PARKING": "#ffd93d",
        "WAREHOUSE": "#ff6b6b",
        "WATER_BODY": "#667eea",
        "FOOD_PARK": "#f093fb",
        "AMENITIES": "#a8edea",
        "BOUNDARY": "#ffffff",
    }

    # Load outer boundary if available (for CSIDC data)
    boundary_path = os.path.join(DATA_DIR, "csidc_outer_boundary.geojson")
    if is_csidc and os.path.exists(boundary_path):
        try:
            with open(boundary_path) as bf:
                boundary_data = json.load(bf)
            boundary_group = folium.FeatureGroup(name="🔲 Area Boundaries", show=True)
            for feat in boundary_data.get("features", []):
                geom = shape(feat["geometry"])
                if geom.geom_type == "MultiPolygon":
                    for poly in geom.geoms:
                        coords = [(c[1], c[0]) for c in poly.exterior.coords]
                        area_name = feat["properties"].get("INDUSTRIAL", "Boundary")
                        folium.Polygon(
                            locations=coords, color="#ffffff", weight=2,
                            dash_array="8", fill=False,
                            tooltip=f"Boundary: {area_name}"
                        ).add_to(boundary_group)
                elif geom.geom_type == "Polygon":
                    coords = [(c[1], c[0]) for c in geom.exterior.coords]
                    area_name = feat["properties"].get("INDUSTRIAL", "Boundary")
                    folium.Polygon(
                        locations=coords, color="#ffffff", weight=2,
                        dash_array="8", fill=False,
                        tooltip=f"Boundary: {area_name}"
                    ).add_to(boundary_group)
            boundary_group.add_to(m)
        except Exception:
            pass

    # Draw plot polygons
    polygon_group = folium.FeatureGroup(name="📐 Plot Boundaries")

    for idx, row in gdf.iterrows():
        geom = row.geometry
        # Handle MultiPolygon by drawing each sub-polygon
        polys = []
        if geom.geom_type == "MultiPolygon":
            polys = list(geom.geoms)
        else:
            polys = [geom]

        # Determine display values based on data source
        if is_csidc:
            pid = row.get("PLOT_NO", "") or f"Plot_{idx}"
            area_name = row.get("INDUSTRIAL", "Unknown")
            label = row.get("LABEL", "")
            ptype = row.get("TYPE", "")
            color = label_colors.get(label, "#4facfe")
            tooltip_html = (
                f"<b>🏗️ Plot {pid}</b><br>"
                f"<b>Area:</b> {area_name}<br>"
                f"<b>Type:</b> {ptype}<br>"
                f"<b>Label:</b> {label}"
            )
        else:
            pid = row.get("plot_id", f"Plot_{idx}")
            zone = row.get("zone", "Unknown")
            status = row.get("status", "unknown")
            area_sqm = row.get("area_sqm", 0)
            pnum = row.get("plot_number", pid)
            color = zone_colors.get(zone, "#ffffff")
            tooltip_html = (
                f"<b>🏗️ {pid}</b><br>"
                f"<b>Plot #:</b> {pnum}<br>"
                f"<b>Zone:</b> {zone}<br>"
                f"<b>Area:</b> {area_sqm} sqm<br>"
                f"<b>Status:</b> {status}"
            )

        for poly in polys:
            coords = list(poly.exterior.coords)
            latlng = [(c[1], c[0]) for c in coords]
            folium.Polygon(
                locations=latlng,
                color=color,
                weight=3,
                fill=True,
                fill_color=color,
                fill_opacity=0.3,
                tooltip=folium.Tooltip(tooltip_html),
                popup=folium.Popup(tooltip_html, max_width=300),
            ).add_to(polygon_group)

    polygon_group.add_to(m)
    folium.LayerControl(collapsed=False).add_to(m)

    # Auto-fit bounds
    m.fit_bounds([
        [bounds[1] - 0.002, bounds[0] - 0.002],
        [bounds[3] + 0.002, bounds[2] + 0.002]
    ])

    st_folium(m, width=None, height=550, use_container_width=True)

    st.markdown("---")

    # ════════════════════════════════════════════
    #  Step 3: Fetch Satellite & Analyze
    # ════════════════════════════════════════════
    st.markdown("### 🛰️ Step 3: Fetch Satellite Imagery & Analyze")

    col1, col2 = st.columns(2)
    with col1:
        use_gee = st.checkbox("Try Google Earth Engine (requires authentication)",
                              value=False,
                              help="If unchecked, uses Esri satellite tiles as fallback")
    with col2:
        save_viz = st.checkbox("Save visualization images", value=True)

    if st.button("🚀 Fetch Satellite Images & Run Analysis", use_container_width=True,
                 type="primary"):

        sat_output_dir = os.path.join(OUTPUT_DIR, "satellite_tiles")
        viz_output_dir = os.path.join(OUTPUT_DIR, "visualizations")
        os.makedirs(sat_output_dir, exist_ok=True)

        results = []
        features = [f for f in geojson_data["features"]
                     if f["geometry"]["type"] in ("Polygon", "MultiPolygon")]

        progress = st.progress(0, text="Fetching satellite images...")
        total = len(features)

        for i, feat in enumerate(features):
            props = feat["properties"]

            # Determine plot ID based on data source
            if is_csidc:
                pno = props.get("PLOT_NO", "") or f"Plot_{i}"
                ind_area = props.get("INDUSTRIAL", "Unknown")
                pid = f"{ind_area} - {pno}"
            else:
                pid = props.get("plot_id", f"Plot_{i}")

            progress.progress((i + 1) / total,
                              text=f"Analyzing {pid} ({i+1}/{total})...")

            # Fetch satellite image
            sat_path = None
            if use_gee:
                sat_path = fetch_satellite_thumbnail_gee(geojson_data, feat, sat_output_dir)

            if sat_path is None:
                sat_path = generate_satellite_tile_image(feat, sat_output_dir)

            # Load and analyze
            image = cv2.imread(sat_path) if sat_path else None
            dev_pct, overlay, analysis = detect_development(image)
            status = classify_status(dev_pct, analysis)
            has_dev, dev_reason = check_deviation(props, status, analysis)

            # Calculate area from geometry
            geom = shape(feat["geometry"])
            b = geom.bounds
            area = props.get("area_sqm", 0)
            if area == 0:
                area = round((b[2]-b[0]) * 104000 * (b[3]-b[1]) * 111120, 1)

            # Build result with CSIDC-aware fields
            result_entry = {
                "plot_id": pid,
                "plot_number": props.get("PLOT_NO", props.get("plot_number", pid)) if is_csidc else props.get("plot_number", pid),
                "zone": props.get("INDUSTRIAL", "N/A") if is_csidc else props.get("zone", "N/A"),
                "area_sqm": area,
                "industry_type": props.get("LABEL", "N/A") if is_csidc else props.get("industry_type", "N/A"),
                "developed_pct": dev_pct,
                "status": status,
                "has_deviation": has_dev,
                "deviation_reason": dev_reason,
                "sat_image_path": sat_path,
                "overlay": overlay,
                "analysis": analysis,
            }
            results.append(result_entry)

        progress.progress(1.0, text="✅ Analysis complete!")
        st.session_state["compare_results"] = results

    # ════════════════════════════════════════════
    #  Step 4: Show Results
    # ════════════════════════════════════════════
    if "compare_results" in st.session_state:
        results = st.session_state["compare_results"]

        st.markdown("---")
        st.markdown("### 📊 Step 4: Analysis Results")

        # Summary metrics
        vacant = sum(1 for r in results if r["status"] == "Vacant")
        partial = sum(1 for r in results if r["status"] == "Partially Developed")
        developed = sum(1 for r in results if r["status"] == "Fully Developed")
        deviations = sum(1 for r in results if r["has_deviation"])

        mc1, mc2, mc3, mc4 = st.columns(4)
        with mc1:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#4facfe,#00f2fe); padding:1rem;
                 border-radius:10px; color:white; text-align:center;">
                <h3 style="margin:0; font-size:1.8rem;">{len(results)}</h3>
                <p style="margin:0; font-size:0.85rem;">Total Plots</p>
            </div>""", unsafe_allow_html=True)
        with mc2:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#eb3349,#f45c43); padding:1rem;
                 border-radius:10px; color:white; text-align:center;">
                <h3 style="margin:0; font-size:1.8rem;">{vacant}</h3>
                <p style="margin:0; font-size:0.85rem;">Vacant</p>
            </div>""", unsafe_allow_html=True)
        with mc3:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#f7971e,#ffd200); padding:1rem;
                 border-radius:10px; color:white; text-align:center;">
                <h3 style="margin:0; font-size:1.8rem;">{partial}</h3>
                <p style="margin:0; font-size:0.85rem;">Partial</p>
            </div>""", unsafe_allow_html=True)
        with mc4:
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#11998e,#38ef7d); padding:1rem;
                 border-radius:10px; color:white; text-align:center;">
                <h3 style="margin:0; font-size:1.8rem;">{developed}</h3>
                <p style="margin:0; font-size:0.85rem;">Developed</p>
            </div>""", unsafe_allow_html=True)

        if deviations > 0:
            st.warning(f"⚠️ **{deviations} deviation(s) detected!**")

        # Results table
        st.markdown("#### 📋 Detailed Results")
        table_data = []
        for r in results:
            table_data.append({
                "Plot ID": r["plot_id"],
                "Plot #": r["plot_number"],
                "Zone": r["zone"],
                "Area (sqm)": r["area_sqm"],
                "Developed %": f"{r['developed_pct']:.1f}%",
                "Status": r["status"],
                "Deviation": "⚠️ YES" if r["has_deviation"] else "✅ No",
            })
        st.dataframe(pd.DataFrame(table_data), use_container_width=True, height=350)

        # Per-plot visual analysis
        st.markdown("#### 🔍 Per-Plot Visual Analysis")

        for r in results:
            with st.expander(
                f"{'🔴' if r['has_deviation'] else '🟢'} "
                f"{r['plot_id']} — {r['status']} ({r['developed_pct']:.1f}%)",
                expanded=r["has_deviation"]
            ):
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.markdown("**🛰️ Satellite Image**")
                    if r.get("sat_image_path") and os.path.exists(r["sat_image_path"]):
                        st.image(r["sat_image_path"], use_container_width=True)
                    else:
                        st.info("No image available")

                with c2:
                    st.markdown("**🔍 Segmentation Overlay**")
                    caption = "R=Built-up  G=Vegetation  B=Structures"
                    if r.get("overlay") is not None:
                        st.image(r["overlay"], caption=caption,
                                 use_container_width=True)
                    else:
                        st.info("No analysis data")

                with c3:
                    st.markdown("**📊 Analysis Breakdown**")
                    st.metric("Overall Development", f"{r['developed_pct']:.1f}%")
                    st.metric("Classification", r["status"])
                    if r["has_deviation"]:
                        st.error(f"⚠️ {r['deviation_reason']}")
                    else:
                        st.success("✅ No deviation")

                # Show detailed signals
                analysis = r.get("analysis", {})
                if analysis:
                    st.markdown("---")
                    s1, s2, s3, s4 = st.columns(4)
                    color_data = analysis.get("color", {})
                    ndvi_data = analysis.get("ndvi", {})
                    tex_data = analysis.get("texture", {})
                    struct_data = analysis.get("structures", {})

                    with s1:
                        st.markdown("**🎨 Color (HSV)**")
                        st.caption(f"🟢 Vegetation: {color_data.get('vegetation_pct', 0):.1f}%")
                        st.caption(f"🏗️ Built-up: {color_data.get('built_up_pct', 0):.1f}%")
                        st.caption(f"🟤 Bare soil: {color_data.get('bare_soil_pct', 0):.1f}%")
                        st.caption(f"🌊 Water: {color_data.get('water_pct', 0):.1f}%")
                    with s2:
                        st.markdown("**🌿 Pseudo-NDVI**")
                        st.caption(f"Mean NDVI: {ndvi_data.get('mean_ndvi', 0):.4f}")
                        st.caption(f"Vegetation: {ndvi_data.get('vegetation_pct', 0):.1f}%")
                        st.caption(f"Non-veg: {ndvi_data.get('built_up_pct', 0):.1f}%")
                    with s3:
                        st.markdown("**📐 Texture**")
                        st.caption(f"Laplacian: {tex_data.get('laplacian_var', 0):.0f}")
                        st.caption(f"Local StdDev: {tex_data.get('mean_local_std', 0):.1f}")
                        st.caption(f"Structures: {'Yes' if tex_data.get('has_structures') else 'No'}")
                    with s4:
                        st.markdown("**🏢 Structures**")
                        st.caption(f"Count: {struct_data.get('structure_count', 0)}")
                        st.caption(f"Coverage: {struct_data.get('coverage_pct', 0):.1f}%")

                    # Weights used
                    weights = analysis.get("weights", {})
                    if weights:
                        st.caption(
                            f"Scores → Color: {weights.get('color_score', 0):.0f} | "
                            f"NDVI: {weights.get('ndvi_score', 0):.0f} | "
                            f"Texture: {weights.get('texture_score', 0):.0f} | "
                            f"Struct: {weights.get('structure_score', 0):.0f}"
                        )

                st.caption(f"Zone: {r['zone']} | Area: {r['area_sqm']:.0f} sqm")

        st.markdown("---")

        # ════════════════════════════════════════
        #  Step 5: Generate & Download Report
        # ════════════════════════════════════════
        st.markdown("### 📑 Step 5: Generate Report")

        if st.button("📑 Generate PDF Report", use_container_width=True, type="primary"):
            with st.spinner("Generating PDF report..."):
                try:
                    from plot_comparison.report import generate_pdf_report

                    # Prepare clean results (remove non-serializable data)
                    clean = []
                    for r in results:
                        clean.append({k: v for k, v in r.items()
                                     if k not in ("overlay", "analysis", "sat_image_path")})

                    pdf_path = os.path.join(OUTPUT_DIR, "satellite_comparison_report.pdf")
                    viz_dir = os.path.join(OUTPUT_DIR, "visualizations")
                    generate_pdf_report(clean, pdf_path, viz_dir=viz_dir)

                    st.session_state["compare_pdf_path"] = pdf_path
                    st.success("✅ Report generated!")

                except Exception as e:
                    st.error(f"Report generation failed: {e}")

        # Download button
        pdf_path = st.session_state.get("compare_pdf_path")
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()
            st.download_button(
                "📥 Download PDF Report",
                pdf_bytes,
                "satellite_comparison_report.pdf",
                "application/pdf",
                use_container_width=True,
            )

        # Deviation details
        deviations_list = [r for r in results if r["has_deviation"]]
        if deviations_list:
            st.markdown("#### 🚨 Deviation Details")
            for r in deviations_list:
                st.markdown(
                    f"- **{r['plot_id']}** (Plot #{r['plot_number']}, {r['zone']}): "
                    f"{r['deviation_reason']}"
                )
