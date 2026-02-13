"""
main.py - Entry point for the Industrial Plot Comparison System.

Usage:
    python -m plot_comparison.main
    python -m plot_comparison.main --geojson data/allotment_map.geojson
    python -m plot_comparison.main --geojson data/allotment_map.geojson --images data/images --output output
    python -m plot_comparison.main --no-viz   (skip visualization images)

This script orchestrates the full pipeline:
  1. Load GeoJSON plots
  2. Load satellite images
  3. Analyze each plot for development
  4. Generate console summary
  5. Generate PDF report
  6. Save visualization images (optional)
"""

import os
import sys
import argparse

# Add project root to path so we can run as: python -m plot_comparison.main
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from plot_comparison.loader import load_plots, load_image, get_plot_image_path
from plot_comparison.processor import analyze_all_plots
from plot_comparison.report import (
    print_console_summary,
    generate_pdf_report,
    save_visualization,
)


def generate_sample_images(plots_gdf, images_dir):
    """
    Generate simple sample satellite images for plots that don't have images.
    
    This creates synthetic test images so the pipeline can demonstrate
    its functionality even without real satellite imagery.

    Args:
        plots_gdf: GeoDataFrame with plot data.
        images_dir: Directory to save generated images.
    """
    import numpy as np
    import cv2

    os.makedirs(images_dir, exist_ok=True)

    np.random.seed(42)

    for idx, row in plots_gdf.iterrows():
        plot_id = row.get("plot_id", f"UNKNOWN_{idx}")
        img_path = os.path.join(images_dir, f"{plot_id}_current.jpg")

        if os.path.exists(img_path):
            continue  # Skip if image already exists

        # Create a 256x256 synthetic satellite image
        img = np.zeros((256, 256, 3), dtype=np.uint8)
        zone = row.get("zone", "").upper()
        plot_status = row.get("status", "").lower()

        if zone in ("GREEN_AREA", "WATER_BODY"):
            # Green or blue tones — should appear vacant
            base_color = (34, 139, 34) if zone == "GREEN_AREA" else (139, 100, 30)
            img[:, :] = base_color
            # Add some natural texture
            noise = np.random.randint(0, 30, img.shape, dtype=np.uint8)
            img = cv2.add(img, noise)

        elif zone in ("PARKING", "ROAD"):
            # Gray tones — moderate edges
            img[:, :] = (128, 128, 128)
            noise = np.random.randint(0, 40, img.shape, dtype=np.uint8)
            img = cv2.add(img, noise)
            # Add some line features
            for y in range(0, 256, 30):
                cv2.line(img, (0, y), (256, y), (180, 180, 180), 2)

        elif plot_status == "allotted":
            # Simulate varying development levels
            development_level = np.random.choice(["vacant", "partial", "full"],
                                                  p=[0.2, 0.4, 0.4])

            if development_level == "vacant":
                # Mostly green/brown — empty land
                img[:, :] = (30, 100, 50)
                noise = np.random.randint(0, 25, img.shape, dtype=np.uint8)
                img = cv2.add(img, noise)

            elif development_level == "partial":
                # Mix of green and structures
                img[:, :] = (40, 110, 60)
                noise = np.random.randint(0, 20, img.shape, dtype=np.uint8)
                img = cv2.add(img, noise)
                # Add some building-like rectangles
                for _ in range(3):
                    x1 = np.random.randint(20, 150)
                    y1 = np.random.randint(20, 150)
                    x2 = x1 + np.random.randint(30, 80)
                    y2 = y1 + np.random.randint(30, 80)
                    color = (180 + np.random.randint(0, 50),
                             180 + np.random.randint(0, 50),
                             180 + np.random.randint(0, 50))
                    cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
                    cv2.rectangle(img, (x1, y1), (x2, y2), (100, 100, 100), 2)

            else:  # full
                # Dense structures
                img[:, :] = (200, 200, 200)
                noise = np.random.randint(0, 20, img.shape, dtype=np.uint8)
                img = cv2.add(img, noise)
                for _ in range(8):
                    x1 = np.random.randint(5, 180)
                    y1 = np.random.randint(5, 180)
                    x2 = x1 + np.random.randint(20, 60)
                    y2 = y1 + np.random.randint(20, 60)
                    color = (150 + np.random.randint(0, 80),
                             150 + np.random.randint(0, 80),
                             150 + np.random.randint(0, 80))
                    cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
                    cv2.rectangle(img, (x1, y1), (x2, y2), (80, 80, 80), 2)
                # Add road-like features
                cv2.line(img, (0, 128), (256, 128), (100, 100, 100), 4)
                cv2.line(img, (128, 0), (128, 256), (100, 100, 100), 4)

        else:
            # Default — some texture
            img[:, :] = (100, 120, 80)
            noise = np.random.randint(0, 30, img.shape, dtype=np.uint8)
            img = cv2.add(img, noise)

        cv2.imwrite(img_path, img)
        print(f"[Main] Generated sample image for {plot_id}")


