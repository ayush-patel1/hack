"""
processor.py - Image processing and development detection.

This module handles:
  - Edge detection to identify built-up areas
  - Calculation of developed vs undeveloped percentage
  - Classification of plots (Vacant / Partial / Developed)
  - Deviation flagging
"""

import cv2
import numpy as np
from shapely.geometry import shape


def detect_development(image):
    """
    Detect built-up / developed area in a satellite image using edge detection.

    Pipeline:
      1. Convert to grayscale
      2. Apply Gaussian blur to reduce noise
      3. Apply Canny edge detection
      4. Dilate edges to fill small gaps
      5. Calculate percentage of edge pixels (proxy for development)

    Args:
        image (numpy.ndarray): BGR satellite image.

    Returns:
        tuple: (developed_percentage, edge_mask)
            - developed_percentage (float): 0-100 percentage of developed area.
            - edge_mask (numpy.ndarray): Binary mask showing detected edges.
    """
    if image is None:
        return 0.0, None

    # Step 1: Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Step 2: Gaussian blur to reduce noise
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # Step 3: Canny edge detection
    # Lower threshold detects more edges (more sensitive)
    edges = cv2.Canny(blurred, threshold1=30, threshold2=100)

    # Step 4: Dilate to connect nearby edges (simulates built-up areas)
    kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(edges, kernel, iterations=2)

    # Step 5: Calculate percentage of developed pixels
    total_pixels = dilated.shape[0] * dilated.shape[1]
    developed_pixels = np.count_nonzero(dilated)
    developed_percentage = (developed_pixels / total_pixels) * 100

    return round(developed_percentage, 2), dilated


def classify_plot(developed_pct):
    """
    Classify a plot based on its development percentage.

    Classification rules:
      - Less than 15%  → "Vacant"
      - 15% to 60%     → "Partially Developed"
      - More than 60%  → "Fully Developed"

    Args:
        developed_pct (float): Percentage of developed area (0-100).

    Returns:
        str: Classification status string.
    """
    if developed_pct < 15:
        return "Vacant"
    elif developed_pct <= 60:
        return "Partially Developed"
    else:
        return "Fully Developed"


def check_deviation(plot_properties, status):
    """
    Check if there is a deviation from expected status.

    Flags deviation if:
      - A reserved/green area plot shows development
      - A plot where construction_allowed is False shows development
      - An allotted plot remains vacant

    Args:
        plot_properties (dict): Plot attributes from GeoJSON.
        status (str): Detected development status.

    Returns:
        tuple: (has_deviation, reason)
    """
    plot_status = plot_properties.get("status", "").lower()
    construction_allowed = plot_properties.get("construction_allowed", True)
    zone = plot_properties.get("zone", "").upper()

    # Check 1: Development on restricted areas
    if not construction_allowed and status != "Vacant":
        return True, f"Development detected on restricted area (zone: {zone})"

    # Check 2: Reserved plots should not have construction
    if plot_status == "reserved" and status in ["Partially Developed", "Fully Developed"]:
        return True, f"Construction detected on reserved plot"

    # Check 3: Allotted plot still vacant (potential underutilization)
    if plot_status == "allotted" and status == "Vacant":
        return True, f"Allotted plot appears unused"

    return False, "No deviation"


def calculate_area_sqm(geometry):
    """
    Calculate approximate area in square meters from a polygon geometry.

    Uses a simple approximation based on the geometry's bounds.
    For more accuracy, consider using pyproj for proper projection.

    Args:
        geometry: Shapely geometry object.

    Returns:
        float: Approximate area in square meters.
    """
    if geometry is None:
        return 0.0

    # Use the area in degrees and convert approximately
    # At ~20.88°N latitude: 1 degree lat ≈ 111,120 m, 1 degree lon ≈ 104,000 m
    bounds = geometry.bounds  # (minx, miny, maxx, maxy)
    lon_span = bounds[2] - bounds[0]
    lat_span = bounds[3] - bounds[1]

    width_m = lon_span * 104000  # approximate meters per degree longitude
    height_m = lat_span * 111120  # approximate meters per degree latitude
    area_approx = width_m * height_m

    return round(area_approx, 1)


def analyze_plot(plot_id, plot_properties, geometry, image, metadata_entry=None):
    """
    Run the full analysis pipeline on a single plot.

    Args:
        plot_id (str): Plot identifier.
        plot_properties (dict): Plot attributes from GeoJSON.
        geometry: Shapely geometry of the plot.
        image (numpy.ndarray): Current satellite image (BGR).
        metadata_entry (dict, optional): Additional metadata.

    Returns:
        dict: Analysis result with keys:
            - plot_id, plot_number, zone, area_sqm
            - developed_pct, status, has_deviation, deviation_reason
            - edge_mask (numpy array for visualization)
    """
    # Get plot attributes
    plot_number = plot_properties.get("plot_number", plot_id)
    zone = plot_properties.get("zone", "Unknown")
    area_sqm = plot_properties.get("area_sqm", 0)

    # If area not in properties, calculate from geometry
    if area_sqm == 0 and geometry is not None:
        area_sqm = calculate_area_sqm(geometry)

    # Run development detection
    developed_pct, edge_mask = detect_development(image)

    # Classify plot
    status = classify_plot(developed_pct)

    # Check for deviations
    has_deviation, deviation_reason = check_deviation(plot_properties, status)

    result = {
        "plot_id": plot_id,
        "plot_number": plot_number,
        "zone": zone,
        "area_sqm": area_sqm,
        "industry_type": plot_properties.get("industry_type", "N/A"),
        "allotment_status": plot_properties.get("status", "N/A"),
        "developed_pct": developed_pct,
        "status": status,
        "has_deviation": has_deviation,
        "deviation_reason": deviation_reason,
        "edge_mask": edge_mask,
    }

    return result


def analyze_all_plots(plots_gdf, images_dir, load_image_fn):
    """
    Analyze all plots in the GeoDataFrame.

    Args:
        plots_gdf (geopandas.GeoDataFrame): GeoDataFrame with plot geometries.
        images_dir (str): Directory containing satellite images.
        load_image_fn (callable): Function to load an image given a path.

    Returns:
        list: List of result dictionaries, one per analyzed plot.
    """
    from . import loader

    results = []

    for idx, row in plots_gdf.iterrows():
        plot_id = row.get("plot_id", f"UNKNOWN_{idx}")
        properties = row.to_dict()

        # Remove geometry from properties dict
        properties.pop("geometry", None)

        # Try to load the satellite image for this plot
        img_path = loader.get_plot_image_path(plot_id, images_dir, suffix="_current")

        if img_path:
            image = load_image_fn(img_path)
        else:
            print(f"[Processor] No satellite image found for {plot_id}, "
                  f"using blank analysis")
            image = None

        # Analyze the plot
        result = analyze_plot(
            plot_id=plot_id,
            plot_properties=properties,
            geometry=row.geometry,
            image=image,
        )

        results.append(result)
        print(f"[Processor] {plot_id}: {result['developed_pct']}% developed "
              f"→ {result['status']}"
              f"{' ⚠ DEVIATION' if result['has_deviation'] else ''}")

    return results
