"""
fetch_csidc_live.py — Real-time WFS data fetcher for CSIDC industrial plot data.

Fetches live vector polygon data from the CG GIS GeoServer WFS endpoint:
  - Plot polygons with allotment details (~4,159 plots)
  - Industrial area outer boundaries (~36 areas)

No authentication required. Data is returned as GeoJSON FeatureCollections.
"""

import json
import os
import ssl
import time
import urllib.request
import urllib.parse
from typing import Optional

# ── Configuration ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

GEOSERVER_BASE = "https://cggis.cgstate.gov.in/giscg/wmscgcog"

# Confirmed working WFS layers
LAYER_PLOTS = "CGCOG_DATABASE:cg_industrial_area_with_plot_info"
LAYER_BOUNDARIES = "CGCOG_DATABASE:csidc_industrial_area_outer_boundary"

# Additional layers to try
EXTRA_LAYERS = [
    "CGCOG_DATABASE:csidc_plots",
    "CGCOG_DATABASE:csidc_plot_boundary",
    "CGCOG_DATABASE:csidc_building",
    "CGCOG_DATABASE:csidc_road",
    "CGCOG_DATABASE:csidc_industrial_area",
    "CGCOG_DATABASE:csidc_land_use",
]

BATCH_SIZE = 200
REQUEST_DELAY = 0.3  # seconds between batches (be nice to the server)

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE


# ── Core WFS Fetcher ───────────────────────────────────────

