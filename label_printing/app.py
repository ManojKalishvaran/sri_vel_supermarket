# app.py
import io
import os
import sqlite3
from datetime import datetime
from typing import Dict, Any

from flask import Flask, jsonify, request, send_file, render_template
from PIL import Image, ImageDraw, ImageFont
from barcode import Code128
from barcode.writer import ImageWriter

from barcode_print import print_image
import win32print   # ✅ to list printers if error

# ---------- Config ----------
DB_PATH = r"Data\products.db"

DPI = 203  # Standard thermal printer DPI
LABEL_W_MM = 40  # Reduced width for better fit
LABEL_H_MM = 25  # Height matches sugar packet
LABELS_PER_ROW = 3
PAGE_MARGIN_MM = 5  # Reduced margin for better print area usage
LABEL_SPACING_MM = 2  # Reduced spacing between labels
PX_PER_MM = DPI / 25.4

# Single label dimensions
LABEL_W = int(LABEL_W_MM * PX_PER_MM)
LABEL_H = int(LABEL_H_MM * PX_PER_MM)

# Sheet dimensions for 3-up printing
PAGE_W_MM = PAGE_MARGIN_MM * 2 + LABEL_W_MM * LABELS_PER_ROW + LABEL_SPACING_MM * (LABELS_PER_ROW - 1)
PAGE_H_MM = PAGE_MARGIN_MM * 2 + LABEL_H_MM
PAGE_W = int(PAGE_W_MM * PX_PER_MM)
PAGE_H = int(PAGE_H_MM * PX_PER_MM)

STORE_NAME_DEFAULT = "SRI VELAVAN SUPERMARKET"  # Updated to match reference
PRINTER_NAME = "Bar Code Printer R220"   # ✅ exact Windows name

FONTS = {
    "bold": ImageFont.load_default(),
    "regular": ImageFont.load_default(),
    "tiny": ImageFont.load_default(),
}

FONTS["bold"] = ImageFont.truetype("label_printing\static\Inter_24pt-Bold.ttf", 18)
FONTS["regular"] = ImageFont.truetype("label_printing\static\Inter_18pt-Regular.ttf", 16)
FONTS["tiny"] = ImageFont.truetype("label_printing\static\Inter_18pt-Regular.ttf", 14)

# ---------- App ----------
app = Flask(__name__)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def query_products_by_name(q: str, limit: int = 20):
    with get_db() as conn:
        cur = conn.execute(
            "SELECT * FROM products WHERE name LIKE ? ORDER BY name LIMIT ?",
            (f"%{q}%", limit),
        )
        return [dict(row) for row in cur.fetchall()]


def get_product_by_barcode(barcode: str) -> Dict[str, Any] | None:
    with get_db() as conn:
        cur = conn.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
        row = cur.fetchone()
        return dict(row) if row else None


def _generate_barcode_pil(code_text: str) -> Image.Image:
    # Ensure 14 digits
    code_text = code_text.zfill(14)[:14]
    barcode_obj = Code128(code_text, writer=ImageWriter())
    buf = io.BytesIO()
    barcode_obj.write(buf, options={
        "module_width": 0.4,  # Increased width for better scanning
        "module_height": 18.0,  # Increased height for better scanning
        "quiet_zone": 6.0,  # Increased quiet zone for reliable scanning
        "write_text": False  # No text under barcode
    })
    buf.seek(0)
    return Image.open(buf).convert("RGB")

