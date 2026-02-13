"""
LandGuard AI - Boundary Detection Script
Detects plot boundaries from aerial/satellite images using OpenCV contour
detection (lightweight) with optional SAM integration.
"""

import json
import os
import sys
import cv2
import numpy as np
from shapely.geometry import Polygon, mapping

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
IMAGE_DIR = os.path.join(DATA_DIR, "images")


# ──────────────────────────────────────────────
#  OpenCV Contour-Based Detection
# ──────────────────────────────────────────────
def detect_contours(image_path, min_area=500, simplify_epsilon=0.02):
    """
    Detect plot boundaries using OpenCV contour detection.

    Args:
        image_path: Path to the aerial/satellite image.
        min_area: Minimum contour area in pixels to keep.
        simplify_epsilon: Contour approximation tolerance (relative to perimeter).

    Returns:
        List of polygons as coordinate lists.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"⚠️  Cannot read image: {image_path}")
        return []

    # Preprocessing pipeline
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Adaptive thresholding for varying lighting
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # Morphological operations to clean up
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    # Find contours
    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    polygons = []
    h, w = img.shape[:2]

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        # Simplify contour
        epsilon = simplify_epsilon * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)

        if len(approx) < 3:
            continue

        # Convert to normalised coordinates [0, 1]
        coords = [(pt[0][0] / w, pt[0][1] / h) for pt in approx]
        coords.append(coords[0])  # close polygon
        polygons.append(coords)

    return polygons


def detect_edges_canny(image_path, min_area=500):
    """Alternative: Canny edge-based boundary detection."""
    img = cv2.imread(image_path)
    if img is None:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=2)

    contours, _ = cv2.findContours(
        dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = img.shape[:2]
    polygons = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_area:
            continue
        epsilon = 0.02 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        if len(approx) >= 3:
            coords = [(pt[0][0] / w, pt[0][1] / h) for pt in approx]
            coords.append(coords[0])
            polygons.append(coords)
    return polygons


# ──────────────────────────────────────────────
#  Coordinate Mapping
# ──────────────────────────────────────────────
def pixel_to_geo(polygons, bbox):
    """
    Convert normalised pixel coordinates to geographic coordinates.

    Args:
        polygons: List of polygon coord lists in [0,1] space.
        bbox: (min_lon, min_lat, max_lon, max_lat) bounding box.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    geo_polygons = []
    for poly in polygons:
        geo_coords = [
            (min_lon + x * (max_lon - min_lon),
             min_lat + y * (max_lat - min_lat))
            for x, y in poly
        ]
        geo_polygons.append(geo_coords)
    return geo_polygons


# ──────────────────────────────────────────────
#  GeoJSON Output
# ──────────────────────────────────────────────
def save_as_geojson(polygons, output_path, id_prefix="DET"):
    """Save detected polygons as a GeoJSON FeatureCollection."""
    features = []
    for i, coords in enumerate(polygons):
        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty:
                continue
            features.append({
                "type": "Feature",
                "properties": {
                    "plot_id": f"{id_prefix}{i+1:03d}",
                    "detection_method": "opencv_contour",
                    "area_px_norm": round(poly.area, 6),
                },
                "geometry": mapping(poly),
            })
        except Exception as e:
            print(f"⚠️  Skipping invalid polygon {i}: {e}")

    geojson = {"type": "FeatureCollection", "features": features}
    with open(output_path, "w") as f:
        json.dump(geojson, f, indent=2)

    print(f"✅ Saved {len(features)} polygons to {output_path}")
    return geojson


def create_annotated_image(image_path, polygons, output_path):
    """Draw detected boundaries overlaid on the original image."""
    img = cv2.imread(image_path)
    if img is None:
        return
    h, w = img.shape[:2]
    overlay = img.copy()

    for poly_coords in polygons:
        pts = np.array(
            [(int(x * w), int(y * h)) for x, y in poly_coords],
            dtype=np.int32,
        )
        cv2.fillPoly(overlay, [pts], (0, 255, 0, 80))
        cv2.polylines(img, [pts], True, (0, 255, 0), 2)

    result = cv2.addWeighted(overlay, 0.3, img, 0.7, 0)
    cv2.imwrite(output_path, result)
    print(f"✅ Annotated image saved to {output_path}")


# ──────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────
def run():
    """Process all images in the data/images directory."""
    if not os.path.exists(IMAGE_DIR):
        print("❌  Image directory not found. Run generate_sample_data.py first.")
        sys.exit(1)

    metadata_path = os.path.join(DATA_DIR, "plot_metadata.json")
    with open(metadata_path) as f:
        metadata = json.load(f)

    print("🔍 Detecting plot boundaries from images...\n")

    ref_all_polygons = []
    cur_all_polygons = []

    for plot in metadata:
        pid = plot["plot_id"]
        ref_img = os.path.join(BASE_DIR, plot["reference_image"])
        cur_img = os.path.join(BASE_DIR, plot["current_image"])

        if os.path.exists(ref_img):
            ref_polys = detect_contours(ref_img)
            print(f"  {pid} reference: {len(ref_polys)} boundary detected")

            # Create annotated image
            annotated_path = os.path.join(IMAGE_DIR, f"{pid}_reference_annotated.jpg")
            create_annotated_image(ref_img, ref_polys, annotated_path)

            for p in ref_polys:
                ref_all_polygons.append({"plot_id": pid, "coords": p})

        if os.path.exists(cur_img):
            cur_polys = detect_contours(cur_img)
            print(f"  {pid} current:   {len(cur_polys)} boundary detected")

            annotated_path = os.path.join(IMAGE_DIR, f"{pid}_current_annotated.jpg")
            create_annotated_image(cur_img, cur_polys, annotated_path)

            for p in cur_polys:
                cur_all_polygons.append({"plot_id": pid, "coords": p})

    # Save detected boundaries as GeoJSON
    if ref_all_polygons:
        save_as_geojson(
            [p["coords"] for p in ref_all_polygons],
            os.path.join(DATA_DIR, "detected_reference.geojson"),
            id_prefix="DREF",
        )
    if cur_all_polygons:
        save_as_geojson(
            [p["coords"] for p in cur_all_polygons],
            os.path.join(DATA_DIR, "detected_current.geojson"),
            id_prefix="DCUR",
        )

    print(f"\n✅ Boundary detection complete")
    print(f"   Reference boundaries: {len(ref_all_polygons)}")
    print(f"   Current boundaries:   {len(cur_all_polygons)}")


if __name__ == "__main__":
    run()
