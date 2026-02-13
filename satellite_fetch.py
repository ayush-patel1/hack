"""
LandGuard AI - Satellite Data Fetcher
Fetches Sentinel-1 (SAR) and Sentinel-2 (Optical) imagery from Google Earth Engine
for polygon-based change detection on industrial plots.

Setup:
    1. pip install earthengine-api
    2. earthengine authenticate   (one-time browser auth)
    3. Or use a service account JSON key
"""

import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAT_DIR = os.path.join(DATA_DIR, "satellite")

# ──────────────────────────────────────────────
#  GEE Initialization
# ──────────────────────────────────────────────
_ee = None


def _init_ee(service_account_key=None):
    """Initialize Google Earth Engine. Call once."""
    global _ee
    if _ee is not None:
        return _ee

    try:
        import ee
    except ImportError:
        print("[ERROR] earthengine-api not installed. Run: pip install earthengine-api")
        sys.exit(1)

    try:
        if service_account_key and os.path.exists(service_account_key):
            credentials = ee.ServiceAccountCredentials(None, service_account_key)
            ee.Initialize(credentials)
        else:
            ee.Authenticate()
            ee.Initialize(project='landguard-ai')
        _ee = ee
        print("[OK] Google Earth Engine initialized")
    except Exception as e:
        print(f"[WARN] GEE init failed: {e}")
        print("       Run `earthengine authenticate` to set up credentials.")
        print("       Falling back to offline mode.")
        _ee = None

    return _ee


# ──────────────────────────────────────────────
#  Polygon Helpers
# ──────────────────────────────────────────────
def polygon_to_ee_geometry(coords):
    """Convert a list of [lon, lat] coords to an ee.Geometry.Polygon."""
    ee = _init_ee()
    if ee is None:
        return None
    return ee.Geometry.Polygon([coords])


def geojson_to_ee_feature_collection(geojson_path):
    """Load a GeoJSON file as an ee.FeatureCollection."""
    ee = _init_ee()
    if ee is None:
        return None

    with open(geojson_path) as f:
        data = json.load(f)

    features = []
    for feat in data["features"]:
        geom = feat["geometry"]
        props = feat.get("properties", {})
        ee_geom = ee.Geometry(geom)
        ee_feat = ee.Feature(ee_geom, props)
        features.append(ee_feat)

    return ee.FeatureCollection(features)


# ──────────────────────────────────────────────
#  Sentinel-1 SAR Data
# ──────────────────────────────────────────────
def fetch_sentinel1(region_geojson, start_date, end_date, polarization="VV"):
    """
    Fetch Sentinel-1 GRD SAR imagery for a region and date range.

    Args:
        region_geojson: Path to GeoJSON file defining the area of interest.
        start_date: Start date string 'YYYY-MM-DD'.
        end_date: End date string 'YYYY-MM-DD'.
        polarization: 'VV', 'VH', or 'both'.

    Returns:
        ee.Image — median composite of the SAR backscatter.
    """
    ee = _init_ee()
    if ee is None:
        return None

    with open(region_geojson) as f:
        geojson = json.load(f)

    # Build bounding region from all features
    all_coords = []
    for feat in geojson["features"]:
        coords = feat["geometry"]["coordinates"][0]
        all_coords.extend(coords)

    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    bbox = ee.Geometry.Rectangle([min(lons) - 0.01, min(lats) - 0.01,
                                   max(lons) + 0.01, max(lats) + 0.01])

    # Sentinel-1 GRD collection
    s1 = (ee.ImageCollection("COPERNICUS/S1_GRD")
          .filterBounds(bbox)
          .filterDate(start_date, end_date)
          .filter(ee.Filter.listContains("transmitterReceiverPolarisation", polarization))
          .filter(ee.Filter.eq("instrumentMode", "IW"))
          .select(polarization))

    count = s1.size().getInfo()
    print(f"[INFO] Sentinel-1 images found: {count} ({start_date} to {end_date})")

    if count == 0:
        print("[WARN] No Sentinel-1 images found for this region/date range.")
        return None

    # Create median composite
    composite = s1.median().clip(bbox)
    return composite


