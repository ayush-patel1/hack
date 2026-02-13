"""
LandGuard AI - Data Preprocessing Script
Extracts images from PPTX/PDF files, loads reference/current survey images,
and prepares structured metadata for the analysis pipeline.
"""

import json
import os
import sys
import glob
from datetime import datetime

import cv2
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")


# ──────────────────────────────────────────────
#  Image Extraction from Documents
# ──────────────────────────────────────────────
def extract_from_pptx(pptx_path, output_dir):
    """Extract all images from a PowerPoint file."""
    try:
        from pptx import Presentation
    except ImportError:
        print("⚠️  python-pptx not installed. Run: pip install python-pptx")
        return []

    prs = Presentation(pptx_path)
    extracted = []
    img_count = 0

    for slide_num, slide in enumerate(prs.slides, 1):
        for shape_obj in slide.shapes:
            if shape_obj.shape_type == 13:  # Picture type
                image = shape_obj.image
                ext = image.content_type.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"
                img_count += 1
                filename = f"pptx_slide{slide_num}_img{img_count}.{ext}"
                filepath = os.path.join(output_dir, filename)

                with open(filepath, "wb") as f:
                    f.write(image.blob)
                extracted.append(filepath)
                print(f"  📸 Extracted: {filename}")

    return extracted


def extract_from_pdf(pdf_path, output_dir):
    """Extract images from a PDF file using PIL/Pillow fallback."""
    extracted = []

    # Try PyMuPDF first (fitz)
    try:
        import fitz
        doc = fitz.open(pdf_path)
        img_count = 0
        for page_num in range(len(doc)):
            page = doc[page_num]
            images = page.get_images(full=True)
            for img_idx, img in enumerate(images):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                if pix.n < 5:  # GRAY or RGB
                    img_count += 1
                    filename = f"pdf_p{page_num+1}_img{img_count}.png"
                    filepath = os.path.join(output_dir, filename)
                    pix.save(filepath)
                    extracted.append(filepath)
                    print(f"  📸 Extracted: {filename}")
                pix = None
        doc.close()
        return extracted
    except ImportError:
        pass

    # Fallback: convert PDF pages to images using pdf2image if available
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(pdf_path, dpi=200)
        for i, page in enumerate(pages):
            filename = f"pdf_page_{i+1}.jpg"
            filepath = os.path.join(output_dir, filename)
            page.save(filepath, "JPEG")
            extracted.append(filepath)
            print(f"  📸 Extracted: {filename}")
        return extracted
    except ImportError:
        print("⚠️  Install PyMuPDF or pdf2image: pip install PyMuPDF pdf2image")
        return []


