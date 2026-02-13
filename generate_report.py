"""
LandGuard AI - PDF Report Generator
Generates a professional compliance report with executive summary,
violation statistics, detailed table, and recommendations.
"""

import json
import os
import sys
from datetime import datetime

from fpdf import FPDF

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


class ComplianceReport(FPDF):
    """Custom PDF report for LandGuard AI compliance monitoring."""

    HEADER_BG = (26, 26, 46)        # Dark navy
    ACCENT = (102, 126, 234)         # Purple-blue
    TEXT_DARK = (30, 30, 30)
    TEXT_LIGHT = (255, 255, 255)

    def header(self):
        self.set_fill_color(*self.HEADER_BG)
        self.rect(0, 0, 210, 28, "F")
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*self.TEXT_LIGHT)
        self.set_y(6)
        self.cell(0, 10, "LandGuard AI - Compliance Report", align="C")
        self.set_font("Helvetica", "", 8)
        self.set_y(16)
        self.cell(0, 6,
                  f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  "
                  "CSIDC Industrial Plot Monitoring", align="C")
        self.ln(20)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(130, 130, 130)
        self.cell(0, 10,
                  f"LandGuard AI  |  Page {self.page_no()}/{{nb}}  |  Confidential",
                  align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*self.ACCENT)
        self.cell(0, 10, title, ln=True)
        self.set_draw_color(*self.ACCENT)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)
        self.set_text_color(*self.TEXT_DARK)

    def body_text(self, text, bold=False):
        style = "B" if bold else ""
        self.set_font("Helvetica", style, 10)
        self.set_text_color(*self.TEXT_DARK)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def stat_box(self, label, value, x, y, w=42, h=18, color=(102, 126, 234)):
        self.set_fill_color(*color)
        self.rect(x, y, w, h, "F")
        self.set_xy(x, y + 2)
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(w, 7, str(value), align="C")
        self.set_xy(x, y + 10)
        self.set_font("Helvetica", "", 7)
        self.cell(w, 5, label, align="C")


