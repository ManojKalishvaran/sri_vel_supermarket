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
DB_PATH = r"\Data\products.db"

DPI = 300
LABEL_W_MM = 45  # Adjusted for better readability
LABEL_H_MM = 25  # Height matches sugar packet
LABELS_PER_ROW = 3
PAGE_MARGIN_MM = 10  # Increased margin for better printer handling
LABEL_SPACING_MM = 5  # Increased spacing between labels
PX_PER_MM = DPI / 25.4

# Single label dimensions
LABEL_W = int(LABEL_W_MM * PX_PER_MM)
LABEL_H = int(LABEL_H_MM * PX_PER_MM)

# Sheet dimensions for 3-up printing
PAGE_W_MM = PAGE_MARGIN_MM * 2 + LABEL_W_MM * LABELS_PER_ROW + LABEL_SPACING_MM * (LABELS_PER_ROW - 1)
PAGE_H_MM = PAGE_MARGIN_MM * 2 + LABEL_H_MM
PAGE_W = int(PAGE_W_MM * PX_PER_MM)
PAGE_H = int(PAGE_H_MM * PX_PER_MM)

STORE_NAME_DEFAULT = "EM.PE.EM SUPER MARKET"  # Updated to match reference
PRINTER_NAME = "Bar Code Printer R220"   # ✅ exact Windows name

FONTS = {
    "bold": ImageFont.load_default(),
    "regular": ImageFont.load_default(),
    "tiny": ImageFont.load_default(),
}

FONTS["bold"] = ImageFont.truetype("label_printing\static\Inter_24pt-Bold.ttf", 16)
FONTS["regular"] = ImageFont.truetype("label_printing\static\Inter_18pt-Regular.ttf", 14)
FONTS["tiny"] = ImageFont.truetype("label_printing\static\Inter_18pt-Regular.ttf", 12)

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
        "module_width": 0.3,  # Width matching reference
        "module_height": 15.0,  # Height matching reference
        "quiet_zone": 3,  # Quiet zone matching reference
        "write_text": False  # No text under barcode
    })
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def compose_label(product: Dict[str, Any],
                  store_name: str = STORE_NAME_DEFAULT,
                  exp: str = "") -> Image.Image:
    label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)

    # Margins
    margin = int(1.5 * PX_PER_MM)
    x = margin
    y = margin
    center_x = LABEL_W // 2

    # 1) Store name
    text_width = draw.textlength(store_name, font=FONTS["bold"])
    draw.text((center_x - text_width/2, y), store_name, font=FONTS["bold"], fill="black")
    y += 28

    # 2) Barcode centered
    bc_img = _generate_barcode_pil(product["barcode"])
    ratio = min((LABEL_W - 2*margin) * 0.95 / bc_img.width, 1.0)
    bc_w = int(bc_img.width * ratio)
    bc_h = 30
    bc_img = bc_img.resize((bc_w, bc_h))
    bc_x = center_x - bc_w//2
    label.paste(bc_img, (bc_x, y))
    y += bc_h + 12

    # 3) Product quantity and measure
    qty_text = f"{product['name']}      {product['quantity']:g} {product['measure']}"
    draw.text((x, y), qty_text, font=FONTS["regular"], fill="black")
    y += 15

    # 4) MRP and retail price
    price_text = f"MRP: {product['mrp']:g}      Rs. {product['retail_price']:g}"
    draw.text((x, y), price_text, font=FONTS["tiny"], fill="black")
    y += 12

    # 5) PKD and EXP
    pkd = datetime.now().strftime("%d.%m.%y")
    date_text = f"PKD: {pkd}    EXP: {exp or ''}"
    draw.text((x, y), date_text, font=FONTS["tiny"], fill="black")

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