def compose_label(product: Dict[str, Any],
                  store_name: str = STORE_NAME_DEFAULT,
                  exp: str = "") -> Image.Image:
    """
    Formal, reference-style label:
      - rounded white panel with thin border
      - store name at top (center)
      - centered barcode (kept to a moderate height)
      - barcode digits under bars
      - product name centered
      - QTY (left) and Measure (right)
      - MRP (left) and RP (right) emphasized
    """
    # base image (white background)
    label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)
    cx = LABEL_W // 2

    # inner panel (rounded rectangle) to give 'sticker' look like your reference
    pad = max(4, int(PX_PER_MM * 0.8))
    panel_box = (pad, pad, LABEL_W - pad, LABEL_H - pad)
    corner_radius = max(6, int(PX_PER_MM * 1.2))
    # panel fill white and subtle border for a formal look
    draw.rounded_rectangle(panel_box, radius=corner_radius, fill="white", outline="black", width=1)

    # content start (inset inside the rounded panel)
    content_x0 = pad + int(PX_PER_MM * 0.6)
    content_x1 = LABEL_W - pad - int(PX_PER_MM * 0.6)
    content_width = content_x1 - content_x0
    y = pad + int(PX_PER_MM * 0.6)

    # 1) Store name - single centered line, uppercase, clipped if needed
    store_text = (store_name or STORE_NAME_DEFAULT).strip().upper()
    store_font = FONTS["bold"]
    max_store_w = content_width
    if draw.textlength(store_text, font=store_font) > max_store_w:
        # fallback to smaller font
        store_font = FONTS["regular"]
    # final clip/truncate if still too wide
    if draw.textlength(store_text, font=store_font) > max_store_w:
        # truncate with ellipsis
        while draw.textlength(store_text + "...", font=store_font) > max_store_w and len(store_text) > 3:
            store_text = store_text[:-1]
        store_text += "..."
    sw = draw.textlength(store_text, font=store_font)
    draw.text((cx - sw / 2, y), store_text, font=store_font, fill="black")
    y += int(PX_PER_MM * 3.0)  # leave breathing room below store name

    # 2) Barcode - generate, then cap width and *height* so it doesn't dominate the label
    bc_img = _generate_barcode_pil(str(product.get("barcode", "")).strip() or "0000000000000")
    # target max width/height for barcode inside panel
    max_bc_w = int(content_width * 0.95)
    max_bc_h = int(LABEL_H * 0.42)  # restrict height to maintain formal proportion
    # scale down while keeping aspect
    w_ratio = max_bc_w / bc_img.width if bc_img.width > max_bc_w else 1.0
    h_ratio = max_bc_h / bc_img.height if bc_img.height > max_bc_h else 1.0
    ratio = min(w_ratio, h_ratio, 1.0)
    if ratio < 1.0:
        new_w = max(1, int(bc_img.width * ratio))
        new_h = max(1, int(bc_img.height * ratio))
        bc_img = bc_img.resize((new_w, new_h), Image.Resampling.NEAREST)

    bc_x = cx - bc_img.width // 2
    label.paste(bc_img, (bc_x, y))

    # barcode bottom
    y = y + bc_img.height + int(PX_PER_MM * 0.2)

    # 2b) barcode digits (human readable) centered below barcode
    # barcode_digits = str(product.get("barcode", "")).strip()
    # if barcode_digits:
    #     digits_font = FONTS["tiny"]
    #     d_w = draw.textlength(barcode_digits, font=digits_font)
    #     draw.text((cx - d_w / 2, y), barcode_digits, font=digits_font, fill="black")
    #     y += int(PX_PER_MM * 1.2)

    # 3) Product name - centered, up to two lines if necessary
    prod_name = str(product.get("name", "")).strip()
    name_font = FONTS["regular"]
    max_name_w = content_width
    if draw.textlength(prod_name, font=name_font) <= max_name_w:
        draw.text((cx - draw.textlength(prod_name, font=name_font) / 2, y), prod_name, font=name_font, fill="black")
        y += int(PX_PER_MM * 2.0)
    else:
        # naive two-line wrap
        words = prod_name.split()
        line1 = ""
        line2 = ""
        for w in words:
            if draw.textlength((line1 + " " + w).strip(), font=name_font) <= max_name_w:
                line1 = (line1 + " " + w).strip()
            else:
                line2 = (line2 + " " + w).strip()
        if not line1:
            line1 = prod_name[:int(len(prod_name)/2)]
            line2 = prod_name[int(len(prod_name)/2):]
        # truncate lines if still too long
        def fit_line(s):
            while draw.textlength(s + "...", font=name_font) > max_name_w and len(s) > 3:
                s = s[:-1]
            return s + "..." if draw.textlength(s, font=name_font) > max_name_w else s
        line1 = fit_line(line1)
        line2 = fit_line(line2) if line2 else ""
        draw.text((cx - draw.textlength(line1, font=name_font) / 2, y), line1, font=name_font, fill="black")
        y += int(PX_PER_MM * 1.4)
        if line2:
            draw.text((cx - draw.textlength(line2, font=name_font) / 2, y), line2, font=name_font, fill="black")
            y += int(PX_PER_MM * 1.8)
        else:
            y += int(PX_PER_MM * 0.6)

    # 4) Info row: QTY (left) and Measure (right)
    info_font = FONTS["tiny"]
    left_info = f"QTY: {product.get('quantity', '')}"
    right_info = f"{product.get('measure', '')}"
    left_x = content_x0 + int(PX_PER_MM * 0.4)
    right_x = content_x1 - int(PX_PER_MM * 0.4) - draw.textlength(right_info, font=info_font)
    # guard against overlap
    if right_x - (left_x + draw.textlength(left_info, font=info_font)) < int(PX_PER_MM * 2):
        # make right shorter
        if len(right_info) > 6:
            right_info = right_info[:6] + "..."
            right_x = content_x1 - int(PX_PER_MM * 0.4) - draw.textlength(right_info, font=info_font)
    draw.text((left_x, y), left_info, font=info_font, fill="black")
    draw.text((right_x, y), right_info, font=info_font, fill="black")
    y += int(PX_PER_MM * 1.6)

    # 5) Price row: MRP left, RP right (emphasized)
    price_font = FONTS["bold"]
    mrp_text = f"MRP: ₹{product.get('mrp', 0):g}"
    rp_text = f"RP: ₹{product.get('retail_price', 0):g}"
    left_x = content_x0 + int(PX_PER_MM * 0.4)
    right_x = content_x1 - int(PX_PER_MM * 0.4) - draw.textlength(rp_text, font=price_font)
    # fallback if overlap
    if right_x - (left_x + draw.textlength(mrp_text, font=price_font)) < int(PX_PER_MM * 2):
        price_font = FONTS["regular"]
        right_x = content_x1 - int(PX_PER_MM * 0.4) - draw.textlength(rp_text, font=price_font)
    draw.text((left_x, y), mrp_text, font=price_font, fill="black")
    draw.text((right_x, y), rp_text, font=price_font, fill="black")
    y += int(PX_PER_MM * 1.0)

    return label