def generate_pdf(output_path=None):
    """Generate the compliance report PDF."""
    output_path = output_path or os.path.join(DATA_DIR, "compliance_report.pdf")

    # Load data
    summary_path = os.path.join(DATA_DIR, "violation_summary.json")
    violations_path = os.path.join(DATA_DIR, "violations.geojson")
    metadata_path = os.path.join(DATA_DIR, "plot_metadata.json")

    if not os.path.exists(summary_path):
        print("[ERROR] No violation summary found. Run detect_violations.py first.")
        sys.exit(1)

    with open(summary_path) as f:
        summary = json.load(f)
    with open(violations_path) as f:
        violations = json.load(f)
    with open(metadata_path) as f:
        metadata = json.load(f)

    pdf = ComplianceReport()
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=20)

    # ── Page 1: Executive Summary ──
    pdf.add_page()
    pdf.section_title("1. Executive Summary")

    total = summary["total_plots"]
    vio_count = summary["total_violations"]
    compliant = summary["compliant"]
    cost = summary["total_estimated_cost_inr"]

    pdf.body_text(
        f"This report presents the automated compliance analysis of {total} "
        f"industrial plots monitored by the LandGuard AI system. The analysis "
        f"detected {vio_count} violations across the monitored area, with "
        f"an estimated financial impact of Rs. {cost:,.0f}."
    )
    pdf.body_text(
        f"Of the {total} plots analysed, {compliant} ({compliant/total*100:.0f}%) "
        f"are fully compliant. The remaining {vio_count} plots require "
        f"immediate attention, with detailed findings below."
    )

    # Stat boxes
    y = pdf.get_y() + 4
    pdf.stat_box("Total Plots", total, 14, y, color=(79, 172, 254))
    pdf.stat_box("Violations", vio_count, 60, y, color=(235, 51, 73))
    sev = summary["severity_breakdown"]
    pdf.stat_box("Critical", sev.get("CRITICAL", 0), 106, y, color=(231, 76, 60))
    pdf.stat_box("High", sev.get("HIGH", 0), 152, y, color=(230, 126, 34))
    pdf.ln(28)

    # ── Page 2: Severity & Type Breakdown ──
    pdf.section_title("2. Violation Statistics")

    # Severity table
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(50, 8, "Severity", border=1, fill=True)
    pdf.cell(30, 8, "Count", border=1, fill=True, align="C")
    pdf.cell(50, 8, "Percentage", border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        count = sev.get(level, 0)
        pct = (count / vio_count * 100) if vio_count else 0
        pdf.cell(50, 7, level, border=1)
        pdf.cell(30, 7, str(count), border=1, align="C")
        pdf.cell(50, 7, f"{pct:.1f}%", border=1, align="C")
        pdf.ln()

    pdf.ln(6)

    # Type breakdown
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(70, 8, "Violation Type", border=1, fill=True)
    pdf.cell(30, 8, "Count", border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 10)
    for vtype, count in summary.get("type_breakdown", {}).items():
        pdf.cell(70, 7, vtype, border=1)
        pdf.cell(30, 7, str(count), border=1, align="C")
        pdf.ln()

    pdf.ln(8)

    # ── Page 3: Detailed Violations ──
    pdf.add_page()
    pdf.section_title("3. Detailed Violation Report")

    # Table header
    col_widths = [18, 40, 22, 22, 22, 66]
    headers = ["Plot ID", "Violation", "Severity", "Area %", "Overlap%", "Action Required"]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*ComplianceReport.ACCENT)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()

    # Table rows
    pdf.set_text_color(*ComplianceReport.TEXT_DARK)
    pdf.set_font("Helvetica", "", 7)
    for feat in violations["features"]:
        p = feat["properties"]

        # Severity-based row color
        sev_colors = {
            "CRITICAL": (255, 230, 230),
            "HIGH": (255, 240, 220),
            "MEDIUM": (255, 252, 220),
            "LOW": (240, 240, 240),
        }
        bg = sev_colors.get(p.get("severity", "LOW"), (255, 255, 255))
        pdf.set_fill_color(*bg)

        row_data = [
            p.get("plot_id", ""),
            p.get("primary_violation", ""),
            p.get("severity", ""),
            f"{p.get('area_diff_pct', 0):.1f}%",
            f"{p.get('overlap_pct', 0):.1f}%",
            p.get("action_required", "")[:45],
        ]
        for i, val in enumerate(row_data):
            pdf.cell(col_widths[i], 6, val, border=1, fill=True)
        pdf.ln()

    pdf.ln(8)

    # ── Recommendations ──
    pdf.section_title("4. Recommendations")
    recommendations = [
        "1. Prioritize CRITICAL violations for immediate field inspection within 48 hours.",
        "2. Issue show-cause notices to all encroachment cases within 7 working days.",
        "3. Commission resurvey for plots with BOUNDARY_DEVIATION violations.",
        "4. Initiate reallocation process for confirmed VACANT_PLOT violations.",
        "5. Deploy continuous monitoring cycle (quarterly satellite imagery analysis).",
        "6. Establish automated alerting pipeline for real-time encroachment detection.",
    ]
    for rec in recommendations:
        pdf.body_text(rec)

    # ── Cost-Benefit Analysis ──
    pdf.section_title("5. Cost-Benefit Analysis")
    manual_cost = total * 25000
    automated_cost = 50000
    savings = manual_cost - automated_cost
    pdf.body_text(f"Manual Survey Cost (drone + operator per plot): Rs. 25,000 x {total} = Rs. {manual_cost:,.0f}")
    pdf.body_text(f"Automated Analysis Cost (LandGuard AI): Rs. {automated_cost:,.0f} (fixed)")
    pdf.body_text(f"Cost Savings per Cycle: Rs. {savings:,.0f} ({savings/manual_cost*100:.0f}% reduction)", bold=True)
    pdf.body_text(f"Annual Savings (4 cycles/year): Rs. {savings * 4:,.0f}")
    pdf.body_text(
        "Additional benefits: Faster detection (hours vs weeks), "
        "consistent analysis, historical trend tracking, scalable to 1000+ plots."
    )

    # Save
    pdf.output(output_path)
    print(f"[OK] Report generated: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_pdf()
