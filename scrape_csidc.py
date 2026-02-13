"""
scrape_csidc.py — Fetch real plot polygons and satellite tiles from CSIDC GeoServer.

The CSIDC GeoServer at cggis.cgstate.gov.in requires browser authentication.
This script provides two approaches:

  1. WFS Vector Fetch (preferred)  — gets actual polygon GeoJSON from GeoServer
  2. WMS Tile Composite           — stitches WMS GetMap tiles for the area

Usage:
  1. Open the CSIDC map portal in your browser (https://cggis.cgstate.gov.in/csidc/)
  2. Open DevTools → Network tab → right-click any wmscgcog request → Copy as cURL
  3. The script will extract cookies and headers automatically

  Or manually: press F12 → Application → Cookies → copy the session cookie values
  and paste them when prompted.
"""

import json
import os
import sys
import math
import ssl
import urllib.request
import urllib.parse
from io import BytesIO

import cv2
import numpy as np

# ── Configuration ──────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "csidc_data")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# CSIDC GeoServer base URL (confirmed from user's browser DevTools)
GEOSERVER_BASE = "https://cggis.cgstate.gov.in/giscg/wmscgcog"

# Known layers from DevTools inspection
KNOWN_LAYERS = [
    "CGCOG_DATABASE:csidc_substation_towers",
    "CGCOG_DATABASE:csidc_plot_boundary",
    "CGCOG_DATABASE:csidc_plots",
    "CGCOG_DATABASE:csidc_road",
    "CGCOG_DATABASE:csidc_building",
    "CGCOG_DATABASE:csidc_industrial_area",
    "CGCOG_DATABASE:csidc_land_use",
]

# SSL context for HTTPS (skip verification for gov sites)
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# Browser-like headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://cggis.cgstate.gov.in/csidc/",
    "Origin": "https://cggis.cgstate.gov.in",
}


# ── Helpers ─────────────────────────────────────────────────

def make_request(url, headers=None, cookies=None, timeout=30):
    """Make HTTP request with proper headers and cookie support."""
    hdrs = {**DEFAULT_HEADERS}
    if headers:
        hdrs.update(headers)
    if cookies:
        hdrs["Cookie"] = cookies

    req = urllib.request.Request(url, headers=hdrs)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX)
        return resp.read(), resp.status
    except urllib.error.HTTPError as e:
        return e.read(), e.code
    except Exception as e:
        print(f"  ❌ Request failed: {e}")
        return None, 0


def extract_cookies_from_curl(curl_cmd):
    """Extract cookies from a curl command string."""
    import re
    # Match -H 'Cookie: ...' or --header 'Cookie: ...'
    match = re.search(r"(?:-H|--header)\s+['\"]Cookie:\s*([^'\"]+)['\"]", curl_cmd)
    if match:
        return match.group(1)
    # Match -b '...' or --cookie '...'
    match = re.search(r"(?:-b|--cookie)\s+['\"]([^'\"]+)['\"]", curl_cmd)
    if match:
        return match.group(1)
    return None


# ── WFS Feature Fetcher ─────────────────────────────────────

def discover_layers_wfs(cookies=None):
    """Try to get WFS capabilities and list available feature types."""
    print("\n🔍 Discovering WFS layers...")

    # Try different WFS endpoint patterns
    wfs_urls = [
        GEOSERVER_BASE + "?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities",
        GEOSERVER_BASE + "?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetCapabilities",
        GEOSERVER_BASE.replace("wmscgcog", "wfscgcog") + "?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetCapabilities",
        GEOSERVER_BASE.replace("wmscgcog", "ows") + "?SERVICE=WFS&VERSION=1.1.0&REQUEST=GetCapabilities",
    ]

    for url in wfs_urls:
        data, status = make_request(url, cookies=cookies)
        if data and status == 200 and b"FeatureType" in data:
            print(f"  ✅ WFS endpoint found: {url[:80]}")

            # Parse layer names
            import re
            layers = re.findall(r"<Name>([^<]+)</Name>", data.decode("utf-8", errors="replace"))
            if layers:
                print(f"  📋 Available layers ({len(layers)}):")
                for layer in layers:
                    print(f"     • {layer}")
                return layers, url.split("?")[0]

    print("  ⚠️ WFS not available — will use WMS approach")
    return [], None


def fetch_features_wfs(layer_name, bbox=None, cookies=None, wfs_base=None):
    """Fetch vector features from a WFS layer as GeoJSON."""
    base = wfs_base or GEOSERVER_BASE
    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": layer_name,
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:4326",
        "MAXFEATURES": "5000",
    }
    if bbox:
        params["BBOX"] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:4326"

    url = base + "?" + urllib.parse.urlencode(params)
    print(f"\n📥 Fetching WFS features from {layer_name}...")
    print(f"   URL: {url[:120]}...")

    data, status = make_request(url, cookies=cookies)
    if data and status == 200:
        try:
            geojson = json.loads(data)
            n = len(geojson.get("features", []))
            print(f"  ✅ Got {n} features!")
            return geojson
        except json.JSONDecodeError:
            text = data.decode("utf-8", errors="replace")[:200]
            print(f"  ⚠️ Not JSON: {text}")
    else:
        print(f"  ❌ HTTP {status}")

    return None


