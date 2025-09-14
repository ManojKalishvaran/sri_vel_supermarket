# app_label_fix.py
# Updated to fix horizontal offset and improve barcode readability (wider bars).
# Label stock: 32mm x 20mm, 3 mm gaps between labels/rows.

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

# Printer / label stock settings
DPI = 203                # R220 native DPI
LABEL_W_MM = 32.0        # 3.2 cm width
LABEL_H_MM = 20.0        # 2.0 cm height
LABELS_PER_ROW = 3       # exactly 3 labels per row

# Margins and spacing (user said 3 mm gap between adjacent labels/rows)
PAGE_MARGIN_MM = 3.5    # outer page margin (left & right) (change it to 1.5 or 2 if continues to cut off)
LABEL_SPACING_MM = 3.0   # gap between adjacent labels (horizontal & vertical)
# Small global X offset to correct left/right shift of printed grid.
# Negative moves labels left, positive moves labels right. Default tuned left (-0.6 mm).
GLOBAL_X_OFFSET_MM = -0.6

PX_PER_MM = DPI / 25.4   # pixels per mm at given DPI

# pixel dims
LABEL_W = int(round(LABEL_W_MM * PX_PER_MM))
LABEL_H = int(round(LABEL_H_MM * PX_PER_MM))

STORE_NAME_DEFAULT = "SRI VELAVAN SUPERMARKET"
PRINTER_NAME = "Bar Code Printer R220"