# ──────────────────────────────────────────────
#  Image Preprocessing
# ──────────────────────────────────────────────
def preprocess_image(image_path, target_size=(800, 800)):
    """
    Normalize and resize an image for consistent analysis.
    Returns the preprocessed image path.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"⚠️  Cannot read: {image_path}")
        return None

    # Resize while maintaining aspect ratio
    h, w = img.shape[:2]
    scale = min(target_size[0] / w, target_size[1] / h)
    new_w, new_h = int(w * scale), int(h * scale)
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)

    # Pad to target size
    canvas = np.full((target_size[1], target_size[0], 3), 220, dtype=np.uint8)
    y_off = (target_size[1] - new_h) // 2
    x_off = (target_size[0] - new_w) // 2
    canvas[y_off:y_off + new_h, x_off:x_off + new_w] = resized

    # Enhance contrast (CLAHE)
    lab = cv2.cvtColor(canvas, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    l = clahe.apply(l)
    enhanced = cv2.merge([l, a, b])
    result = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

    # Save preprocessed
    base = os.path.splitext(os.path.basename(image_path))[0]
    out_path = os.path.join(IMAGE_DIR, f"{base}_preprocessed.jpg")
    cv2.imwrite(out_path, result)
    return out_path


# ──────────────────────────────────────────────
#  Metadata Builder
# ──────────────────────────────────────────────
def build_metadata_from_images(reference_dir, current_dir, center_lat=21.2514,
                                center_lon=81.6296):
    """
    Build plot_metadata.json by pairing reference and current images.
    Expects filenames like P001_reference.jpg / P001_current.jpg.
    """
    ref_images = sorted(glob.glob(os.path.join(reference_dir, "*_reference.*")))
    metadata = []

    for i, ref_path in enumerate(ref_images):
        base = os.path.basename(ref_path)
        plot_id = base.split("_")[0]

        # Find matching current image
        cur_candidates = glob.glob(
            os.path.join(current_dir, f"{plot_id}_current.*")
        )
        cur_path = cur_candidates[0] if cur_candidates else None

        # Estimate area from image dimensions
        img = cv2.imread(ref_path)
        area_sqm = 5000 + i * 500  # default estimate

        lat = center_lat + (i // 5) * 0.003
        lon = center_lon + (i % 5) * 0.003

        entry = {
            "plot_id": plot_id,
            "reference_image": os.path.relpath(ref_path, BASE_DIR),
            "current_image": os.path.relpath(cur_path, BASE_DIR) if cur_path else None,
            "coordinates": [round(lat, 6), round(lon, 6)],
            "area_sqm": area_sqm,
            "owner": f"Industrial Unit {i + 1}",
            "allotment_date": f"2018-{(i % 12) + 1:02d}-15",
            "preprocessed": False,
        }
        metadata.append(entry)

    return metadata


# ──────────────────────────────────────────────
#  Main Pipeline
# ──────────────────────────────────────────────
def run(upload_path=None):
    """
    Run the full preprocessing pipeline.

    Args:
        upload_path: Optional path to a PPTX/PDF file to extract images from.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    print("🔧 LandGuard AI — Preprocessing Pipeline\n")

    # Step 1: Extract from uploaded documents
    if upload_path:
        ext = os.path.splitext(upload_path)[1].lower()
        print(f"📂 Processing upload: {upload_path}")
        if ext == ".pptx":
            extracted = extract_from_pptx(upload_path, UPLOAD_DIR)
        elif ext == ".pdf":
            extracted = extract_from_pdf(upload_path, UPLOAD_DIR)
        else:
            print(f"⚠️  Unsupported format: {ext}")
            extracted = []
        print(f"   Extracted {len(extracted)} images\n")

    # Step 2: Preprocess existing images
    existing_images = glob.glob(os.path.join(IMAGE_DIR, "*.jpg")) + \
                      glob.glob(os.path.join(IMAGE_DIR, "*.png"))

    if existing_images:
        print(f"🖼️  Preprocessing {len(existing_images)} images...")
        for img_path in existing_images:
            if "_preprocessed" in img_path or "_annotated" in img_path:
                continue
            result = preprocess_image(img_path)
            if result:
                print(f"   ✅ {os.path.basename(img_path)}")
    else:
        print("ℹ️  No images found in data/images/. Run generate_sample_data.py first.")

    # Step 3: Build/update metadata
    meta_path = os.path.join(DATA_DIR, "plot_metadata.json")
    if not os.path.exists(meta_path):
        print("\n📋 Building metadata from image files...")
        metadata = build_metadata_from_images(IMAGE_DIR, IMAGE_DIR)
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)
        print(f"   ✅ Created {meta_path} ({len(metadata)} plots)")
    else:
        print(f"\nℹ️  Metadata already exists at {meta_path}")

    print("\n✅ Preprocessing complete!")
    print("   Next steps:")
    print("   1. python detect_boundaries.py   (detect plot boundaries)")
    print("   2. python detect_violations.py    (run violation analysis)")
    print("   3. streamlit run app.py           (launch dashboard)")


if __name__ == "__main__":
    upload = sys.argv[1] if len(sys.argv) > 1 else None
    run(upload_path=upload)
