# app_label_fix.py
# Modified label-printing server to produce consistent, scanner-friendly labels.
# Combines printing helper so it's a single file replacement for your previous app.py.

import io
import os
import sqlite3
from datetime import datetime
from typing import Dict, Any

from flask import Flask, jsonify, request, send_file, render_template
from PIL import Image, ImageDraw, ImageFont, ImageOps
from barcode import Code128
from barcode.writer import ImageWriter

import math


# try to import win32 printing helpers when on Windows
try:
    import win32print
    import win32ui
    from PIL import ImageWin
    WINDOWS_PRINTING_AVAILABLE = True
except Exception:
    WINDOWS_PRINTING_AVAILABLE = False

# ---------- Config ----------
DB_PATH = r"Data\products.db"

# Keep DPI matching your thermal printer (203 or 300). 203 is common for label printers.
DPI = 203
LABEL_W_MM = 40
LABEL_H_MM = 25
LABELS_PER_ROW = 3
PAGE_MARGIN_MM = 5
LABEL_SPACING_MM = 2
PX_PER_MM = DPI / 25.4

# Single label dimensions
LABEL_W = int(LABEL_W_MM * PX_PER_MM)
LABEL_H = int(LABEL_H_MM * PX_PER_MM)

# Sheet dimensions
PAGE_W_MM = PAGE_MARGIN_MM * 2 + LABEL_W_MM * LABELS_PER_ROW + LABEL_SPACING_MM * (LABELS_PER_ROW - 1)
PAGE_H_MM = PAGE_MARGIN_MM * 2 + LABEL_H_MM
PAGE_W = int(PAGE_W_MM * PX_PER_MM)
PAGE_H = int(PAGE_H_MM * PX_PER_MM)

STORE_NAME_DEFAULT = "SRI VELAVAN SUPERMARKET"
PRINTER_NAME = "Bar Code Printer R220"

# load fonts (fallback to default if not found)
FONTS = {}
try:
    FONTS["bold"] = ImageFont.truetype("label_printing/static/Inter_24pt-Bold.ttf", 18)
    FONTS["regular"] = ImageFont.truetype("label_printing/static/Inter_18pt-Regular.ttf", 16)
    FONTS["tiny"] = ImageFont.truetype("label_printing/static/Inter_18pt-Regular.ttf", 14)
except Exception:
    FONTS["bold"] = ImageFont.load_default()
    FONTS["regular"] = ImageFont.load_default()
    FONTS["tiny"] = ImageFont.load_default()

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
    """
    Generate a barcode PIL image tuned for small labels and reliable scanning:
    - produces a compact barcode with thicker modules and taller bars
    - removes excessive white margins and crops tightly around the bars (keeping small quiet zone)
    """
    # ensure length and digits
    code_text = code_text.zfill(14)[:14]
    barcode_obj = Code128(code_text, writer=ImageWriter())
    buf = io.BytesIO()
    # increase module width & height to make bars bolder for cheap cameras
    barcode_obj.write(buf, options={
        "module_width": 0.9,    # thicker bars -> easier to read
        "module_height": 48.0,  # taller bars
        "quiet_zone": 6.0,      # small quiet zone
        "font_size": 10,
        "text_distance": 1.0,
        "write_text": False,
    })
    buf.seek(0)
    img = Image.open(buf).convert("RGB")

    # Convert to pure black/white to increase scanner contrast
    img = img.convert("L")
    img = img.point(lambda p: 0 if p < 200 else 255, mode="1").convert("RGB")

    # crop to non-white area but keep a small margin (quiet zone)
    bbox = img.convert("L").point(lambda p: 0 if p < 250 else 255).getbbox()
    if bbox:
        left, upper, right, lower = bbox
        # expand a bit for quiet zone
        pad = max(2, int(PX_PER_MM * 0.5))
        left = max(0, left - pad)
        upper = max(0, upper - pad)
        right = min(img.width, right + pad)
        lower = min(img.height, lower + pad)
        img = img.crop((left, upper, right, lower))

    return img

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

    # # 2b) barcode digits (human readable) centered below barcode
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
    """
    Compose a sheet that places labels in fixed, identical positions,
    with exactly LABELS_PER_ROW labels per row (mandatory).
    The sheet height is computed to fit `count` labels.
    Blank spaces remain white if count does not fill the final row.
    """
    # calculate number of rows required (always ceil)
    rows = math.ceil(max(1, count) / LABELS_PER_ROW)

    # compute sheet pixel dimensions dynamically
    margin_x = int(PAGE_MARGIN_MM * PX_PER_MM)
    margin_y = int(PAGE_MARGIN_MM * PX_PER_MM)
    spacing = int(LABEL_SPACING_MM * PX_PER_MM)

    sheet_w = margin_x * 2 + LABEL_W * LABELS_PER_ROW + spacing * (LABELS_PER_ROW - 1)
    sheet_h = margin_y * 2 + LABEL_H * rows + spacing * (rows - 1)

    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")

    # pre-compose single label so all labels are identical
    label_img = compose_label(product, store_name=store_name, exp=exp)

    # paste labels in exact grid positions: left-to-right, top-to-bottom
    pasted = 0
    for r in range(rows):
        for c in range(LABELS_PER_ROW):
            if pasted >= count:
                # leave blank if no more labels requested (ensures consistent positions)
                pasted += 1
                continue
            x = margin_x + c * (LABEL_W + spacing)
            y = margin_y + r * (LABEL_H + spacing)
            sheet.paste(label_img, (x, y))
            pasted += 1

    return sheet

def print_image_windows(image_path: str, title: str = "Label Print", printer_name: str = None):
    """Simple image print helper for Windows printers (uses win32ui/win32print).
    Centers horizontally and prints at 1:1 pixel scale when possible so label sizing remains accurate.
    """
    if not WINDOWS_PRINTING_AVAILABLE:
        raise RuntimeError("Windows printing is not available on this system.")

    if not printer_name:
        printer_name = win32print.GetDefaultPrinter()

    img = Image.open(image_path)

    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    printable_area = hDC.GetDeviceCaps(8), hDC.GetDeviceCaps(10)
    # physical size in pixels
    physical_size = hDC.GetDeviceCaps(110), hDC.GetDeviceCaps(111)

    img_w, img_h = img.size
    max_w, max_h = printable_area

    # If printable area is larger than image, print at actual size (no up/down scaling)
    # but still ensure it fits by scaling down if needed.
    ratio = min(max_w / img_w, max_h / img_h, 1.0)
    target_w = int(img_w * ratio)
    target_h = int(img_h * ratio)

    if img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize((target_w, target_h), Image.Resampling.NEAREST)

    hDC.StartDoc(title)
    hDC.StartPage()

    dib = ImageWin.Dib(img)
    x = int((max_w - target_w) / 2)
    y = 0
    dib.draw(hDC.GetHandleOutput(), (x, y, x + target_w, y + target_h))

    hDC.EndPage()
    hDC.EndDoc()
    hDC.DeleteDC()


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

    # Compose a sheet with exactly 3 labels per row (rows auto-computed)
    sheet = compose_sheet(product, count, store_name=store, exp=exp)
    tmp_path = os.path.abspath("label_sheet.png")
    # save with DPI so printer scales correctly
    sheet.save(tmp_path, format="PNG", dpi=(DPI, DPI))

    # rest of your printing logic unchanged...
    printed = 0
    errors = []
    try:
        print_image_windows(tmp_path, title="Labels", printer_name=PRINTER_NAME)
        printed = count
    except Exception as e:
        available = []
        try:
            available = [p[2] for p in win32print.EnumPrinters(2)]
        except Exception:
            pass
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
