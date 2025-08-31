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

from barcode_print import print_image_to_default_printer

# ---------- Config ----------
DB_PATH = "Data/products.db"

# Label geometry (forward-thinking: size in mm -> pixels at chosen DPI)
DPI = 300                  # typical thermal / label DPI
LABEL_W_MM = 50            # 50mm x 30mm ~ 2" x 1.2"
LABEL_H_MM = 30
PX_PER_MM = DPI / 25.4
LABEL_W = int(LABEL_W_MM * PX_PER_MM)
LABEL_H = int(LABEL_H_MM * PX_PER_MM)

STORE_NAME_DEFAULT = "Sri Velavan Supermarket"  # your store name
FONTS = {
    "bold": ImageFont.load_default(),
    "regular": ImageFont.load_default(),
    "tiny": ImageFont.load_default(),
}

# If you have TTF fonts, uncomment & point to them:
FONTS["bold"] = ImageFont.truetype("D:\Bill priting\SUPERMARKET-MANAGEMENT\Final_APIs\label_printing\static\Inter_24pt-Bold.ttf", 24)
FONTS["regular"] = ImageFont.truetype("D:\Bill priting\SUPERMARKET-MANAGEMENT\Final_APIs\label_printing\static\Inter_18pt-Regular.ttf", 18)
FONTS["tiny"] = ImageFont.truetype("D:\Bill priting\SUPERMARKET-MANAGEMENT\Final_APIs\label_printing\static\Inter_18pt-Regular.ttf", 16)

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


# def _generate_barcode_pil(code_text: str) -> Image.Image:
#     """Return a PIL Image for a Code128 barcode."""
#     barcode_obj = Code128(code_text, writer=ImageWriter())
#     # write to a bytes buffer instead of file
#     buf = io.BytesIO()
#     barcode_obj.write(buf, options={
#         "module_width": 0.2,     # thin bars
#         "module_height": 18.0,   # bar height in mm-ish; writer uses its own units
#         "font_size": 10,
#         "write_text": False,
#         "text_distance": 1,
#         "quiet_zone": 1,
#     })
#     buf.seek(0)
#     return Image.open(buf).convert("RGB")

# def _generate_barcode_pil(code_text: str) -> Image.Image:
#     """Return a PIL Image for a Code128 barcode, no text, smaller size."""
#     barcode_obj = Code128(code_text, writer=ImageWriter())
#     buf = io.BytesIO()
#     barcode_obj.write(buf, options={
#         "module_width": 0.18,   # thinner bars
#         "module_height": 25.0,  # shorter barcode
#         "quiet_zone": 2,
#         "write_text": False     # remove digits below
#     })
#     buf.seek(0)
#     return Image.open(buf).convert("RGB")

def _generate_barcode_pil(code_text: str) -> Image.Image:
    barcode_obj = Code128(code_text, writer=ImageWriter())
    buf = io.BytesIO()
    barcode_obj.write(buf, options={
        "module_width": 0.4,   # increase thickness (default ~0.2)
        "module_height": 25.0,
        "quiet_zone": 2,
        "write_text": False
    })
    buf.seek(0)
    return Image.open(buf).convert("RGB")


# def compose_label(product: Dict[str, Any],
#                   store_name: str = STORE_NAME_DEFAULT,
#                   exp: str = "") -> Image.Image:
#     """
#     Compose a single label image (white background) that matches the requested fields.
#     Layout aims to resemble the sample: simple, compact, readable.
#     """
#     # Base
#     label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
#     draw = ImageDraw.Draw(label)

#     # Margins
#     pad = int(3 * PX_PER_MM)
#     x, y = pad, pad
#     inner_w = LABEL_W - 2 * pad
#     inner_h = LABEL_H - 2 * pad

#     # 1) Store name (top)
#     store_font = FONTS["bold"]
#     store_text = store_name.strip()[:40]  # keep it short
#     draw.text((x, y), store_text, font=store_font, fill="black")
#     y += int(store_font.getbbox(store_text)[3] - store_font.getbbox(store_text)[1]) + int(1.5 * PX_PER_MM)

#     # 2) Barcode (center block)
#     bc_img = _generate_barcode_pil(product["barcode"])
#     # scale barcode to fit width
#     max_bc_w = inner_w
#     ratio = min(max_bc_w / bc_img.width, 1.0)
#     bc_img = bc_img.resize((int(bc_img.width * ratio), int(bc_img.height * ratio)))
#     # paste centered
#     bc_x = x + (inner_w - bc_img.width) // 2
#     label.paste(bc_img, (bc_x, y))
#     y += bc_img.height + int(1 * PX_PER_MM)

#     # 3) Details lines
#     reg = FONTS["regular"]
#     tiny = FONTS["tiny"]
#     name_line = product["name"]
#     qty_line = f'{product["quantity"]:g} {product["measure"]}'
#     mrp_line = f'MRP: ₹{product["mrp"]:g}'
#     retail_line = f'RP: ₹{product["retail_price"]:g}'
#     exp_line = f'EXP: {exp or ""}'

#     def write_line(text, font=reg, underline=False):
#         nonlocal y
#         draw.text((x, y), text, font=font, fill="black")
#         y += int(font.getbbox(text)[3] - font.getbbox(text)[1]) + int(0.8 * PX_PER_MM)
#         if underline:
#             w = draw.textlength(text, font=font)
#             draw.line((x, y, x + w, y), fill="black", width=1)
#             y += int(0.6 * PX_PER_MM)

