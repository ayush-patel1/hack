"""
LandGuard AI - Polygon-Based Change Detection
Uses satellite data (Sentinel-1 SAR + Sentinel-2 Optical) to detect
real changes within provided plot allotment polygons.

Supports:
  - SAR backscatter change (construction/demolition detection)
  - NDVI change (vegetation gain/loss → vacant plot detection)
  - NDBI change (built-up area increase → encroachment detection)
  - Image-based change detection using OpenCV on downloaded tiles
"""

import json
import os
import sys
from datetime import datetime

import cv2
import numpy as np
from shapely.geometry import shape, mapping


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
SAT_DIR = os.path.join(DATA_DIR, "satellite")

# ──────────────────────────────────────────────
#  Thresholds for satellite-based change detection
# ──────────────────────────────────────────────
SAR_CHANGE_THRESHOLD_DB = 3.0       # dB change in VV backscatter
NDVI_VACANT_THRESHOLD = 0.4         # High NDVI = vegetation = vacant
NDVI_CHANGE_THRESHOLD = 0.15        # Significant NDVI shift
NDBI_CONSTRUCTION_THRESHOLD = 0.1   # Positive NDBI = built-up
NDBI_CHANGE_THRESHOLD = 0.1         # Significant NDBI increase
IMAGE_CHANGE_THRESHOLD = 0.15       # 15% pixel change in tile comparison


# ──────────────────────────────────────────────
#  SAR-Based Change Detection
# ──────────────────────────────────────────────
def detect_sar_change(ref_stats, cur_stats):
    """
    Detect change using Sentinel-1 SAR backscatter difference.

    Increase in backscatter → new structures (construction)
    Decrease in backscatter → structures removed

    Args:
        ref_stats: {"VV": {"mean": float, "std": float}}
        cur_stats: {"VV": {"mean": float, "std": float}}

    Returns:
        dict with change metrics.
    """
    if not ref_stats or not cur_stats:
        return {"method": "SAR", "available": False}

    ref_vv = ref_stats.get("VV", {}).get("mean")
    cur_vv = cur_stats.get("VV", {}).get("mean")

    if ref_vv is None or cur_vv is None:
        return {"method": "SAR", "available": False}

    change_db = cur_vv - ref_vv  # dB difference
    abs_change = abs(change_db)

    result = {
        "method": "SAR",
        "available": True,
        "ref_backscatter_db": round(ref_vv, 2),
        "cur_backscatter_db": round(cur_vv, 2),
        "change_db": round(change_db, 2),
        "significant_change": abs_change > SAR_CHANGE_THRESHOLD_DB,
    }

    if change_db > SAR_CHANGE_THRESHOLD_DB:
        result["interpretation"] = "NEW_CONSTRUCTION"
        result["confidence"] = min(abs_change / 10.0, 1.0)
    elif change_db < -SAR_CHANGE_THRESHOLD_DB:
        result["interpretation"] = "STRUCTURE_REMOVED"
        result["confidence"] = min(abs_change / 10.0, 1.0)
    else:
        result["interpretation"] = "NO_CHANGE"
        result["confidence"] = 1.0 - (abs_change / SAR_CHANGE_THRESHOLD_DB)

    return result


# ──────────────────────────────────────────────
#  NDVI-Based Vacancy Detection
# ──────────────────────────────────────────────
def detect_ndvi_change(ref_stats, cur_stats):
    """
    Detect vegetation changes using NDVI.

    High current NDVI + low NDBI → likely vacant/unused land.
    NDVI decrease + NDBI increase → construction activity.
    """
    if not ref_stats or not cur_stats:
        return {"method": "NDVI", "available": False}

    ref_ndvi = ref_stats.get("NDVI", {}).get("mean")
    cur_ndvi = cur_stats.get("NDVI", {}).get("mean")

    if ref_ndvi is None or cur_ndvi is None:
        return {"method": "NDVI", "available": False}

    ndvi_change = cur_ndvi - ref_ndvi

    result = {
        "method": "NDVI",
        "available": True,
        "ref_ndvi": round(ref_ndvi, 4),
        "cur_ndvi": round(cur_ndvi, 4),
        "ndvi_change": round(ndvi_change, 4),
        "is_vegetated": cur_ndvi > NDVI_VACANT_THRESHOLD,
        "significant_change": abs(ndvi_change) > NDVI_CHANGE_THRESHOLD,
    }

    if cur_ndvi > NDVI_VACANT_THRESHOLD:
        result["interpretation"] = "LIKELY_VACANT"
        result["confidence"] = min(cur_ndvi / 0.8, 1.0)
    elif ndvi_change < -NDVI_CHANGE_THRESHOLD:
        result["interpretation"] = "VEGETATION_CLEARED"
        result["confidence"] = min(abs(ndvi_change) / 0.3, 1.0)
    elif ndvi_change > NDVI_CHANGE_THRESHOLD:
        result["interpretation"] = "VEGETATION_GROWTH"
        result["confidence"] = min(ndvi_change / 0.3, 1.0)
    else:
        result["interpretation"] = "STABLE"
        result["confidence"] = 1.0

    return result