def fetch_sentinel2(region_geojson, start_date, end_date, cloud_pct=20):
    """
    Fetch Sentinel-2 optical imagery with cloud masking.

    Returns:
        ee.Image — median composite with NDVI band added.
    """
    ee = _init_ee()
    if ee is None:
        return None

    with open(region_geojson) as f:
        geojson = json.load(f)

    all_coords = []
    for feat in geojson["features"]:
        coords = feat["geometry"]["coordinates"][0]
        all_coords.extend(coords)

    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]
    bbox = ee.Geometry.Rectangle([min(lons) - 0.01, min(lats) - 0.01,
                                   max(lons) + 0.01, max(lats) + 0.01])

    # Cloud masking function
    def mask_clouds(image):
        qa = image.select("QA60")
        cloud_mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
        return image.updateMask(cloud_mask)

    # Sentinel-2 SR collection
    s2 = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
          .filterBounds(bbox)
          .filterDate(start_date, end_date)
          .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", cloud_pct))
          .map(mask_clouds)
          .select(["B2", "B3", "B4", "B8", "B11", "B12"]))

    count = s2.size().getInfo()
    print(f"[INFO] Sentinel-2 images found: {count} ({start_date} to {end_date})")

    if count == 0:
        print("[WARN] No Sentinel-2 images found for this region/date range.")
        return None

    composite = s2.median().clip(bbox)

    # Add NDVI band: (NIR - Red) / (NIR + Red)
    ndvi = composite.normalizedDifference(["B8", "B4"]).rename("NDVI")
    # Add NDBI (Built-up Index): (SWIR - NIR) / (SWIR + NIR)
    ndbi = composite.normalizedDifference(["B11", "B8"]).rename("NDBI")

    composite = composite.addBands(ndvi).addBands(ndbi)
    return composite


# ──────────────────────────────────────────────
#  Export / Download Tiles
# ──────────────────────────────────────────────
def download_plot_tiles(image, plots_geojson, output_dir, band, scale=10):
    """
    Download satellite tiles clipped to each plot polygon.

    Args:
        image: ee.Image to sample.
        plots_geojson: Path to GeoJSON with plot polygons.
        output_dir: Directory to save tiles.
        band: Band name to extract (e.g. 'VV', 'NDVI', 'NDBI').
        scale: Resolution in metres.
    """
    ee = _init_ee()
    if ee is None or image is None:
        return {}

    os.makedirs(output_dir, exist_ok=True)

    with open(plots_geojson) as f:
        data = json.load(f)

    tile_paths = {}
    for feat in data["features"]:
        pid = feat["properties"].get("plot_id", "unknown")
        geom = ee.Geometry(feat["geometry"])

        try:
            # Get thumbnail URL as a PNG
            url = image.select(band).clip(geom).getThumbURL({
                "min": -25 if band in ("VV", "VH") else -0.5,
                "max": 0 if band in ("VV", "VH") else 1.0,
                "dimensions": 400,
                "format": "png",
                "palette": ["blue", "white", "green"] if "NDV" in band
                           else ["black", "white"],
            })

            # Download the tile
            import urllib.request
            out_path = os.path.join(output_dir, f"{pid}_{band}.png")
            urllib.request.urlretrieve(url, out_path)
            tile_paths[pid] = out_path
            print(f"  [OK] {pid} — {band} tile saved")

        except Exception as e:
            print(f"  [WARN] {pid} — Failed: {e}")

    return tile_paths


# ──────────────────────────────────────────────
#  Compute Per-Plot Statistics
# ──────────────────────────────────────────────
def compute_plot_stats(image, plots_geojson, bands=None, scale=10):
    """
    Compute mean/std statistics for each band over each plot polygon.

    Returns:
        dict: {plot_id: {band: {mean, std}}}
    """
    ee = _init_ee()
    if ee is None or image is None:
        return {}

    if bands is None:
        bands = image.bandNames().getInfo()

    with open(plots_geojson) as f:
        data = json.load(f)

    results = {}
    for feat in data["features"]:
        pid = feat["properties"].get("plot_id", "unknown")
        geom = ee.Geometry(feat["geometry"])

        try:
            stats = image.reduceRegion(
                reducer=ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
                geometry=geom,
                scale=scale,
                maxPixels=1e8,
            ).getInfo()

            plot_stats = {}
            for b in bands:
                plot_stats[b] = {
                    "mean": stats.get(f"{b}_mean", stats.get(b)),
                    "std": stats.get(f"{b}_stdDev"),
                }
            results[pid] = plot_stats
            print(f"  [OK] {pid} — stats computed")

        except Exception as e:
            print(f"  [WARN] {pid} — stats failed: {e}")

    return results


