"""
report.py - Generate PDF reports and console summaries.

This module handles:
  - PDF report generation using reportlab
  - Console summary printing
  - Visualization image saving with matplotlib
"""

import os
from datetime import datetime

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, PageBreak, Image as RLImage
)


# ─────────────────────────────────────────────────────────
#  Console Summary
# ─────────────────────────────────────────────────────────

def print_console_summary(results):
    """
    Print a formatted summary table to the console.

    Args:
        results (list): List of analysis result dicts.
    """
    # Header
    print("\n" + "=" * 100)
    print("  INDUSTRIAL PLOT COMPARISON REPORT")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 100)

    # Column headers
    header = (
        f"{'Plot ID':<18} {'Plot #':<10} {'Zone':<12} "
        f"{'Area(sqm)':<12} {'Dev %':<8} {'Status':<22} {'Deviation':<10}"
    )
    print(header)
    print("-" * 100)

    # Counters
    vacant = partial = developed = deviations = 0

    for r in results:
        flag = "⚠ YES" if r["has_deviation"] else "No"
        status = r["status"]

        if status == "Vacant":
            vacant += 1
        elif status == "Partially Developed":
            partial += 1
        else:
            developed += 1

        if r["has_deviation"]:
            deviations += 1

        row = (
            f"{r['plot_id']:<18} {str(r['plot_number']):<10} {r['zone']:<12} "
            f"{r['area_sqm']:<12.1f} {r['developed_pct']:<8.1f} "
            f"{status:<22} {flag:<10}"
        )
        print(row)

    # Summary footer
    print("-" * 100)
    print(f"  Total Plots: {len(results)}  |  "
          f"Vacant: {vacant}  |  Partial: {partial}  |  "
          f"Developed: {developed}  |  Deviations: {deviations}")
    print("=" * 100 + "\n")


# ─────────────────────────────────────────────────────────
#  PDF Report Generation
# ─────────────────────────────────────────────────────────

def _get_status_color(status):
    """Return a color based on plot status."""
    if status == "Vacant":
        return colors.Color(0.95, 0.6, 0.6)      # Light red
    elif status == "Partially Developed":
        return colors.Color(1.0, 0.9, 0.6)        # Light yellow
    else:
        return colors.Color(0.6, 0.9, 0.6)        # Light green