@app.get("/")
def index():
    return render_template("index.html", store_name=STORE_NAME_DEFAULT)


@app.get("/api/products")
def api_products():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    rows = query_products_by_name(q)
    results = [{
        "barcode": r["barcode"],
        "name": r["name"],
        "measure": r["measure"],
        "quantity": r["quantity"],
        "mrp": r["mrp"],
        "retail_price": r["retail_price"],
    } for r in rows]
    return jsonify(results)


@app.get("/preview")
def preview_label():
    barcode = request.args.get("barcode")
    store = request.args.get("store", STORE_NAME_DEFAULT)
    exp = request.args.get("exp", "")

    if barcode:
        product = get_product_by_barcode(barcode)
        if not product:
            return "Product not found", 404
    else:
        product = {
            "barcode": request.args.get("code", "0000000000000"),
            "name": request.args.get("name", "Sample"),
            "measure": request.args.get("measure", "KG"),
            "quantity": float(request.args.get("quantity", "1.0")),
            "mrp": float(request.args.get("mrp", "0")),
            "retail_price": float(request.args.get("retail_price", "0")),
        }

    img = compose_label(product, store_name=store, exp=exp)
    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(DPI, DPI))
    buf.seek(0)
    return send_file(buf, mimetype="image/png")
    

def compose_sheet(product: Dict[str, Any], count: int, store_name: str = STORE_NAME_DEFAULT, exp: str = "") -> Image.Image:
    # Create full sheet
    sheet = Image.new("RGB", (PAGE_W, PAGE_H), "white")
    
    # Calculate positions for 3-up layout
    label_w = LABEL_W
    label_h = LABEL_H
    margin_x = int(PAGE_MARGIN_MM * PX_PER_MM)
    margin_y = int(PAGE_MARGIN_MM * PX_PER_MM)
    spacing = int(LABEL_SPACING_MM * PX_PER_MM)
    
    # Generate single label once
    label = compose_label(product, store_name, exp)
    
    # Paste labels in 3-up layout
    labels_this_row = min(count, LABELS_PER_ROW)
    for i in range(labels_this_row):
        x = margin_x + i * (label_w + spacing)
        y = margin_y
        sheet.paste(label, (x, y))
    
    return sheet

@app.post("/api/print")
def api_print():
    data = request.get_json(force=True)
    barcode = (data.get("barcode") or "").strip()
    count = int(data.get("count") or 1)
    store = (data.get("store_name") or STORE_NAME_DEFAULT).strip()
    exp = (data.get("exp") or "").strip()

    if not barcode:
        return jsonify({"ok": False, "error": "barcode is required"}), 400

    product = get_product_by_barcode(barcode)
    if not product:
        return jsonify({"ok": False, "error": "product not found"}), 404

    # Generate sheet with 3 labels per row
    sheet = compose_sheet(product, count, store_name=store, exp=exp)
    tmp_path = os.path.abspath("label_sheet.png")
    sheet.save(tmp_path, format="PNG", dpi=(DPI, DPI))

    printed = 0
    errors = []
    try:
        print_image(tmp_path, title="Labels", printer_name=PRINTER_NAME)
        printed = count
    except Exception as e:
        available = [p[2] for p in win32print.EnumPrinters(2)]
        errors.append(f"{str(e)} | Available printers: {available}")
        printed = 0

    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return jsonify({
        "ok": printed == count,
        "printed": printed,
        "errors": errors
    }), (200 if printed == count else 500)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