# load fonts with graceful fallback
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
    Generate barcode optimized for thermal printing (203 DPI).
    Increased module_width for thicker bars to improve scanner reliability.
    """
    code_text = str(code_text or "").strip()
    if not code_text.isdigit():
        code_text = code_text.zfill(14)[:14]
    else:
        code_text = code_text.zfill(14)[:14]

    barcode_obj = Code128(code_text, writer=ImageWriter())
    buf = io.BytesIO()

    # Wider module_width (0.40) for thicker bars on thermal head,
    # module_height increased slightly to give barcode ample vertical stroke for scanning.
    barcode_obj.write(buf, options={
        "module_width": 0.60,    # increased from 0.33 to 0.40 for sturdier bars
        "module_height": 16.0,   # a bit taller to help cheap scanners
        "quiet_zone": 4.0,       # quiet zone (tunable)
        "write_text": False,
        "background": "white",
        "foreground": "black",
        "dpi": DPI
    })
    buf.seek(0)

    # Open as grayscale; threshold at 128 produces crisp black/white bars.
    img = Image.open(buf).convert("L")
    img = img.point(lambda p: 0 if p < 128 else 255, mode="1").convert("RGB")

    # Trim whitespace while keeping small quiet-zone padding
    bbox = img.convert("L").point(lambda p: 0 if p < 250 else 255).getbbox()
    if bbox:
        left, upper, right, lower = bbox
        pad = max(1, int(round(PX_PER_MM * 0.6)))  # ~0.6 mm
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
    Compose one label sized LABEL_W x LABEL_H pixels.
    """
    label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)
    cx = LABEL_W // 2

    # inner rounded panel
    pad = max(2, int(round(PX_PER_MM * 0.6)))
    panel = (pad, pad, LABEL_W - pad, LABEL_H - pad)
    corner_radius = max(3, int(round(PX_PER_MM * 0.8)))
    draw.rounded_rectangle(panel, radius=corner_radius, fill="white", outline="black", width=1)

    content_x0 = pad + int(round(PX_PER_MM * 0.4))
    content_x1 = LABEL_W - pad - int(round(PX_PER_MM * 0.4))
    content_width = content_x1 - content_x0
    y = pad + int(round(PX_PER_MM * 0.4))

    # store name (centered)
    store_text = (store_name or STORE_NAME_DEFAULT).strip().upper()
    store_font = FONTS["bold"]
    if draw.textlength(store_text, font=store_font) > content_width:
        store_font = FONTS["regular"]
    if draw.textlength(store_text, font=store_font) > content_width:
        while draw.textlength(store_text + "...", font=store_font) > content_width and len(store_text) > 3:
            store_text = store_text[:-1]
        store_text += "..."
    sw = draw.textlength(store_text, font=store_font)
    draw.text((cx - sw / 2, y), store_text, font=store_font, fill="black")
    y += int(round(PX_PER_MM * 2.4))

    # barcode area
    bc_img = _generate_barcode_pil(str(product.get("barcode", "")).strip() or "0000000000000")
    max_bc_w = int(round(content_width * 0.95))
    max_bc_h = int(round(LABEL_H * 0.46))  # give more height room for taller module_height
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

    # product name (wrap if needed)
    prod_name = str(product.get("name", "")).strip()
    name_font = FONTS["regular"]
    if draw.textlength(prod_name, font=name_font) <= content_width:
        draw.text((cx - draw.textlength(prod_name, font=name_font) / 2, y), prod_name, font=name_font, fill="black")
        y += int(round(PX_PER_MM * 1.8))
    else:
        words = prod_name.split()
        l1, l2 = "", ""
        for w in words:
            if draw.textlength((l1 + " " + w).strip(), font=name_font) <= content_width:
                l1 = (l1 + " " + w).strip()
            else:
                l2 = (l2 + " " + w).strip()
        if not l1:
            l1 = prod_name[:int(len(prod_name) / 2)]
            l2 = prod_name[int(len(prod_name) / 2):]
        def fit_line(s):
            while draw.textlength(s + "...", font=name_font) > content_width and len(s) > 3:
                s = s[:-1]
            return s + "..." if draw.textlength(s, font=name_font) > content_width else s
        l1 = fit_line(l1)
        l2 = fit_line(l2) if l2 else ""
        draw.text((cx - draw.textlength(l1, font=name_font) / 2, y), l1, font=name_font, fill="black")
        y += int(round(PX_PER_MM * 1.1))
        if l2:
            draw.text((cx - draw.textlength(l2, font=name_font) / 2, y), l2, font=name_font, fill="black")
            y += int(round(PX_PER_MM * 1.6))
        else:
            y += int(round(PX_PER_MM * 0.6))

    # info row (QTY and measure)
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

    # price row
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
    Compose sheet containing `count` labels in rows of LABELS_PER_ROW.
    Uses GLOBAL_X_OFFSET_MM for small left/right adjustments.
    """
    rows = math.ceil(max(1, count) / LABELS_PER_ROW)

    margin_x = int(round(PAGE_MARGIN_MM * PX_PER_MM))
    margin_y = int(round(PAGE_MARGIN_MM * PX_PER_MM))
    spacing = int(round(LABEL_SPACING_MM * PX_PER_MM))
    global_x_offset = int(round(GLOBAL_X_OFFSET_MM * PX_PER_MM))

    sheet_w = margin_x * 2 + LABEL_W * LABELS_PER_ROW + spacing * (LABELS_PER_ROW - 1)
    sheet_h = margin_y * 2 + LABEL_H * rows + spacing * (rows - 1)

    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")

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
    """Print image to Windows printer (Rongta R220) with exact sizing."""
    if not WINDOWS_PRINTING_AVAILABLE:
        raise RuntimeError("Windows printing is not available on this system.")

    if not printer_name:
        printer_name = win32print.GetDefaultPrinter()

    img = Image.open(image_path)
    if img.mode != '1':
        img = img.convert('L')
        img = img.point(lambda x: 0 if x < 128 else 255, '1')  # crisp B/W

    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    dpi_x = hDC.GetDeviceCaps(88)  # LOGPIXELSX
    dpi_y = hDC.GetDeviceCaps(90)  # LOGPIXELSY

    # Convert image pixel size to printer DPI
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
    Visual calibration PNG so you can adjust offset_mm & spacing_mm quickly.
    Params:
      - offset_mm: override GLOBAL_X_OFFSET_MM
      - spacing_mm: override LABEL_SPACING_MM
      - count: number of labels to display (default 3)
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

    sample = {
        "barcode": "123456789012",
        "name": "Aachi Chicken Masala",
        "measure": "PC",
        "quantity": 1,
        "mrp": 39,
        "retail_price": 38
    }

    margin_x = int(round(PAGE_MARGIN_MM * PX_PER_MM))
    margin_y = int(round(PAGE_MARGIN_MM * PX_PER_MM))
    spacing = int(round(spacing_mm * PX_PER_MM))
    global_x_offset = int(round(offset_mm * PX_PER_MM))

    rows = math.ceil(max(1, count) / LABELS_PER_ROW)
    sheet_w = margin_x * 2 + LABEL_W * LABELS_PER_ROW + spacing * (LABELS_PER_ROW - 1)
    sheet_h = margin_y * 2 + LABEL_H * rows + spacing * (rows - 1)
    sheet = Image.new("RGB", (sheet_w, sheet_h), "white")

    label_img = compose_label(sample)
    draw = ImageDraw.Draw(sheet)

    pasted = 0
    for r in range(rows):
        for c in range(LABELS_PER_ROW):
            x = margin_x + c * (LABEL_W + spacing) + global_x_offset
            y = margin_y + r * (LABEL_H + spacing)
            draw.rectangle((x, y, x + LABEL_W - 1, y + LABEL_H - 1), outline="red", width=1)
            if pasted < count:
                sheet.paste(label_img, (x, y))
            draw.text((x + 2, y + 2), str(pasted + 1), font=FONTS["tiny"], fill="red")
            pasted += 1

    buf = io.BytesIO()
    sheet.save(buf, format="PNG", dpi=(DPI, DPI))
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