# ──────────────────────────────────────────────
#  NDBI-Based Built-Up Detection
# ──────────────────────────────────────────────
def detect_ndbi_change(ref_stats, cur_stats):
    """
    Detect built-up area changes using NDBI.

    Increasing NDBI → more construction / encroachment.
    """
    if not ref_stats or not cur_stats:
        return {"method": "NDBI", "available": False}

    ref_ndbi = ref_stats.get("NDBI", {}).get("mean")
    cur_ndbi = cur_stats.get("NDBI", {}).get("mean")

    if ref_ndbi is None or cur_ndbi is None:
        return {"method": "NDBI", "available": False}

    ndbi_change = cur_ndbi - ref_ndbi

    result = {
        "method": "NDBI",
        "available": True,
        "ref_ndbi": round(ref_ndbi, 4),
        "cur_ndbi": round(cur_ndbi, 4),
        "ndbi_change": round(ndbi_change, 4),
        "is_built_up": cur_ndbi > NDBI_CONSTRUCTION_THRESHOLD,
        "significant_change": abs(ndbi_change) > NDBI_CHANGE_THRESHOLD,
    }

    if ndbi_change > NDBI_CHANGE_THRESHOLD:
        result["interpretation"] = "CONSTRUCTION_INCREASE"
        result["confidence"] = min(ndbi_change / 0.3, 1.0)
    elif ndbi_change < -NDBI_CHANGE_THRESHOLD:
        result["interpretation"] = "CONSTRUCTION_DECREASE"
        result["confidence"] = min(abs(ndbi_change) / 0.3, 1.0)
    else:
        result["interpretation"] = "STABLE"
        result["confidence"] = 1.0

    return result


# ──────────────────────────────────────────────
#  Image Tile Change Detection (OpenCV)
# ──────────────────────────────────────────────
def detect_tile_change(ref_tile_path, cur_tile_path):
    """
    Pixel-level change detection between reference and current satellite tiles.
    Uses structural similarity and absolute difference.
    """
    if not ref_tile_path or not cur_tile_path:
        return {"method": "TILE_DIFF", "available": False}
    if not os.path.exists(ref_tile_path) or not os.path.exists(cur_tile_path):
        return {"method": "TILE_DIFF", "available": False}

    ref = cv2.imread(ref_tile_path, cv2.IMREAD_GRAYSCALE)
    cur = cv2.imread(cur_tile_path, cv2.IMREAD_GRAYSCALE)

    if ref is None or cur is None:
        return {"method": "TILE_DIFF", "available": False}

    # Resize to same dimensions
    h, w = 256, 256
    ref = cv2.resize(ref, (w, h))
    cur = cv2.resize(cur, (w, h))

    # Absolute difference
    diff = cv2.absdiff(ref, cur)
    _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

    change_pct = np.count_nonzero(thresh) / (h * w)

    # Structural Similarity (manual — avoids scikit-image dep for speed)
    ref_f = ref.astype(np.float64)
    cur_f = cur.astype(np.float64)
    mean_ref, mean_cur = ref_f.mean(), cur_f.mean()
    std_ref, std_cur = ref_f.std(), cur_f.std()
    cov = ((ref_f - mean_ref) * (cur_f - mean_cur)).mean()
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    ssim = ((2 * mean_ref * mean_cur + c1) * (2 * cov + c2)) / \
           ((mean_ref ** 2 + mean_cur ** 2 + c1) * (std_ref ** 2 + std_cur ** 2 + c2))

    # Save change mask
    diff_dir = os.path.join(SAT_DIR, "change_masks")
    os.makedirs(diff_dir, exist_ok=True)
    base = os.path.basename(ref_tile_path).replace("_reference", "").replace("_current", "")
    diff_path = os.path.join(diff_dir, f"change_{base}")

    # Create colour-coded change map
    change_map = np.zeros((h, w, 3), dtype=np.uint8)
    change_map[thresh > 0] = (0, 0, 255)  # Red for changes
    change_map[thresh == 0] = (0, 100, 0)  # Dark green for stable
    cv2.imwrite(diff_path, change_map)

    return {
        "method": "TILE_DIFF",
        "available": True,
        "change_pct": round(float(change_pct * 100), 2),
        "ssim": round(float(ssim), 4),
        "significant_change": bool(change_pct > IMAGE_CHANGE_THRESHOLD),
        "change_mask_path": diff_path,
    }


