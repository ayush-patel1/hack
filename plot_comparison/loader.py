"""
loader.py - Load GeoJSON plots, metadata, and satellite images.

This module handles all data loading:
  - GeoJSON files with plot polygons
  - Plot metadata JSON
  - Satellite images (per-plot JPGs or a single GeoTIFF)
"""

import os
import json
import cv2
import numpy as np
import geopandas as gpd


def load_plots(geojson_path):
    """
    Load plot polygons from a GeoJSON file.

    Args:
        geojson_path (str): Path to the GeoJSON file.

    Returns:
        geopandas.GeoDataFrame: GeoDataFrame with plot geometries and attributes.
    """
    if not os.path.exists(geojson_path):
        raise FileNotFoundError(f"GeoJSON file not found: {geojson_path}")

    gdf = gpd.read_file(geojson_path)
    print(f"[Loader] Loaded {len(gdf)} features from {os.path.basename(geojson_path)}")

    # Filter to only Polygon geometries (skip LineStrings like roads)
    polygon_mask = gdf.geometry.type.isin(["Polygon", "MultiPolygon"])
    gdf = gdf[polygon_mask].copy()
    print(f"[Loader] {len(gdf)} polygon plots after filtering")

    return gdf


def load_metadata(metadata_path):
    """
    Load plot metadata from a JSON file.

    Args:
        metadata_path (str): Path to the metadata JSON file.

    Returns:
        list: List of metadata dictionaries, one per plot.
    """
    if not os.path.exists(metadata_path):
        print(f"[Loader] Warning: Metadata file not found: {metadata_path}")
        return []

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    print(f"[Loader] Loaded metadata for {len(metadata)} plots")
    return metadata


def load_image(image_path):
    """
    Load a satellite image using OpenCV.

    Args:
        image_path (str): Path to the image file (JPG, PNG, TIFF).

    Returns:
        numpy.ndarray: Image array in BGR format, or None if loading fails.
    """
    if not os.path.exists(image_path):
        print(f"[Loader] Warning: Image not found: {image_path}")
        return None

    image = cv2.imread(image_path)
    if image is None:
        print(f"[Loader] Warning: Could not read image: {image_path}")
        return None

    print(f"[Loader] Loaded image: {os.path.basename(image_path)} "
          f"({image.shape[1]}x{image.shape[0]} pixels)")
    return image


def get_plot_image_path(plot_id, images_dir, suffix="_current"):
    """
    Get the path to a plot's satellite image.

    Looks for files named like: {plot_id}_current.jpg

    Args:
        plot_id (str): Plot identifier (e.g., "PLOT_1").
        images_dir (str): Directory containing satellite images.
        suffix (str): Image suffix, e.g., "_current" or "_reference".

    Returns:
        str or None: Path to the image file, or None if not found.
    """
    # Try common extensions
    for ext in [".jpg", ".jpeg", ".png", ".tif", ".tiff"]:
        path = os.path.join(images_dir, f"{plot_id}{suffix}{ext}")
        if os.path.exists(path):
            return path

    return None


def list_available_plots(images_dir):
    """
    List all plot IDs that have satellite images available.

    Args:
        images_dir (str): Directory containing satellite images.

    Returns:
        list: List of plot IDs with available images.
    """
    if not os.path.exists(images_dir):
        return []

    plot_ids = set()
    for filename in os.listdir(images_dir):
        # Extract plot_id from filenames like "PLOT_1_current.jpg"
        if "_current" in filename:
            plot_id = filename.split("_current")[0]
            plot_ids.add(plot_id)

    return sorted(plot_ids)