# ──────────────────────────────────────────────
#  Full Fetch Pipeline
# ──────────────────────────────────────────────
def fetch_all(plots_geojson=None, reference_date=None, current_date=None,
              service_key=None):
    """
    Complete satellite data fetch pipeline.

    Args:
        plots_geojson: Path to allotment map GeoJSON.
        reference_date: 'YYYY-MM-DD' baseline date (default: 6 months ago).
        current_date: 'YYYY-MM-DD' current date (default: today).
        service_key: Optional GEE service account key path.
    """
    os.makedirs(SAT_DIR, exist_ok=True)

    plots_geojson = plots_geojson or os.path.join(DATA_DIR, "reference_plots.geojson")

    if not os.path.exists(plots_geojson):
        print("[ERROR] Plot GeoJSON not found. Provide allotment map or run generate_sample_data.py")
        sys.exit(1)

    now = datetime.now()
    if current_date is None:
        current_date = now.strftime("%Y-%m-%d")
    if reference_date is None:
        reference_date = (now - timedelta(days=180)).strftime("%Y-%m-%d")

    # Date windows (30-day composites)
    ref_start = reference_date
    ref_end = (datetime.strptime(reference_date, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
    cur_start = (datetime.strptime(current_date, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    cur_end = current_date

    print("=" * 60)
    print("LandGuard AI — Satellite Data Fetch")
    print("=" * 60)
    print(f"  Plots:     {plots_geojson}")
    print(f"  Reference: {ref_start} to {ref_end}")
    print(f"  Current:   {cur_start} to {cur_end}")
    print()

    _init_ee(service_account_key=service_key)

    results = {"reference": {}, "current": {}}

    # ── Sentinel-1 SAR ──
    print("\n--- Sentinel-1 SAR (Reference) ---")
    s1_ref = fetch_sentinel1(plots_geojson, ref_start, ref_end, "VV")
    print("\n--- Sentinel-1 SAR (Current) ---")
    s1_cur = fetch_sentinel1(plots_geojson, cur_start, cur_end, "VV")

    if s1_ref:
        print("\nDownloading reference SAR tiles...")
        ref_dir = os.path.join(SAT_DIR, "sentinel1_reference")
        results["reference"]["s1_tiles"] = download_plot_tiles(
            s1_ref, plots_geojson, ref_dir, "VV")
        results["reference"]["s1_stats"] = compute_plot_stats(
            s1_ref, plots_geojson, ["VV"])

    if s1_cur:
        print("\nDownloading current SAR tiles...")
        cur_dir = os.path.join(SAT_DIR, "sentinel1_current")
        results["current"]["s1_tiles"] = download_plot_tiles(
            s1_cur, plots_geojson, cur_dir, "VV")
        results["current"]["s1_stats"] = compute_plot_stats(
            s1_cur, plots_geojson, ["VV"])

    # ── Sentinel-2 Optical ──
    print("\n--- Sentinel-2 Optical (Reference) ---")
    s2_ref = fetch_sentinel2(plots_geojson, ref_start, ref_end)
    print("\n--- Sentinel-2 Optical (Current) ---")
    s2_cur = fetch_sentinel2(plots_geojson, cur_start, cur_end)

    if s2_ref:
        print("\nDownloading reference NDVI/NDBI tiles...")
        ref_dir = os.path.join(SAT_DIR, "sentinel2_reference")
        download_plot_tiles(s2_ref, plots_geojson, ref_dir, "NDVI")
        download_plot_tiles(s2_ref, plots_geojson, ref_dir, "NDBI")
        results["reference"]["s2_stats"] = compute_plot_stats(
            s2_ref, plots_geojson, ["NDVI", "NDBI"])

    if s2_cur:
        print("\nDownloading current NDVI/NDBI tiles...")
        cur_dir = os.path.join(SAT_DIR, "sentinel2_current")
        download_plot_tiles(s2_cur, plots_geojson, cur_dir, "NDVI")
        download_plot_tiles(s2_cur, plots_geojson, cur_dir, "NDBI")
        results["current"]["s2_stats"] = compute_plot_stats(
            s2_cur, plots_geojson, ["NDVI", "NDBI"])

    # ── Save results ──
    output_path = os.path.join(SAT_DIR, "satellite_data.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'=' * 60}")
    print(f"[OK] Satellite data saved to {SAT_DIR}/")
    print(f"     Run `python change_detection.py` next.")

    return results


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fetch satellite data from GEE")
    parser.add_argument("--plots", default=None,
                        help="Path to allotment map GeoJSON")
    parser.add_argument("--ref-date", default=None,
                        help="Reference date YYYY-MM-DD (default: 6 months ago)")
    parser.add_argument("--cur-date", default=None,
                        help="Current date YYYY-MM-DD (default: today)")
    parser.add_argument("--key", default=None,
                        help="GEE service account JSON key path")
    args = parser.parse_args()

    fetch_all(
        plots_geojson=args.plots,
        reference_date=args.ref_date,
        current_date=args.cur_date,
        service_key=args.key,
    )