# ──────────────────────────────────────────────
#  Combined Change Analysis Per Plot
# ──────────────────────────────────────────────
def classify_violation_from_satellite(sar, ndvi, ndbi, tile_diff):
    """
    Combine all satellite change indicators to classify violation type.
    """
    violation_type = None
    severity = "LOW"
    confidence_scores = []

    # Rule 1: High NDVI + no construction → VACANT_PLOT
    if ndvi.get("available") and ndvi.get("is_vegetated"):
        if not ndbi.get("is_built_up", True):
            violation_type = "VACANT_PLOT"
            confidence_scores.append(ndvi.get("confidence", 0.5))

    # Rule 2: SAR increase + NDBI increase → UNAUTHORIZED_CONSTRUCTION or ENCROACHMENT
    if sar.get("available") and sar.get("interpretation") == "NEW_CONSTRUCTION":
        if ndbi.get("available") and ndbi.get("interpretation") == "CONSTRUCTION_INCREASE":
            violation_type = "UNAUTHORIZED_CONSTRUCTION"
            confidence_scores.extend([sar.get("confidence", 0.5),
                                       ndbi.get("confidence", 0.5)])
        else:
            violation_type = "ENCROACHMENT"
            confidence_scores.append(sar.get("confidence", 0.5))

    # Rule 3: Pixel-level change but no SAR/NDBI confirmation → BOUNDARY_DEVIATION
    if tile_diff.get("available") and tile_diff.get("significant_change"):
        if violation_type is None:
            violation_type = "BOUNDARY_DEVIATION"
            confidence_scores.append(0.6)

    # Determine severity from change magnitudes
    if violation_type:
        change_magnitude = max(
            abs(sar.get("change_db", 0)) / 10.0 if sar.get("available") else 0,
            abs(ndvi.get("ndvi_change", 0)) / 0.3 if ndvi.get("available") else 0,
            abs(ndbi.get("ndbi_change", 0)) / 0.3 if ndbi.get("available") else 0,
            tile_diff.get("change_pct", 0) / 50.0 if tile_diff.get("available") else 0,
        )

        if change_magnitude > 0.7:
            severity = "CRITICAL"
        elif change_magnitude > 0.5:
            severity = "HIGH"
        elif change_magnitude > 0.3:
            severity = "MEDIUM"
        else:
            severity = "LOW"

    avg_confidence = (sum(confidence_scores) / len(confidence_scores)
                      if confidence_scores else 0)

    return {
        "violation_type": violation_type or "COMPLIANT",
        "severity": severity if violation_type else None,
        "confidence": round(avg_confidence, 3),
        "satellite_evidence": {
            "sar": sar,
            "ndvi": ndvi,
            "ndbi": ndbi,
            "tile_diff": {k: v for k, v in tile_diff.items() if k != "change_mask_path"},
        },
    }


