# app_label_fix.py
# Full updated label-printing server (drop-in replacement)

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

# Rongta R220 printer settings
DPI = 203  # R220 native DPI
LABEL_W_MM = 32  # Label width (3.2 cm)
LABEL_H_MM = 20  # Label height (2.0 cm)
LABELS_PER_ROW = 3  # 3-up printing

# Margins/spacing - tweak these if your physical sheet differs
PAGE_MARGIN_MM = 2.0          # outer page margin (both left & right by default)
LABEL_SPACING_MM = 3.0        # gap between adjacent labels
GLOBAL_X_OFFSET_MM = 0.0      # positive moves labels right, negative moves left (calibration)

PX_PER_MM = DPI / 25.4  # Pixel density

# Single label dimensions (pixels)
LABEL_W = int(round(LABEL_W_MM * PX_PER_MM))
LABEL_H = int(round(LABEL_H_MM * PX_PER_MM))

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
    Generate a barcode optimized for thermal printer (R220) and reliable scanning.
    Tuned for 203 DPI: slightly larger module width & height, stable thresholding.
    """
    # normalize to digits length
    code_text = str(code_text or "").strip()
    if not code_text.isdigit():
        # keep whatever was provided, pad/truncate for deterministic result
        code_text = code_text.zfill(14)[:14]
    else:
        code_text = code_text.zfill(14)[:14]

    barcode_obj = Code128(code_text, writer=ImageWriter())
    buf = io.BytesIO()

    # Barcode writer options tuned for thermal printing
    # module_width is in mm-ish units interpreted by the writer; DPI specified for scaling
    barcode_obj.write(buf, options={
        "module_width": 0.33,    # slightly wider for thermal head reliability
        "module_height": 14.0,   # good vertical height for scanners
        "quiet_zone": 4.0,       # a conservative quiet zone
        "write_text": False,
        "background": "white",
        "foreground": "black",
        "dpi": DPI
    })
    buf.seek(0)

    # open as grayscale for robust thresholding
    img = Image.open(buf).convert("L")

    # threshold at 128 for crisp 1-bit black/white (avoid too-high threshold which can break bars)
    img = img.point(lambda p: 0 if p < 128 else 255, mode="1").convert("RGB")

    # Trim surrounding whitespace but keep a small padding as quiet zone
    bbox = img.convert("L").point(lambda p: 0 if p < 250 else 255).getbbox()
    if bbox:
        left, upper, right, lower = bbox
        pad = max(1, int(round(PX_PER_MM * 0.6)))  # ~0.6 mm padding
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
    Compose a single label image sized exactly LABEL_W x LABEL_H (pixels).
    Layout: rounded panel, store name, barcode, product name, info rows, price rows.
    """
    label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)
    cx = LABEL_W // 2

    # inner panel
    pad = max(2, int(round(PX_PER_MM * 0.6)))
    panel_box = (pad, pad, LABEL_W - pad, LABEL_H - pad)
    corner_radius = max(3, int(round(PX_PER_MM * 0.8)))
    draw.rounded_rectangle(panel_box, radius=corner_radius, fill="white", outline="black", width=1)

    content_x0 = pad + int(round(PX_PER_MM * 0.4))
    content_x1 = LABEL_W - pad - int(round(PX_PER_MM * 0.4))
    content_width = content_x1 - content_x0
    y = pad + int(round(PX_PER_MM * 0.4))

    # Store name
    store_text = (store_name or STORE_NAME_DEFAULT).strip().upper()
    store_font = FONTS["bold"]
    max_store_w = content_width
    if draw.textlength(store_text, font=store_font) > max_store_w:
        store_font = FONTS["regular"]
    if draw.textlength(store_text, font=store_font) > max_store_w:
        # truncate with ellipsis
        while draw.textlength(store_text + "...", font=store_font) > max_store_w and len(store_text) > 3:
            store_text = store_text[:-1]
        store_text += "..."
    sw = draw.textlength(store_text, font=store_font)
    draw.text((cx - sw / 2, y), store_text, font=store_font, fill="black")
    y += int(round(PX_PER_MM * 2.4))

    # Barcode
    bc_img = _generate_barcode_pil(str(product.get("barcode", "")).strip() or "0000000000000")
    # Fit barcode within content width and a limited height fraction
    max_bc_w = int(round(content_width * 0.95))
    max_bc_h = int(round(LABEL_H * 0.42))
    w_ratio = max_bc_w / bc_img.width if bc_img.width > max_bc_w else 1.0
    h_ratio = max_bc_h / bc_img.height if bc_img.height > max_bc_h else 1.0
    ratio = min(w_ratio, h_ratio, 1.0)
    if ratio < 1.0:
        new_w = max(1, int(bc_img.width * ratio))
        new_h = max(1, int(bc_img.height * ratio))
        bc_img = bc_img.resize((new_w, new_h), Image.Resampling.NEAREST)

    bc_x = cx - bc_img.width // 2
    label.paste(bc_img, (bc_x, y))
    y = y + bc_img.height + int(round(PX_PER_MM * 0.16))

    # Product name (one or two lines)
    prod_name = str(product.get("name", "")).strip()
    name_font = FONTS["regular"]
    max_name_w = content_width
    if draw.textlength(prod_name, font=name_font) <= max_name_w:
        draw.text((cx - draw.textlength(prod_name, font=name_font) / 2, y), prod_name, font=name_font, fill="black")
        y += int(round(PX_PER_MM * 1.8))
    else:
        words = prod_name.split()
        line1 = ""
        line2 = ""
        for w in words:
            if draw.textlength((line1 + " " + w).strip(), font=name_font) <= max_name_w:
                line1 = (line1 + " " + w).strip()
            else:
                line2 = (line2 + " " + w).strip()
        if not line1:
            line1 = prod_name[:int(len(prod_name) / 2)]
            line2 = prod_name[int(len(prod_name) / 2):]
        def fit_line(s):
            while draw.textlength(s + "...", font=name_font) > max_name_w and len(s) > 3:
                s = s[:-1]
            return s + "..." if draw.textlength(s, font=name_font) > max_name_w else s
        line1 = fit_line(line1)
        line2 = fit_line(line2) if line2 else ""
        draw.text((cx - draw.textlength(line1, font=name_font) / 2, y), line1, font=name_font, fill="black")
        y += int(round(PX_PER_MM * 1.1))
        if line2:
            draw.text((cx - draw.textlength(line2, font=name_font) / 2, y), line2, font=name_font, fill="black")
            y += int(round(PX_PER_MM * 1.6))
        else:
            y += int(round(PX_PER_MM * 0.6))

    # Info row: QTY and Measure
    info_font = FONTS["tiny"]
    left_info = f"QTY: {product.get('quantity', '')}"
    right_info = f"{product.get('measure', '')}"
    left_x = content_x0 + int(round(PX_PER_MM * 0.3))
    right_x = content_x1 - int(round(PX_PER_MM * 0.3)) - draw.textlength(right_info, font=info_font)
    if right_x - (left_x + draw.textlength(left_info, font=info_font)) < int(round(PX_PER_MM * 1.6)):
        if len(right_info) > 6:
            right_info = right_info[:6] + "..."
            right_x = content_x1 - int(round(PX_PER_MM * 0.3)) - draw.textlength(right_info, font=info_font)
    draw.text((left_x, y), left_info, font=info_font, fill="black")
    draw.text((right_x, y), right_info, font=info_font, fill="black")
    y += int(round(PX_PER_MM * 1.4))

    # Price row: MRP and RP
    price_font = FONTS["bold"]
    try:
        mrp_val = float(product.get("mrp", 0))
    except Exception:
        mrp_val = 0
    try:
        rp_val = float(product.get("retail_price", 0))
    except Exception:
        rp_val = 0
    mrp_text = f"MRP: ₹{mrp_val:g}"
    rp_text = f"RP: ₹{rp_val:g}"
    left_x = content_x0 + int(round(PX_PER_MM * 0.3))
    right_x = content_x1 - int(round(PX_PER_MM * 0.3)) - draw.textlength(rp_text, font=price_font)
    if right_x - (left_x + draw.textlength(mrp_text, font=price_font)) < int(round(PX_PER_MM * 1.6)):
        price_font = FONTS["regular"]
        right_x = content_x1 - int(round(PX_PER_MM * 0.3)) - draw.textlength(rp_text, font=price_font)
    draw.text((left_x, y), mrp_text, font=price_font, fill="black")
    draw.text((right_x, y), rp_text, font=price_font, fill="black")
    y += int(round(PX_PER_MM * 0.8))

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
    Compose a sheet with exactly LABELS_PER_ROW per row, rows computed automatically.
    Applies a global X offset (in mm) for calibration of physical sheets.
    """
    rows = math.ceil(max(1, count) / LABELS_PER_ROW)

    # dynamic pixel values
    margin_x = int(round(PAGE_MARGIN_MM * PX_PER_MM))
    margin_y = int(round(PAGE_MARGIN_MM * PX_PER_MM))
    spacing = int(round(LABEL_SPACING_MM * PX_PER_MM))
    global_x_offset = int(round(GLOBAL_X_OFFSET_MM * PX_PER_MM))

    sheet_w = margin_x * 2 + LABEL_W * LABELS_PER_ROW + spacing * (LABELS_PER_ROW - 1)
    sheet_h = margin_y * 2 + LABEL_H * rows + spacing * (rows - 1)

    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")

    # create a single label image and paste multiple times
    label_img = compose_label(product, store_name=store_name, exp=exp)

    pasted = 0
    for r in range(rows):
        for c in range(LABELS_PER_ROW):
            if pasted >= count:
                pasted += 1
                continue
            x = margin_x + c * (LABEL_W + spacing) + global_x_offset
            y = margin_y + r * (LABEL_H + spacing)
            sheet.paste(label_img, (x, y))
            pasted += 1

    return sheet


def print_image_windows(image_path: str, title: str = "Label Print", printer_name: str = None):
    """Windows printing helper for Rongta R220 thermal printer."""
    if not WINDOWS_PRINTING_AVAILABLE:
        raise RuntimeError("Windows printing is not available on this system.")

    if not printer_name:
        printer_name = win32print.GetDefaultPrinter()

    # Open and threshold to pure B/W for thermal printing
    img = Image.open(image_path)
    if img.mode != '1':
        img = img.convert('L')
        img = img.point(lambda x: 0 if x < 128 else 255, '1')

    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    # For R220 we want exact size output by converting image pixels using device DPI
    dpi_x = hDC.GetDeviceCaps(88)  # LOGPIXELSX
    dpi_y = hDC.GetDeviceCaps(90)  # LOGPIXELSY

    # Convert image size to printer's native DPI
    img_w = int(img.width * dpi_x / DPI)
    img_h = int(img.height * dpi_y / DPI)

    if img.size != (img_w, img_h):
        img = img.resize((img_w, img_h), Image.Resampling.NEAREST)

    hDC.StartDoc(title)
    hDC.StartPage()

    dib = ImageWin.Dib(img)
    dib.draw(hDC.GetHandleOutput(), (0, 0, img_w, img_h))

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

    # Compose a sheet and save temporarily
    sheet = compose_sheet(product, count, store_name=store, exp=exp)
    tmp_path = os.path.abspath("label_sheet.png")
    sheet.save(tmp_path, format="PNG", dpi=(DPI, DPI))

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


@app.get("/calibrate")
def calibrate():
    """
    Return a visual calibration sheet (PNG) for testing offsets & spacing.
    Query params:
      - offset_mm: override GLOBAL_X_OFFSET_MM for preview
      - spacing_mm: override LABEL_SPACING_MM for preview
      - count: how many labels to show (default 3)
    """
    try:
        offset_mm = float(request.args.get("offset_mm", GLOBAL_X_OFFSET_MM))
    except Exception:
        offset_mm = GLOBAL_X_OFFSET_MM
    try:
        spacing_mm = float(request.args.get("spacing_mm", LABEL_SPACING_MM))
    except Exception:
        spacing_mm = LABEL_SPACING_MM
    try:
        count = int(request.args.get("count", 3))
    except Exception:
        count = 3

    # small sample product
    sample = {
        "barcode": "123456789012",
        "name": "Aachi Chicken Masala",
        "measure": "PC",
        "quantity": 1,
        "mrp": 39,
        "retail_price": 38
    }

    # temporary override global vars for rendering the preview
    old_spacing = LABEL_SPACING_MM
    old_offset = GLOBAL_X_OFFSET_MM
    try:
        # local compute using supplied params
        margin_x = int(round(PAGE_MARGIN_MM * PX_PER_MM))
        margin_y = int(round(PAGE_MARGIN_MM * PX_PER_MM))
        spacing = int(round(spacing_mm * PX_PER_MM))
        global_x_offset = int(round(offset_mm * PX_PER_MM))

        rows = math.ceil(max(1, count) / LABELS_PER_ROW)
        sheet_w = margin_x * 2 + LABEL_W * LABELS_PER_ROW + spacing * (LABELS_PER_ROW - 1)
        sheet_h = margin_y * 2 + LABEL_H * rows + spacing * (rows - 1)
        sheet = Image.new("RGB", (sheet_w, sheet_h), "white")

        # Draw boxes for label positions and paste sample labels
        label_img = compose_label(sample)
        draw = ImageDraw.Draw(sheet)
        pasted = 0
        for r in range(rows):
            for c in range(LABELS_PER_ROW):
                x = margin_x + c * (LABEL_W + spacing) + global_x_offset
                y = margin_y + r * (LABEL_H + spacing)
                # draw rectangle guide
                draw.rectangle((x, y, x + LABEL_W - 1, y + LABEL_H - 1), outline="red", width=1)
                if pasted < count:
                    sheet.paste(label_img, (x, y))
                # write small index
                draw.text((x + 2, y + 2), str(pasted + 1), font=FONTS["tiny"], fill="red")
                pasted += 1

        buf = io.BytesIO()
        sheet.save(buf, format="PNG", dpi=(DPI, DPI))
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    finally:
        LABEL_SPACING_MM = old_spacing
        GLOBAL_X_OFFSET_MM = old_offset


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