def _make_request(url: str, timeout: int = 30) -> tuple:
    """Make HTTP GET request with browser-like headers."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://cggis.cgstate.gov.in/csidc/",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
        return resp.read(), resp.status
    except urllib.error.HTTPError as e:
        return e.read(), e.code
    except Exception as e:
        return None, 0


def fetch_wfs_batch(layer: str, offset: int = 0, max_features: int = BATCH_SIZE,
                    bbox: Optional[tuple] = None) -> dict:
    """
    Fetch a single batch of WFS features as GeoJSON.

    Args:
        layer: WFS layer name (e.g. "CGCOG_DATABASE:cg_industrial_area_with_plot_info")
        offset: STARTINDEX for pagination
        max_features: MAXFEATURES per request
        bbox: Optional (min_lat, min_lon, max_lat, max_lon) to filter spatially

    Returns:
        Parsed GeoJSON dict or None on failure.
    """
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": layer,
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:4326",
        "MAXFEATURES": str(max_features),
        "STARTINDEX": str(offset),
    }
    if bbox:
        params["BBOX"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326"

    url = GEOSERVER_BASE + "?" + urllib.parse.urlencode(params)
    data, status = _make_request(url)

    if data and status == 200:
        try:
            text = data.decode("utf-8", errors="replace")
            return json.loads(text)
        except json.JSONDecodeError:
            return None
    return None


def fetch_all_features(layer: str, bbox: Optional[tuple] = None,
                       max_total: int = 5000,
                       progress_callback=None) -> list:
    """
    Fetch ALL features from a WFS layer using pagination.

    Args:
        layer: WFS layer name
        bbox: Optional spatial filter
        max_total: Safety cap on total features
        progress_callback: fn(fetched_so_far, batch_count) for progress updates

    Returns:
        List of GeoJSON Feature dicts.
    """
    all_features = []
    offset = 0
    batch_num = 0

    while len(all_features) < max_total:
        batch_num += 1
        result = fetch_wfs_batch(layer, offset=offset, bbox=bbox)

        if not result or not result.get("features"):
            break

        batch = result["features"]

        # Clean coordinates (remove Z values if present)
        for feat in batch:
            if feat.get("geometry"):
                _clean_coords(feat["geometry"])

        all_features.extend(batch)

        if progress_callback:
            progress_callback(len(all_features), batch_num)

        if len(batch) < BATCH_SIZE:
            break  # last page

        offset += BATCH_SIZE
        time.sleep(REQUEST_DELAY)

    return all_features[:max_total]


def _clean_coords(geom: dict):
    """Strip Z values from coordinates (keep only lon, lat)."""
    gtype = geom.get("type", "")
    coords = geom.get("coordinates")
    if not coords:
        return

    if gtype == "MultiPolygon":
        geom["coordinates"] = [
            [[(c[0], c[1]) for c in ring] for ring in poly]
            for poly in coords
        ]
    elif gtype == "Polygon":
        geom["coordinates"] = [
            [(c[0], c[1]) for c in ring]
            for ring in coords
        ]
    elif gtype == "MultiLineString":
        geom["coordinates"] = [
            [(c[0], c[1]) for c in line]
            for line in coords
        ]
    elif gtype == "LineString":
        geom["coordinates"] = [(c[0], c[1]) for c in coords]
    elif gtype == "Point":
        geom["coordinates"] = (coords[0], coords[1])


def _normalize_geometry(feat: dict) -> dict:
    """
    Normalize MultiPolygon to Polygon if it has only one polygon.
    This simplifies downstream processing.
    """
    geom = feat.get("geometry", {})
    if geom.get("type") == "MultiPolygon":
        coords = geom["coordinates"]
        if len(coords) == 1:
            feat["geometry"] = {"type": "Polygon", "coordinates": coords[0]}
    return feat


# ── High-Level Fetch Functions ─────────────────────────────

def fetch_plots(industrial_area: Optional[str] = None,
                bbox: Optional[tuple] = None,
                max_plots: int = 5000,
                progress_callback=None) -> dict:
    """
    Fetch industrial plot polygons from CSIDC GeoServer.

    Args:
        industrial_area: Filter by industrial area name (e.g. "URLA PHASE-I")
        bbox: Optional (min_lat, min_lon, max_lat, max_lon)
        max_plots: Max number of plots to fetch
        progress_callback: Progress callback function

    Returns:
        GeoJSON FeatureCollection dict.
    """
    features = fetch_all_features(
        LAYER_PLOTS, bbox=bbox, max_total=max_plots,
        progress_callback=progress_callback
    )

    # Normalize geometries
    features = [_normalize_geometry(f) for f in features]

    # Filter by industrial area if specified
    if industrial_area and features:
        area_upper = industrial_area.upper().strip()
        features = [
            f for f in features
            if area_upper in (f.get("properties", {}).get("INDUSTRIAL", "") or "").upper()
        ]

    return _build_collection(features)


def fetch_boundaries(industrial_area: Optional[str] = None,
                     progress_callback=None) -> dict:
    """
    Fetch industrial area outer boundary polygons.

    Args:
        industrial_area: Filter by area name
        progress_callback: Progress callback

    Returns:
        GeoJSON FeatureCollection dict.
    """
    features = fetch_all_features(
        LAYER_BOUNDARIES, max_total=100,
        progress_callback=progress_callback
    )

    features = [_normalize_geometry(f) for f in features]

    if industrial_area and features:
        area_upper = industrial_area.upper().strip()
        features = [
            f for f in features
            if area_upper in (f.get("properties", {}).get("industrial", "") or "").upper()
        ]

    return _build_collection(features)


def fetch_and_save(industrial_area: Optional[str] = None,
                   bbox: Optional[tuple] = None,
                   progress_callback=None) -> tuple:
    """
    Fetch both plots and boundaries and save to data/ directory.

    Returns:
        Tuple of (plots_path, boundaries_path, plots_count, boundaries_count)
    """
    plots = fetch_plots(
        industrial_area=industrial_area, bbox=bbox,
        progress_callback=progress_callback
    )
    boundaries = fetch_boundaries(
        industrial_area=industrial_area,
        progress_callback=progress_callback
    )

    plots_path = os.path.join(DATA_DIR, "csidc_live_plots.geojson")
    boundaries_path = os.path.join(DATA_DIR, "csidc_live_boundaries.geojson")

    with open(plots_path, "w", encoding="utf-8") as f:
        json.dump(plots, f, indent=2)

    with open(boundaries_path, "w", encoding="utf-8") as f:
        json.dump(boundaries, f, indent=2)

    n_plots = len(plots.get("features", []))
    n_bounds = len(boundaries.get("features", []))

    return plots_path, boundaries_path, n_plots, n_bounds


def list_industrial_areas(progress_callback=None) -> list:
    """
    Fetch boundary data and return list of unique industrial area names.
    """
    boundaries = fetch_boundaries(progress_callback=progress_callback)
    areas = set()
    for feat in boundaries.get("features", []):
        name = feat.get("properties", {}).get("industrial", "")
        if name:
            areas.add(name)
    return sorted(areas)


def _build_collection(features: list) -> dict:
    """Build a GeoJSON FeatureCollection."""
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
        "features": features,
    }


# ── CLI ────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    def progress(total, batch):
        print(f"  Batch {batch}: {total} features fetched", end="\r")

    print("=" * 60)
    print("🏗️  CSIDC Real-Time WFS Data Fetcher")
    print("=" * 60)

    # List available areas first
    print("\n📋 Fetching available industrial areas...")
    areas = list_industrial_areas(progress_callback=progress)
    print(f"\n✅ Found {len(areas)} industrial areas:")
    for i, area in enumerate(areas, 1):
        print(f"   {i}. {area}")

    # Ask which area
    print("\nEnter area name to filter (or Enter for all):")
    area_input = input("> ").strip() or None

    print("\n🚀 Fetching plot data...")
    plots_path, bounds_path, n_plots, n_bounds = fetch_and_save(
        industrial_area=area_input, progress_callback=progress
    )
    print(f"\n✅ Done!")
    print(f"   📊 Plots: {n_plots} → {plots_path}")
    print(f"   🗺️ Boundaries: {n_bounds} → {bounds_path}")