def main():
    """Main entry point for the plot comparison system."""

    parser = argparse.ArgumentParser(
        description="Industrial Plot Comparison System - "
                    "Compare land plots with satellite imagery"
    )
    parser.add_argument(
        "--geojson",
        default="data/allotment_map.geojson",
        help="Path to GeoJSON file with plot polygons (default: data/allotment_map.geojson)"
    )
    parser.add_argument(
        "--images",
        default="data/plot_images",
        help="Directory containing satellite images (default: data/plot_images)"
    )
    parser.add_argument(
        "--output",
        default="output",
        help="Output directory for reports and visualizations (default: output)"
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Skip generating visualization images"
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        default=True,
        help="Generate sample satellite images if none exist (default: True)"
    )

    args = parser.parse_args()

    # Resolve paths relative to project root
    geojson_path = os.path.join(PROJECT_ROOT, args.geojson) \
        if not os.path.isabs(args.geojson) else args.geojson
    images_dir = os.path.join(PROJECT_ROOT, args.images) \
        if not os.path.isabs(args.images) else args.images
    output_dir = os.path.join(PROJECT_ROOT, args.output) \
        if not os.path.isabs(args.output) else args.output

    print("=" * 60)
    print("  INDUSTRIAL PLOT COMPARISON SYSTEM")
    print("=" * 60)
    print(f"  GeoJSON : {geojson_path}")
    print(f"  Images  : {images_dir}")
    print(f"  Output  : {output_dir}")
    print("=" * 60 + "\n")

    # ── Step 1: Load GeoJSON plots ──
    print("── Step 1: Loading GeoJSON plots ──")
    plots_gdf = load_plots(geojson_path)

    if plots_gdf.empty:
        print("[Main] ERROR: No polygon plots found in GeoJSON. Exiting.")
        sys.exit(1)

    # ── Step 2: Ensure satellite images exist ──
    print("\n── Step 2: Loading satellite images ──")
    if args.generate_samples:
        generate_sample_images(plots_gdf, images_dir)

    # ── Step 3: Analyze all plots ──
    print("\n── Step 3: Analyzing plots for development ──")
    results = analyze_all_plots(plots_gdf, images_dir, load_image)

    # ── Step 4: Save visualizations ──
    viz_dir = os.path.join(output_dir, "visualizations")
    if not args.no_viz:
        print("\n── Step 4: Generating visualizations ──")
        for r in results:
            plot_id = r["plot_id"]
            img_path = get_plot_image_path(plot_id, images_dir, suffix="_current")
            if img_path:
                image = load_image(img_path)
                edge_mask = r.get("edge_mask")
                viz_path = save_visualization(plot_id, image, edge_mask, viz_dir)
                if viz_path:
                    print(f"[Main] Saved visualization: {os.path.basename(viz_path)}")
    else:
        print("\n── Step 4: Skipped visualizations (--no-viz) ──")

    # ── Step 5: Print console summary ──
    print("\n── Step 5: Results ──")

    # Remove edge_mask from results before reporting (not serializable)
    clean_results = []
    for r in results:
        clean = {k: v for k, v in r.items() if k != "edge_mask"}
        clean_results.append(clean)

    print_console_summary(clean_results)

    # ── Step 6: Generate PDF report ──
    print("── Step 6: Generating PDF report ──")
    pdf_path = os.path.join(output_dir, "plot_comparison_report.pdf")
    generate_pdf_report(clean_results, pdf_path, viz_dir=viz_dir)

    print(f"\n✅ Done! Report saved to: {pdf_path}")
    print(f"   Visualizations saved to: {viz_dir}")

    return clean_results


if __name__ == "__main__":
    main()
