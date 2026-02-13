"""
LandGuard AI - Sample Data Generator
Generates synthetic plot polygons, metadata, and mock satellite images
for demonstration and testing purposes.
"""

import json
import os
import random
import numpy as np
import cv2
from shapely.geometry import Polygon, mapping
from shapely.affinity import scale, translate

# ──────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────
CENTER_LAT = 21.2514       # Raipur Industrial Area (CSIDC)
CENTER_LON = 81.6296
NUM_PLOTS = 10
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
IMAGE_DIR = os.path.join(OUTPUT_DIR, "images")
IMG_SIZE = 400             # px per synthetic image

# Violation assignments: plot index → violation type
VIOLATION_MAP = {
    1: "ENCROACHMENT",
    3: "ENCROACHMENT",
    5: "ENCROACHMENT",
    7: "ENCROACHMENT",
    2: "VACANT_PLOT",
    8: "VACANT_PLOT",
    4: "UNAUTHORIZED_CONSTRUCTION",
    9: "BOUNDARY_DEVIATION",
}

random.seed(42)
np.random.seed(42)


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────
def _make_rect_polygon(cx, cy, w, h, jitter=0.0001):
    """Create a slightly irregular rectangular polygon."""
    coords = [
        (cx - w / 2 + random.uniform(-jitter, jitter),
         cy - h / 2 + random.uniform(-jitter, jitter)),
        (cx + w / 2 + random.uniform(-jitter, jitter),
         cy - h / 2 + random.uniform(-jitter, jitter)),
        (cx + w / 2 + random.uniform(-jitter, jitter),
         cy + h / 2 + random.uniform(-jitter, jitter)),
        (cx - w / 2 + random.uniform(-jitter, jitter),
         cy + h / 2 + random.uniform(-jitter, jitter)),
    ]
    return Polygon(coords)


def _generate_grid_centers(n, start_lon, start_lat, cols=5, spacing=0.003):
    """Lay out plot centres on a grid."""
    centres = []
    for i in range(n):
        r, c = divmod(i, cols)
        centres.append((start_lon + c * spacing, start_lat - r * spacing))
    return centres