# ── WMS Capabilities ────────────────────────────────────────

def discover_layers_wms(cookies=None):
    """Try to get WMS capabilities and list available layers."""
    print("\n🔍 Discovering WMS layers...")

    url = GEOSERVER_BASE + "?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetCapabilities"
    data, status = make_request(url, cookies=cookies)

    if data and status == 200:
        text = data.decode("utf-8", errors="replace")
        if "<Layer" in text or "WMS_Capabilities" in text:
            import re
            layers = re.findall(r"<Name>([^<]+)</Name>", text)
            if layers:
                print(f"  ✅ Found {len(layers)} WMS layers:")
                for layer in layers:
                    if "CGCOG" in layer or "csidc" in layer.lower():
                        print(f"     • {layer}")
                return layers

    print("  ⚠️ Could not get WMS capabilities")
    return []


# ── WMS Tile Fetcher ────────────────────────────────────────

def fetch_wms_tile(layer, bbox, width=512, height=512, cookies=None):
    """Fetch a single WMS GetMap tile for the given BBOX."""
    params = {
        "REQUEST": "GetMap",
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "FORMAT": "image/png; mode=8bit",
        "STYLES": "",
        "TRANSPARENT": "TRUE",
        "LAYERS": layer,
        "TILED": "true",
        "SRS": "EPSG:4326",
        "CRS": "EPSG:4326",
        "FORMAT_OPTIONS": "dpi:113",
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "BBOX": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}",
    }

    url = GEOSERVER_BASE + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    data, status = make_request(url, cookies=cookies)

    if data and status == 200 and len(data) > 500:
        # Convert PNG bytes to numpy array
        nparr = np.frombuffer(data, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_UNCHANGED)
        return img, data

    return None, None


def fetch_area_tiles(layer, area_bbox, grid_size=4, cookies=None):
    """
    Fetch a grid of WMS tiles covering the area and stitch them.
    area_bbox = (min_lat, min_lon, max_lat, max_lon) in EPSG:4326
    """
    min_lat, min_lon, max_lat, max_lon = area_bbox
    lat_step = (max_lat - min_lat) / grid_size
    lon_step = (max_lon - min_lon) / grid_size

    tile_w, tile_h = 512, 512
    stitched = np.zeros((grid_size * tile_h, grid_size * tile_w, 4), dtype=np.uint8)
    fetched = 0

    print(f"\n🗺️ Fetching {grid_size}×{grid_size} WMS tile grid for {layer}...")
    for row in range(grid_size):
        for col in range(grid_size):
            tile_min_lat = min_lat + row * lat_step
            tile_max_lat = min_lat + (row + 1) * lat_step
            tile_min_lon = min_lon + col * lon_step
            tile_max_lon = min_lon + (col + 1) * lon_step

            tile_bbox = (tile_min_lat, tile_min_lon, tile_max_lat, tile_max_lon)
            img, _ = fetch_wms_tile(layer, tile_bbox, tile_w, tile_h, cookies=cookies)

            if img is not None:
                # WMS returns BGRA (transparent PNG)
                if img.ndim == 2:
                    img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
                elif img.shape[2] == 3:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)

                y_pos = (grid_size - 1 - row) * tile_h  # flip Y (lat goes up)
                x_pos = col * tile_w
                stitched[y_pos:y_pos+tile_h, x_pos:x_pos+tile_w] = img[:tile_h, :tile_w]
                fetched += 1
                print(f"  ✅ Tile [{row},{col}] fetched")
            else:
                print(f"  ❌ Tile [{row},{col}] failed")

    print(f"  📊 Fetched {fetched}/{grid_size**2} tiles")
    return stitched if fetched > 0 else None


# ── Polygon Extraction from WMS tiles ───────────────────────

def extract_polygons_from_overlay(img, area_bbox):
    """
    Extract polygon geometries from a WMS overlay tile (transparent PNG).
    The colored/filled regions on the transparent background are the plot polygons.
    Returns GeoJSON features.
    """
    if img is None or img.ndim < 3:
        return []

    min_lat, min_lon, max_lat, max_lon = area_bbox
    h, w = img.shape[:2]

    # Get alpha channel — non-transparent pixels are features
    if img.shape[2] == 4:
        alpha = img[:, :, 3]
    else:
        # If no alpha, use color-based detection
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        alpha = (gray > 10).astype(np.uint8) * 255

    # Threshold and find contours
    _, thresh = cv2.threshold(alpha, 30, 255, cv2.THRESH_BINARY)

    # Clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    features = []
    min_area = w * h * 0.0005  # at least 0.05% of image

    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        # Simplify contour
        epsilon = 0.01 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) < 3:
            continue

        # Convert pixel coords to geographic coords
        geo_coords = []
        for pt in approx:
            px, py = pt[0]
            lon = min_lon + (px / w) * (max_lon - min_lon)
            lat = max_lat - (py / h) * (max_lat - min_lat)
            geo_coords.append([round(lon, 8), round(lat, 8)])

        # Close polygon
        if geo_coords[0] != geo_coords[-1]:
            geo_coords.append(geo_coords[0])

        features.append({
            "type": "Feature",
            "properties": {
                "plot_id": f"CSIDC_PLOT_{i+1}",
                "source": "CSIDC GeoServer WMS",
                "area_px": int(area),
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [geo_coords]
            }
        })

    return features