# ──────────────────────────────────────────────
#  Main Pipeline
# ──────────────────────────────────────────────
def run(plots_geojson=None, satellite_data_path=None):
    """
    Run change detection on all plots using satellite data.
    If satellite_data.json exists, uses real GEE data.
    Otherwise, falls back to image-based comparison of local tiles.
    """
    plots_geojson = plots_geojson or os.path.join(DATA_DIR, "reference_plots.geojson")
    satellite_data_path = satellite_data_path or os.path.join(SAT_DIR, "satellite_data.json")

    if not os.path.exists(plots_geojson):
        print("[ERROR] Plot GeoJSON not found.")
        sys.exit(1)

    with open(plots_geojson) as f:
        plots = json.load(f)

    # Load satellite stats if available
    sat_data = {}
    if os.path.exists(satellite_data_path):
        with open(satellite_data_path) as f:
            sat_data = json.load(f)
        print("[INFO] Using real satellite data from GEE")
    else:
        print("[INFO] No satellite data found — using image-based fallback")

    ref_s1_stats = sat_data.get("reference", {}).get("s1_stats", {})
    cur_s1_stats = sat_data.get("current", {}).get("s1_stats", {})
    ref_s2_stats = sat_data.get("reference", {}).get("s2_stats", {})
    cur_s2_stats = sat_data.get("current", {}).get("s2_stats", {})
    ref_s1_tiles = sat_data.get("reference", {}).get("s1_tiles", {})
    cur_s1_tiles = sat_data.get("current", {}).get("s1_tiles", {})

    print(f"\n{'=' * 60}")
    print("LandGuard AI — Satellite Change Detection")
    print(f"{'=' * 60}\n")

    results = []

    for feat in plots["features"]:
        pid = feat["properties"].get("plot_id", "unknown")
        geom = shape(feat["geometry"])

        # Gather per-plot satellite evidence
        sar = detect_sar_change(
            ref_s1_stats.get(pid, {}),
            cur_s1_stats.get(pid, {}),
        )
        ndvi = detect_ndvi_change(
            ref_s2_stats.get(pid, {}),
            cur_s2_stats.get(pid, {}),
        )
        ndbi = detect_ndbi_change(
            ref_s2_stats.get(pid, {}),
            cur_s2_stats.get(pid, {}),
        )
        tile_diff = detect_tile_change(
            ref_s1_tiles.get(pid),
            cur_s1_tiles.get(pid),
        )

        # Also try local image comparison as fallback
        if not tile_diff.get("available"):
            ref_img = os.path.join(DATA_DIR, "images", f"{pid}_reference.jpg")
            cur_img = os.path.join(DATA_DIR, "images", f"{pid}_current.jpg")
            tile_diff = detect_tile_change(ref_img, cur_img)

        classification = classify_violation_from_satellite(sar, ndvi, ndbi, tile_diff)

        result = {
            "plot_id": pid,
            "geometry": mapping(geom),
            **classification,
        }
        results.append(result)

        status = classification["violation_type"]
        icon = {"COMPLIANT": "[OK]", "ENCROACHMENT": "[!!]",
                "VACANT_PLOT": "[VP]", "UNAUTHORIZED_CONSTRUCTION": "[UC]",
                "BOUNDARY_DEVIATION": "[BD]"}.get(status, "[??]")
        print(f"  {icon} {pid}: {status} "
              f"(confidence: {classification['confidence']:.0%})")

    # Save results
    features_out = []
    for r in results:
        geom = r.pop("geometry")
        # Remove non-serializable paths from satellite evidence
        sat_ev = r.get("satellite_evidence", {})
        tile_d = sat_ev.get("tile_diff", {})
        tile_d.pop("change_mask_path", None)
        features_out.append({
            "type": "Feature",
            "geometry": geom,
            "properties": r,
        })

    output = {
        "type": "FeatureCollection",
        "features": features_out,
    }

    output_path = os.path.join(DATA_DIR, "satellite_changes.geojson")
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, cls=NumpyEncoder)

    violations = [r for r in output["features"]
                  if r["properties"]["violation_type"] != "COMPLIANT"]
    print(f"\n{'=' * 60}")
    print(f"[OK] Change detection complete")
    print(f"     Total plots: {len(output['features'])}")
    print(f"     Satellite violations detected: {len(violations)}")
    print(f"     Output: {output_path}")

    return output


if __name__ == "__main__":
    run()
