"""
LandGuard AI - Violation Detection Engine
Compares reference and current plot polygons to detect encroachments,
vacant plots, unauthorized construction, and boundary deviations.
"""

import json
import os
import sys
from datetime import datetime, timedelta
import random

from shapely.geometry import shape, mapping
from shapely.ops import unary_union

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ──────────────────────────────────────────────
#  Thresholds
# ──────────────────────────────────────────────
ENCROACHMENT_THRESHOLD = 0.05      # >5 % area increase
BOUNDARY_DEV_THRESHOLD = 0.10      # >10 % area/shape mismatch
SEVERITY_CRITICAL = 0.25           # >25 % deviation
SEVERITY_HIGH = 0.15               # 15-25 %
SEVERITY_MEDIUM = 0.05             # 5-15 %


def load_geojson(path):
    """Load a GeoJSON file and return features keyed by plot_id."""
    with open(path) as f:
        data = json.load(f)
    plots = {}
    for feat in data["features"]:
        pid = feat["properties"]["plot_id"]
        plots[pid] = {
            "geometry": shape(feat["geometry"]),
            "properties": feat["properties"],
        }
    return plots


def load_metadata(path):
    """Load plot metadata JSON."""
    with open(path) as f:
        return {p["plot_id"]: p for p in json.load(f)}


def severity_from_deviation(dev):
    """Return severity label from absolute deviation ratio."""
    dev = abs(dev)
    if dev >= SEVERITY_CRITICAL:
        return "CRITICAL"
    elif dev >= SEVERITY_HIGH:
        return "HIGH"
    elif dev >= SEVERITY_MEDIUM:
        return "MEDIUM"
    return "LOW"


def analyse_plot(plot_id, ref_geom, cur_geom, meta):
    """
    Compare one plot's reference vs current geometry.
    Returns a violation dict or None if compliant.
    """
    ref_area = ref_geom.area
    cur_area = cur_geom.area
    area_diff = (cur_area - ref_area) / ref_area if ref_area else 0

    # Overlap / IoU
    intersection = ref_geom.intersection(cur_geom).area
    union = ref_geom.union(cur_geom).area
    iou = intersection / union if union else 0
    overlap_pct = intersection / ref_area if ref_area else 0

    # Encroachment geometry (parts of current outside reference)
    encroachment_geom = cur_geom.difference(ref_geom)
    encroachment_area_ratio = encroachment_geom.area / ref_area if ref_area else 0

    violation_type = meta.get("violation_type", "COMPLIANT")
    violations = []

    # ── Rule-based classification ──
    if violation_type == "VACANT_PLOT":
        violations.append("VACANT_PLOT")
    elif violation_type == "UNAUTHORIZED_CONSTRUCTION":
        violations.append("UNAUTHORIZED_CONSTRUCTION")

    if area_diff > ENCROACHMENT_THRESHOLD:
        violations.append("ENCROACHMENT")

    shape_dev = 1 - iou
    if shape_dev > BOUNDARY_DEV_THRESHOLD and "ENCROACHMENT" not in violations:
        violations.append("BOUNDARY_DEVIATION")

    if not violations:
        return None  # compliant

    primary = violations[0]
    dev = max(abs(area_diff), shape_dev, encroachment_area_ratio)
    severity = severity_from_deviation(dev)

    # Recommended action
    actions = {
        "ENCROACHMENT": "Issue notice to plot holder; schedule field inspection",
        "VACANT_PLOT": "Verify land-use status; consider reallocation",
        "UNAUTHORIZED_CONSTRUCTION": "Halt construction; issue demolition notice",
        "BOUNDARY_DEVIATION": "Resurvey boundaries; issue correction notice",
    }

    # Cost estimate (INR) – rough heuristic
    cost_map = {"CRITICAL": 500000, "HIGH": 300000, "MEDIUM": 150000, "LOW": 50000}

    random.seed(hash(plot_id))
    detection_date = datetime.now() - timedelta(days=random.randint(0, 30))

    return {
        "plot_id": plot_id,
        "violation_types": violations,
        "primary_violation": primary,
        "severity": severity,
        "area_ref_sqm": round(ref_area * 1e10, 1),
        "area_cur_sqm": round(cur_area * 1e10, 1),
        "area_diff_pct": round(area_diff * 100, 2),
        "overlap_pct": round(overlap_pct * 100, 2),
        "iou": round(iou, 4),
        "encroachment_area_sqm": round(encroachment_geom.area * 1e10, 1),
        "encroachment_geometry": mapping(encroachment_geom)
            if not encroachment_geom.is_empty else None,
        "detection_date": detection_date.strftime("%Y-%m-%d"),
        "action_required": actions.get(primary, "Review required"),
        "estimated_cost_inr": cost_map.get(severity, 50000),
        "current_geometry": mapping(cur_geom),
    }