# ── Main Pipeline ───────────────────────────────────────────

def run(cookies=None, area_bbox=None, layers_to_try=None):
    """
    Main scraping pipeline:
    1. Try WFS to get vector polygons directly
    2. Fall back to WMS tile fetch → polygon extraction
    3. Save everything as GeoJSON
    """
    print("=" * 60)
    print("🏗️ CSIDC GeoServer Plot Data Scraper")
    print("=" * 60)

    # Default area from user's screenshot (BBOX from DevTools)
    if area_bbox is None:
        area_bbox = (22.975034, 82.908560, 22.983873, 82.913568)

    if layers_to_try is None:
        layers_to_try = KNOWN_LAYERS

    all_features = []

    # ── Step 1: Try WFS ──
    wfs_layers, wfs_base = discover_layers_wfs(cookies)
    if wfs_layers:
        for layer in wfs_layers:
            if "plot" in layer.lower() or "boundary" in layer.lower() or "building" in layer.lower():
                geojson = fetch_features_wfs(layer, bbox=area_bbox, cookies=cookies,
                                             wfs_base=wfs_base)
                if geojson and geojson.get("features"):
                    all_features.extend(geojson["features"])
                    print(f"  ✅ Added {len(geojson['features'])} features from {layer}")

    # ── Step 2: Try WMS GetCapabilities to find layers ──
    if not all_features:
        wms_layers = discover_layers_wms(cookies)
        if wms_layers:
            layers_to_try = [l for l in wms_layers
                             if "CGCOG" in l or "csidc" in l.lower()]
            if not layers_to_try:
                layers_to_try = wms_layers[:10]

    # ── Step 3: WMS tile fetching and polygon extraction ──
    if not all_features:
        print("\n🗺️ Falling back to WMS tile → polygon extraction...")

        for layer in layers_to_try:
            print(f"\n  Trying layer: {layer}")
            overlay = fetch_area_tiles(layer, area_bbox, grid_size=3, cookies=cookies)

            if overlay is not None:
                # Save the stitched overlay
                out_img = os.path.join(OUTPUT_DIR, f"{layer.replace(':', '_')}_overlay.png")
                cv2.imwrite(out_img, overlay)
                print(f"  💾 Saved overlay: {out_img}")

                # Extract polygons from the overlay
                features = extract_polygons_from_overlay(overlay, area_bbox)
                if features:
                    all_features.extend(features)
                    print(f"  ✅ Extracted {len(features)} polygons from {layer}")
                else:
                    print(f"  ⚠️ No polygons found in {layer} overlay")

    # ── Step 4: Save combined GeoJSON ──
    if all_features:
        geojson = {
            "type": "FeatureCollection",
            "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
            "features": all_features,
        }

        out_path = os.path.join(DATA_DIR, "csidc_real_plots.geojson")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(geojson, f, indent=2)
        print(f"\n✅ Saved {len(all_features)} features to {out_path}")
        print(f"   Use this file in the Plot Analysis tab!")
        return out_path
    else:
        print("\n⚠️ No features extracted. Possible reasons:")
        print("   1. Server requires authentication — paste browser cookies")
        print("   2. WFS is disabled — need to use WMS overlay approach")
        print("   3. Layer names are different — check DevTools for actual names")
        return None


# ── Interactive mode ─────────────────────────────────────────

if __name__ == "__main__":
    print("🏗️ CSIDC Plot Data Scraper")
    print("-" * 40)
    print("\nTo authenticate, you have two options:")
    print("  1. Paste the Cookie header value from DevTools")
    print("  2. Press Enter to try without cookies\n")

    cookie_input = input("Cookie value (or Enter to skip): ").strip()
    cookies = cookie_input if cookie_input else None

    print("\nEnter the area BBOX (from DevTools Network → Payload → BBOX)")
    print("Format: min_lat,min_lon,max_lat,max_lon")
    print("Example: 22.975034,82.908560,22.983873,82.913568")
    bbox_input = input("BBOX (or Enter for default): ").strip()

    if bbox_input:
        parts = [float(x) for x in bbox_input.split(",")]
        area_bbox = tuple(parts[:4])
    else:
        area_bbox = None

    print("\nEnter layer names to try (comma-separated, from DevTools LAYERS param)")
    print("Example: CGCOG_DATABASE:csidc_substation_towers")
    layer_input = input("Layers (or Enter for all known): ").strip()

    layers = None
    if layer_input:
        layers = [l.strip() for l in layer_input.split(",")]

    run(cookies=cookies, area_bbox=area_bbox, layers_to_try=layers)