#     # Name (trim if overflows)
#     # If too long, clip with ellipsis
#     max_chars = 28
#     if len(name_line) > max_chars:
#         name_line = name_line[:max_chars - 1] + "…"
#     write_line(name_line, reg)

#     # Qty + MRP + RP in two lines for compactness
#     write_line(f"QTY: {qty_line}", tiny)
#     write_line(mrp_line + "   " + retail_line, tiny)

#     # EXP (empty placeholder for now)
#     write_line(exp_line, tiny)

#     return label


# def compose_label(product: Dict[str, Any],
#                   store_name: str = STORE_NAME_DEFAULT,
#                   exp: str = "") -> Image.Image:
#     """
#     Compose a label identical to reference design:
#     - Store name top
#     - Barcode only (no text)
#     - Clean aligned product details
#     """
#     label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
#     draw = ImageDraw.Draw(label)

#     pad = int(2 * PX_PER_MM)
#     x, y = pad, pad
#     inner_w = LABEL_W - 2 * pad

#     # 1) Store name
#     draw.text((x, y), store_name, font=FONTS["bold"], fill="black")
#     y += 28

#     # 2) Barcode (smaller, centered)
#     bc_img = _generate_barcode_pil(product["barcode"])
#     max_bc_w = int(inner_w * 0.65)   # only 65% of available width
#     ratio = min(max_bc_w / bc_img.width, 1.0)
#     bc_img = bc_img.resize((int(bc_img.width * ratio), 50))  # fixed 50px height
#     bc_x = x + (inner_w - bc_img.width) // 2
#     label.paste(bc_img, (bc_x, y))
#     y += bc_img.height + 8


#     # 3) Product details – aligned like sample
#     name_line = product["name"]
#     qty_line = f'{product["quantity"]:g} {product["measure"]}'
#     mrp_line = f'MRP: {product["mrp"]:g}'
#     retail_line = f'RP: {product["retail_price"]:g}'
#     exp_line = f'EXP: {exp or ""}'

#     draw.text((x, y), name_line, font=FONTS["regular"], fill="black"); y += 22
#     draw.text((x, y), f"QTY: {qty_line}", font=FONTS["tiny"], fill="black"); y += 20
#     draw.text((x, y), f"{mrp_line}   {retail_line}", font=FONTS["tiny"], fill="black"); y += 20
#     draw.text((x, y), exp_line, font=FONTS["tiny"], fill="black")

#     return label


def compose_label(product: Dict[str, Any],
                  store_name: str = STORE_NAME_DEFAULT,
                  exp: str = "") -> Image.Image:
    label = Image.new("RGB", (LABEL_W, LABEL_H), "white")
    draw = ImageDraw.Draw(label)

    pad = int(2 * PX_PER_MM)
    x, y = pad, pad
    inner_w = LABEL_W - 2 * pad

    # 1) Store name
    draw.text((x, y), store_name, font=FONTS["bold"], fill="black")
    y += 26

    # 2) Barcode
    bc_img = _generate_barcode_pil(product["barcode"])
    ratio = min(inner_w * 0.7 / bc_img.width, 1.0)
    bc_img = bc_img.resize((int(bc_img.width * ratio), 45))
    bc_x = x + (inner_w - bc_img.width) // 2
    label.paste(bc_img, (bc_x, y))
    y += bc_img.height + 6

    # 3) Product name
    draw.text((x, y), product["name"], font=FONTS["regular"], fill="black")
    y += 22

    # 4) Combined line: code + qty + batch (dummy example)
    qty_line = f'{product["quantity"]:g}{product["measure"]}'
    code_line = f'EM36   {qty_line}   S.24'
    draw.text((x, y), code_line, font=FONTS["tiny"], fill="black")
    y += 20

    # 5) MRP and RP each on own line
    draw.text((x, y), f'MRP: {product["mrp"]:g}', font=FONTS["tiny"], fill="black")
    y += 20
    draw.text((x, y), f'RP: {product["retail_price"]:g}', font=FONTS["tiny"], fill="black")
    y += 20

    # 6) PKD + EXP
    pkd = datetime.now().strftime("%d.%m.%y")
    draw.text((x, y), f'PKD: {pkd}   EXP: {exp or ""}', font=FONTS["tiny"], fill="black")

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
    # send minimal payload
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
    """
    Generates a label PNG for preview in the browser.
    Accepts either ?barcode=... or the product fields via query params.
    """
    barcode = request.args.get("barcode")
    store = request.args.get("store", STORE_NAME_DEFAULT)
    exp = request.args.get("exp", "")

    if barcode:
        product = get_product_by_barcode(barcode)
        if not product:
            return "Product not found", 404
    else:
        # fallback (allow ad-hoc preview via params)
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
    

@app.post("/api/print")
def api_print():
    """
    POST JSON:
    {
      "barcode": "...",           # product barcode
      "count": 3,                 # number of labels
      "store_name": "My Store",   # optional
      "exp": ""                   # optional
    }
    """
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

    # Compose once and save to temp PNG
    img = compose_label(product, store_name=store, exp=exp)
    tmp_path = os.path.abspath("label_tmp.png")
    img.save(tmp_path, format="PNG", dpi=(DPI, DPI))

    # Send to printer N times
    printed = 0
    errors = []
    for i in range(count):
        try:
            print_image_to_default_printer(tmp_path, title=f"Label {i+1}/{count}")
            printed += 1
        except Exception as e:
            errors.append(str(e))
            break

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
    # Helpful in dev: run with `python app.py`
    app.run(host="0.0.0.0", port=5001, debug=True)