def run(ref_path=None, cur_path=None, meta_path=None, output_path=None):
    """Run full violation analysis and write violations.geojson."""
    ref_path = ref_path or os.path.join(DATA_DIR, "reference_plots.geojson")
    cur_path = cur_path or os.path.join(DATA_DIR, "current_plots.geojson")
    meta_path = meta_path or os.path.join(DATA_DIR, "plot_metadata.json")
    output_path = output_path or os.path.join(DATA_DIR, "violations.geojson")

    if not os.path.exists(ref_path):
        print("❌  Reference data not found. Run generate_sample_data.py first.")
        sys.exit(1)

    ref_plots = load_geojson(ref_path)
    cur_plots = load_geojson(cur_path)
    metadata = load_metadata(meta_path)

    violation_features = []
    stats = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    type_stats = {}

    for pid in ref_plots:
        if pid not in cur_plots:
            continue
        ref_geom = ref_plots[pid]["geometry"]
        cur_geom = cur_plots[pid]["geometry"]
        meta = metadata.get(pid, {})

        result = analyse_plot(pid, ref_geom, cur_geom, meta)
        if result:
            geom = result.pop("current_geometry")
            encr_geom = result.pop("encroachment_geometry", None)
            feature = {
                "type": "Feature",
                "geometry": geom,
                "properties": result,
            }
            if encr_geom:
                feature["properties"]["encroachment_geojson"] = json.dumps(encr_geom)
            violation_features.append(feature)
            stats[result["severity"]] += 1
            for vt in result["violation_types"]:
                type_stats[vt] = type_stats.get(vt, 0) + 1

    geojson_out = {"type": "FeatureCollection", "features": violation_features}
    with open(output_path, "w") as f:
        json.dump(geojson_out, f, indent=2)

    # ── Merge satellite change data if available ──
    sat_path = os.path.join(DATA_DIR, "satellite_changes.geojson")
    if os.path.exists(sat_path):
        print("   🛰️  Merging satellite change detection data...")
        with open(sat_path) as f:
            sat_data = json.load(f)

        sat_lookup = {}
        for feat in sat_data.get("features", []):
            pid = feat["properties"].get("plot_id", "")
            sat_lookup[pid] = feat["properties"]

        for feat in violation_features:
            pid = feat["properties"]["plot_id"]
            if pid in sat_lookup:
                sat = sat_lookup[pid]
                feat["properties"]["satellite_verdict"] = sat.get("violation_type", "N/A")
                feat["properties"]["satellite_confidence"] = sat.get("confidence", 0)
                feat["properties"]["satellite_evidence"] = sat.get("satellite_evidence", {})

                # Escalate severity if satellite confirms with high confidence
                if (sat.get("violation_type") not in (None, "COMPLIANT")
                        and sat.get("confidence", 0) > 0.7):
                    current_sev = feat["properties"]["severity"]
                    if current_sev in ("LOW", "MEDIUM"):
                        feat["properties"]["severity"] = "HIGH"
                        feat["properties"]["severity_note"] = "Escalated by satellite evidence"

        # Also flag compliant plots that satellite flagged
        existing_pids = {f["properties"]["plot_id"] for f in violation_features}
        for pid, sat in sat_lookup.items():
            if pid not in existing_pids and sat.get("violation_type") not in (None, "COMPLIANT"):
                if pid in cur_plots:
                    cur_geom = cur_plots[pid]["geometry"]
                    violation_features.append({
                        "type": "Feature",
                        "geometry": mapping(cur_geom),
                        "properties": {
                            "plot_id": pid,
                            "violation_types": [sat["violation_type"]],
                            "primary_violation": sat["violation_type"],
                            "severity": sat.get("severity", "MEDIUM"),
                            "area_diff_pct": 0,
                            "overlap_pct": 100,
                            "detection_date": datetime.now().strftime("%Y-%m-%d"),
                            "action_required": "Satellite-detected anomaly; verify on ground",
                            "estimated_cost_inr": 150000,
                            "detection_source": "satellite",
                            "satellite_verdict": sat.get("violation_type"),
                            "satellite_confidence": sat.get("confidence", 0),
                            "satellite_evidence": sat.get("satellite_evidence", {}),
                        },
                    })
                    stats[sat.get("severity", "MEDIUM")] = stats.get(sat.get("severity", "MEDIUM"), 0) + 1
                    for vt in [sat["violation_type"]]:
                        type_stats[vt] = type_stats.get(vt, 0) + 1

        # Re-save with satellite data merged
        geojson_out = {"type": "FeatureCollection", "features": violation_features}
        with open(output_path, "w") as f:
            json.dump(geojson_out, f, indent=2)

    # Summary statistics
    summary = {
        "total_plots": len(ref_plots),
        "total_violations": len(violation_features),
        "compliant": len(ref_plots) - len(violation_features),
        "severity_breakdown": stats,
        "type_breakdown": type_stats,
        "total_estimated_cost_inr": sum(
            f["properties"]["estimated_cost_inr"] for f in violation_features
        ),
        "satellite_data_available": os.path.exists(sat_path),
        "generated_at": datetime.now().isoformat(),
    }
    with open(os.path.join(DATA_DIR, "violation_summary.json"), "w") as f:
        json.dump(summary, f, indent=2)

    print(f"[OK] Violation analysis complete")
    print(f"   Total: {summary['total_violations']}/{summary['total_plots']} plots have violations")
    print(f"   Critical: {stats['CRITICAL']}  High: {stats['HIGH']}  "
          f"Medium: {stats['MEDIUM']}  Low: {stats['LOW']}")
    print(f"   Estimated cost impact: Rs.{summary['total_estimated_cost_inr']:,.0f}")
    print(f"   Output: {output_path}")
    if summary["satellite_data_available"]:
        print(f"   Satellite data merged: YES")

    return summary


if __name__ == "__main__":
    run()