def _draw_plot_image(poly_coords, img_size, fill_color, border_color,
                     add_buildings=True, violation_type=None):
    """Render a synthetic top-down image of a plot."""
    img = np.full((img_size, img_size, 3), 200, dtype=np.uint8)  # light grey bg

    # Normalise polygon coords to pixel space
    xs = [c[0] for c in poly_coords]
    ys = [c[1] for c in poly_coords]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    pad = 40
    sx = (img_size - 2 * pad) / max(max_x - min_x, 1e-9)
    sy = (img_size - 2 * pad) / max(max_y - min_y, 1e-9)
    s = min(sx, sy)

    pts = np.array([
        [int(pad + (x - min_x) * s), int(pad + (y - min_y) * s)]
        for x, y in poly_coords
    ], dtype=np.int32)

    # Fill plot area
    cv2.fillPoly(img, [pts], fill_color)
    cv2.polylines(img, [pts], True, border_color, 2)

    if add_buildings and violation_type != "VACANT_PLOT":
        # Draw mock building rectangles inside
        bx, by, bw, bh = cv2.boundingRect(pts)
        for _ in range(random.randint(2, 5)):
            rw = random.randint(20, 60)
            rh = random.randint(20, 50)
            rx = random.randint(bx + 10, max(bx + bw - rw - 10, bx + 11))
            ry = random.randint(by + 10, max(by + bh - rh - 10, by + 11))
            cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh),
                          (120, 120, 140), -1)
            cv2.rectangle(img, (rx, ry), (rx + rw, ry + rh),
                          (80, 80, 100), 1)

    if violation_type == "VACANT_PLOT":
        # Draw green vegetation
        for _ in range(30):
            cx_px = random.randint(pad, img_size - pad)
            cy_px = random.randint(pad, img_size - pad)
            r = random.randint(5, 15)
            cv2.circle(img, (cx_px, cy_px), r,
                       (50, random.randint(140, 200), 50), -1)

    if violation_type == "UNAUTHORIZED_CONSTRUCTION":
        # Add a bright red structure outside normal area
        cv2.rectangle(img, (img_size - 100, img_size - 100),
                      (img_size - 30, img_size - 30), (40, 40, 200), -1)
        cv2.putText(img, "UNAUTH", (img_size - 98, img_size - 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

    return img


# ──────────────────────────────────────────────
#  Main Generation
# ──────────────────────────────────────────────
def generate():
    os.makedirs(IMAGE_DIR, exist_ok=True)

    centres = _generate_grid_centers(NUM_PLOTS, CENTER_LON - 0.006,
                                     CENTER_LAT + 0.003)

    ref_features = []
    cur_features = []
    metadata = []

    for idx in range(NUM_PLOTS):
        plot_id = f"P{idx + 1:03d}"
        cx, cy = centres[idx]
        w = random.uniform(0.0015, 0.0025)
        h = random.uniform(0.0012, 0.0020)

        ref_poly = _make_rect_polygon(cx, cy, w, h)
        violation_type = VIOLATION_MAP.get(idx)

        # Build the "current" polygon based on violation type
        if violation_type == "ENCROACHMENT":
            factor = random.uniform(1.08, 1.25)
            cur_poly = scale(ref_poly, xfact=factor, yfact=factor, origin='center')
        elif violation_type == "BOUNDARY_DEVIATION":
            cur_poly = translate(ref_poly,
                                 xoff=random.uniform(0.0003, 0.0006),
                                 yoff=random.uniform(-0.0004, 0.0004))
            cur_poly = scale(cur_poly, xfact=random.uniform(0.85, 0.95),
                             yfact=random.uniform(1.05, 1.15), origin='center')
        elif violation_type in ("VACANT_PLOT", "UNAUTHORIZED_CONSTRUCTION"):
            cur_poly = ref_poly  # boundary unchanged
        else:
            # Compliant – minor jitter only
            cur_poly = scale(ref_poly,
                             xfact=random.uniform(0.98, 1.02),
                             yfact=random.uniform(0.98, 1.02),
                             origin='center')

        # ── GeoJSON features ──
        ref_features.append({
            "type": "Feature",
            "properties": {"plot_id": plot_id, "type": "reference"},
            "geometry": mapping(ref_poly),
        })
        cur_features.append({
            "type": "Feature",
            "properties": {
                "plot_id": plot_id,
                "type": "current",
                "violation_type": violation_type or "COMPLIANT",
            },
            "geometry": mapping(cur_poly),
        })

        # ── Images ──
        ref_img_path = os.path.join(IMAGE_DIR, f"{plot_id}_reference.jpg")
        cur_img_path = os.path.join(IMAGE_DIR, f"{plot_id}_current.jpg")

        ref_img = _draw_plot_image(
            list(ref_poly.exterior.coords), IMG_SIZE,
            fill_color=(180, 210, 180), border_color=(60, 120, 60))
        cur_img = _draw_plot_image(
            list(cur_poly.exterior.coords), IMG_SIZE,
            fill_color=(210, 190, 180), border_color=(160, 60, 60),
            violation_type=violation_type)

        cv2.imwrite(ref_img_path, ref_img)
        cv2.imwrite(cur_img_path, cur_img)

        # ── Metadata ──
        area_sqm = ref_poly.area * 1e10  # rough degree→m² at this latitude
        metadata.append({
            "plot_id": plot_id,
            "reference_image": f"data/images/{plot_id}_reference.jpg",
            "current_image": f"data/images/{plot_id}_current.jpg",
            "coordinates": [round(cy, 6), round(cx, 6)],
            "area_sqm": round(area_sqm, 1),
            "owner": f"Industrial Unit {idx + 1}",
            "allotment_date": f"201{random.randint(0,9)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
            "violation_type": violation_type or "COMPLIANT",
        })

    # ── Write outputs ──
    ref_geojson = {"type": "FeatureCollection", "features": ref_features}
    cur_geojson = {"type": "FeatureCollection", "features": cur_features}

    with open(os.path.join(OUTPUT_DIR, "reference_plots.geojson"), "w") as f:
        json.dump(ref_geojson, f, indent=2)
    with open(os.path.join(OUTPUT_DIR, "current_plots.geojson"), "w") as f:
        json.dump(cur_geojson, f, indent=2)
    with open(os.path.join(OUTPUT_DIR, "plot_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"✅ Generated {NUM_PLOTS} sample plots")
    print(f"   📁 {OUTPUT_DIR}/reference_plots.geojson")
    print(f"   📁 {OUTPUT_DIR}/current_plots.geojson")
    print(f"   📁 {OUTPUT_DIR}/plot_metadata.json")
    print(f"   🖼️  {len(os.listdir(IMAGE_DIR))} images in {IMAGE_DIR}")


if __name__ == "__main__":
    generate()