def generate_pdf_report(results, output_path, viz_dir=None):
    """
    Generate a professional PDF report with plot analysis results.

    Args:
        results (list): List of analysis result dicts.
        output_path (str): Path to save the PDF file.
        viz_dir (str, optional): Directory containing visualization images.
    """
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    doc = SimpleDocTemplate(
        output_path,
        pagesize=landscape(A4),
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    elements = []

    # ── Title ──
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=24,
        spaceAfter=6,
        textColor=colors.HexColor("#1a237e"),
    )
    elements.append(Paragraph("Industrial Plot Comparison Report", title_style))

    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=12,
        textColor=colors.grey,
        spaceAfter=20,
    )
    date_str = datetime.now().strftime("%B %d, %Y at %H:%M")
    elements.append(Paragraph(f"Generated on {date_str}", subtitle_style))
    elements.append(Spacer(1, 10))

    # ── Summary Section ──
    vacant = sum(1 for r in results if r["status"] == "Vacant")
    partial = sum(1 for r in results if r["status"] == "Partially Developed")
    developed = sum(1 for r in results if r["status"] == "Fully Developed")
    deviations = sum(1 for r in results if r["has_deviation"])

    section_style = ParagraphStyle(
        "SectionHeader",
        parent=styles["Heading2"],
        fontSize=16,
        textColor=colors.HexColor("#283593"),
        spaceAfter=10,
        spaceBefore=10,
    )
    elements.append(Paragraph("Summary", section_style))

    summary_data = [
        ["Total Plots", "Vacant", "Partially Developed", "Fully Developed", "Deviations"],
        [str(len(results)), str(vacant), str(partial), str(developed), str(deviations)],
    ]
    summary_table = Table(summary_data, colWidths=[120, 100, 140, 120, 100])
    summary_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white]),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # ── Detailed Results Table ──
    elements.append(Paragraph("Detailed Plot Analysis", section_style))

    table_header = [
        "Plot ID", "Plot #", "Zone", "Area (sqm)",
        "Developed %", "Status", "Deviation"
    ]
    table_data = [table_header]

    for r in results:
        deviation_text = "YES" if r["has_deviation"] else "No"
        table_data.append([
            r["plot_id"],
            str(r["plot_number"]),
            r["zone"],
            f"{r['area_sqm']:.1f}",
            f"{r['developed_pct']:.1f}%",
            r["status"],
            deviation_text,
        ])

    col_widths = [110, 70, 90, 80, 80, 130, 70]
    detail_table = Table(table_data, colWidths=col_widths)

    # Build style commands
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#283593")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]

    # Color-code status cells and deviation cells
    for i, r in enumerate(results, start=1):
        # Status column (index 5)
        status_color = _get_status_color(r["status"])
        style_cmds.append(("BACKGROUND", (5, i), (5, i), status_color))

        # Deviation column (index 6)
        if r["has_deviation"]:
            style_cmds.append(("BACKGROUND", (6, i), (6, i),
                               colors.Color(1.0, 0.7, 0.7)))
            style_cmds.append(("FONTNAME", (6, i), (6, i), "Helvetica-Bold"))

        # Alternating row backgrounds
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (4, i),
                               colors.Color(0.95, 0.95, 0.98)))

    detail_table.setStyle(TableStyle(style_cmds))
    elements.append(detail_table)
    elements.append(Spacer(1, 20))

    # ── Deviation Details ──
    deviation_results = [r for r in results if r["has_deviation"]]
    if deviation_results:
        elements.append(PageBreak())
        elements.append(Paragraph("Deviation Details", section_style))

        for r in deviation_results:
            note_style = ParagraphStyle(
                "DeviationNote",
                parent=styles["Normal"],
                fontSize=10,
                spaceAfter=8,
                leftIndent=10,
            )
            elements.append(Paragraph(
                f"<b>{r['plot_id']}</b> (Plot #{r['plot_number']}, "
                f"{r['zone']}): {r['deviation_reason']}",
                note_style
            ))

    # ── Visualization Images ──
    if viz_dir and os.path.exists(viz_dir):
        viz_files = sorted([f for f in os.listdir(viz_dir) if f.endswith(".png")])
        if viz_files:
            elements.append(PageBreak())
            elements.append(Paragraph("Visual Analysis", section_style))

            for viz_file in viz_files:
                viz_path = os.path.join(viz_dir, viz_file)
                try:
                    img = RLImage(viz_path, width=680, height=200)
                    plot_name = viz_file.replace("_analysis.png", "")
                    elements.append(Paragraph(
                        f"<b>{plot_name}</b>",
                        ParagraphStyle("VizLabel", parent=styles["Normal"],
                                       fontSize=10, spaceAfter=4)
                    ))
                    elements.append(img)
                    elements.append(Spacer(1, 10))
                except Exception as e:
                    print(f"[Report] Warning: Could not embed image {viz_file}: {e}")

    # Build the PDF
    doc.build(elements)
    print(f"[Report] PDF report saved to: {output_path}")


# ─────────────────────────────────────────────────────────
#  Visualization
# ─────────────────────────────────────────────────────────

def save_visualization(plot_id, original_image, edge_mask, output_dir):
    """
    Save a side-by-side visualization of original image vs edge detection.

    Args:
        plot_id (str): Plot identifier for the filename.
        original_image (numpy.ndarray): Original BGR satellite image.
        edge_mask (numpy.ndarray): Binary edge detection mask.
        output_dir (str): Directory to save visualization images.

    Returns:
        str: Path to the saved visualization, or None on failure.
    """
    if original_image is None or edge_mask is None:
        return None

    os.makedirs(output_dir, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    # Original image (convert BGR to RGB for matplotlib)
    rgb_image = cv2.cvtColor(original_image, cv2.COLOR_BGR2RGB)
    axes[0].imshow(rgb_image)
    axes[0].set_title("Satellite Image", fontsize=11, fontweight="bold")
    axes[0].axis("off")

    # Edge detection result
    axes[1].imshow(edge_mask, cmap="gray")
    axes[1].set_title("Edge Detection", fontsize=11, fontweight="bold")
    axes[1].axis("off")

    # Overlay: edges on top of original
    overlay = rgb_image.copy()
    # Make edges red on the overlay
    edge_colored = np.zeros_like(overlay)
    edge_colored[:, :, 0] = edge_mask  # Red channel
    # Resize if needed
    if edge_colored.shape[:2] != overlay.shape[:2]:
        edge_colored = cv2.resize(edge_colored, (overlay.shape[1], overlay.shape[0]))
    overlay = cv2.addWeighted(overlay, 0.7, edge_colored, 0.3, 0)

    axes[2].imshow(overlay)
    axes[2].set_title("Overlay", fontsize=11, fontweight="bold")
    axes[2].axis("off")

    plt.suptitle(f"Plot: {plot_id}", fontsize=13, fontweight="bold")
    plt.tight_layout()

    output_path = os.path.join(output_dir, f"{plot_id}_analysis.png")
    plt.savefig(output_path, dpi=120, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close(fig)

    return output_path
