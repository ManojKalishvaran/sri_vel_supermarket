"""Do a single-sheet test with a 1-row print. Measure the output against the pre-cut sheets physically — small offsets are common. Adjust LEFT_MARGIN_MM, TOP_MARGIN_MM, and HORIZONTAL_GAP_MM by ±1 mm until perfect. R220 has an adjustable sensor & auto-calibrate features—use them to detect gaps. 
retsol.net
+1

Barcode size: if a scanner fails, increase module_height and ensure quiet zone exists. Use Code128 for variable-length alphanumeric codes. If you must print EAN/UPC, swap to the corresponding barcode symbology.

DPI matters: we rendered at 203 DPI because the R220 commonly ships as 203 dpi (8 dots/mm). If you have a 300 dpi model, change DPI to 300. Verify on the spec sheet or driver. 
Amazon India

If you need ZPL/EPL direct commands (to push templates into printer firmware) that’s a different path — use the printer language the R220 supports and send raw bytes to the USB port. Most users get far better alignment by printing raster images via the Windows driver (what the script does)."""

"""
Print 3 labels-per-row to a Retsol R220 (Windows USB).
Requirements (install via pip):
    pip install pillow python-barcode pywin32

Notes:
 - This prints at 203 DPI (native printer resolution for R220).
 - Uses Code128 barcodes (scanner-friendly).
 - Make sure the Retsol R220 driver is installed and the printer name below is exact.
 - If you prefer EAN or other symbologies, swap barcode generation accordingly.
"""

from PIL import Image, ImageDraw, ImageFont, ImageOps
import barcode
from barcode.writer import ImageWriter
import win32print, win32ui
from PIL import ImageWin
import math
import os

# --------- USER CONFIG ----------
PRINTER_NAME = "Retsol R220"   # exact name as in Windows Printers. Adjust if different.
# Path to product image (change to your path). The conversation image path:
PRODUCT_IMAGE = r"C:\path\to\your\product.jpg"  # replace with actual path on Windows
# Label content (you can loop/replace per-label if needed)
PRODUCT_TITLE = "Perun Seeragam 100g"
PRICE_TEXT = "Price: ₹ 24.00"
BARCODE_VALUE = "890123456789"   # put actual barcode data here (or generate per-label)
# Label geometry (metrics provided by you)
LABEL_W_CM = 3.2    # cm
LABEL_H_CM = 2.0    # cm
LABELS_PER_ROW = 3
VERTICAL_GAP_MM = 3  # gap between rows in mm
# Sheet margins (mm) - tune for your pre-cut sheet alignment
LEFT_MARGIN_MM = 5
TOP_MARGIN_MM = 5
HORIZONTAL_GAP_MM = 2  # optional gap between columns (set small if pre-cut)
# Printer DPI for R220
DPI = 203
# Font files: Windows has Arial Bold - fallback to default if not found
FONT_BOLD_PATH = r"C:\Windows\Fonts\Arialbd.ttf"
FONT_REGULAR_PATH = r"C:\Windows\Fonts\Arial.ttf"
# --------------------------------

# helper conversions
def cm_to_px(cm, dpi=DPI): return int(round(cm / 2.54 * dpi))
def mm_to_px(mm, dpi=DPI): return int(round(mm / 25.4 * dpi))

label_w_px = cm_to_px(LABEL_W_CM)
label_h_px = cm_to_px(LABEL_H_CM)
vertical_gap_px = mm_to_px(VERTICAL_GAP_MM)
left_margin_px = mm_to_px(LEFT_MARGIN_MM)
top_margin_px = mm_to_px(TOP_MARGIN_MM)
horizontal_gap_px = mm_to_px(HORIZONTAL_GAP_MM)

# Build one row width and an estimated sheet width. For safety we create a sheet with N rows.
# We'll create a 1-row sheet containing 3 labels. If you want multi-row, loop or increase rows variable.
rows_on_sheet = 1
sheet_w_px = left_margin_px + LABELS_PER_ROW * label_w_px + (LABELS_PER_ROW - 1) * horizontal_gap_px + left_margin_px
sheet_h_px = top_margin_px + rows_on_sheet * label_h_px + (rows_on_sheet - 1) * vertical_gap_px + top_margin_px

# Load fonts
def load_font(path, size):
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

# Suggested font sizes (tuned for 203 DPI and this small label)
title_font = load_font(FONT_BOLD_PATH, int(round(8/72*DPI)))   # ~8pt scaled to DPI
price_font = load_font(FONT_BOLD_PATH, int(round(9/72*DPI)))   # slightly larger
barcode_text_font = load_font(FONT_REGULAR_PATH, int(round(6/72*DPI)))

# Create the sheet image (white background)
sheet = Image.new("RGB", (sheet_w_px, sheet_h_px), "white")
draw = ImageDraw.Draw(sheet)

# Prepare product image (if available)
def prepare_product_image(path, target_w, target_h):
    try:
        im = Image.open(path).convert("RGBA")
        # Fit image into a box preserving aspect ratio
        im.thumbnail((target_w, target_h), Image.LANCZOS)
        # Create white background and center
        bg = Image.new("RGBA", (target_w, target_h), (255,255,255,255))
        offset = ((target_w - im.width)//2, (target_h - im.height)//2)
        bg.paste(im, offset, im if im.mode=="RGBA" else None)
        return bg.convert("RGB")
    except Exception as e:
        print("Product image load failed:", e)
        return Image.new("RGB", (target_w, target_h), "white")

# Barcode generator using python-barcode + Pillow writer
def generate_code128_image(code, target_width_px, target_height_px, text_below=True):
    # python-barcode will create an image with the barcode and optional text
    CODE128 = barcode.get_barcode_class('code128')
    writer_opts = {
        'module_height': max(10, int(target_height_px * 0.6 / DPI * 203)),  # tune height
        'font_size': 10,
        'text_distance': 1,
        'quiet_zone': 1,
        'dpi': DPI
    }
    bc = CODE128(code, writer=ImageWriter())
    img = bc.render(writer_options=writer_opts)
    # Resize preserving aspect to fit target area (width priority)
    w_ratio = target_width_px / img.width
    new_h = int(img.height * w_ratio)
    img = img.resize((target_width_px, new_h), Image.LANCZOS)
    # If resulting height > target_height_px, scale down by height
    if img.height > target_height_px:
        h_ratio = target_height_px / img.height
        new_w = int(img.width * h_ratio)
        img = img.resize((new_w, target_height_px), Image.LANCZOS)
    return img

# Compose a single label at x,y (top-left)
def draw_label(x, y, title, price, barcode_value, product_image_path=None):
    # draw border (for debug/alignment) - you can comment out in production
    # draw.rectangle([x, y, x+label_w_px-1, y+label_h_px-1], outline="black")

    # area layout inside label:
    padding = int(round(1/25.4 * DPI))  # ~1 mm padding
    inner_w = label_w_px - 2*padding
    inner_h = label_h_px - 2*padding

    # allocate vertical areas:
    # top: tiny product image (approx 40% height)
    img_area_h = int(inner_h * 0.40)
    # middle: title + price
    mid_area_h = int(inner_h * 0.30)
    # bottom: barcode
    bc_area_h = inner_h - img_area_h - mid_area_h

    # Product image area
    prod_img = prepare_product_image(product_image_path, inner_w, img_area_h)
    sheet.paste(prod_img, (x+padding, y+padding))

    # Title & price area
    title_y = y + padding + img_area_h
    # bold title centered
    draw_text_centered(draw, x+padding, title_y, inner_w, int(mid_area_h*0.55), title, title_font)
    # price below title
    price_y = title_y + int(mid_area_h*0.55)
    draw_text_centered(draw, x+padding, price_y, inner_w, int(mid_area_h*0.45), price, price_font)

    # Barcode area - generate and center
    bc_img = generate_code128_image(barcode_value, inner_w, bc_area_h)
    bc_x = x + padding + (inner_w - bc_img.width)//2
    bc_y = y + padding + img_area_h + mid_area_h + ((bc_area_h - bc_img.height)//2)
    sheet.paste(bc_img, (bc_x, bc_y))

def draw_text_centered(draw_obj, x, y, box_w, box_h, text, font):
    bbox = draw_obj.textbbox((0,0), text, font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    tx = x + (box_w - w)//2
    ty = y + (box_h - h)//2
    draw_obj.text((tx, ty), text, font=font, fill="black")


# Compose three labels in the top row
for col in range(LABELS_PER_ROW):
    x = left_margin_px + col * (label_w_px + horizontal_gap_px)
    y = top_margin_px
    # If you have per-label data, read from a list; here we reuse same content
    draw_label(x, y, PRODUCT_TITLE, PRICE_TEXT, BARCODE_VALUE, PRODUCT_IMAGE if os.path.exists(PRODUCT_IMAGE) else None)

# Save the produced sheet for inspection (useful)
output_path = os.path.join(os.getcwd(), "label_sheet.png")
sheet.save(output_path, dpi=(DPI, DPI))
print("Label sheet saved to:", output_path)

# ---------- Send to Windows printer (GDI) ----------
def print_image_to_windows_printer(image_path, printer_name=PRINTER_NAME):
    # open printer
    hPrinter = win32print.OpenPrinter(printer_name)
    try:
        # use win32ui CreateDC from printer
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)
        printable_area = hDC.GetDeviceCaps(8), hDC.GetDeviceCaps(10)  # HORZRES, VERTRES
        printer_size = hDC.GetDeviceCaps(110), hDC.GetDeviceCaps(111) # PHYSICALWIDTH, PHYSICALHEIGHT
        print_size = printable_area
        bmp = Image.open(image_path)

        # scale image to fit printable area if bigger
        ratio = min(printable_area[0]/bmp.width, printable_area[1]/bmp.height)
        if ratio < 1.0:
            new_size = (int(bmp.width*ratio), int(bmp.height*ratio))
            bmp = bmp.resize(new_size, Image.LANCZOS)

        # start doc
        hDC.StartDoc("LabelPrint")
        hDC.StartPage()

        dib = ImageWin.Dib(bmp)
        # position at top-left (can adjust to adjust sheet margins)
        x1 = 0
        y1 = 0
        x2 = int(bmp.size[0])
        y2 = int(bmp.size[1])
        dib.draw(hDC.GetHandleOutput(), (x1, y1, x2, y2))

        hDC.EndPage()
        hDC.EndDoc()
        hDC.DeleteDC()
    finally:
        win32print.ClosePrinter(hPrinter)

# uncomment to actually send to printer
# print_image_to_windows_printer(output_path)
print("Ready to print. Uncomment print_image_to_windows_printer(...) to send to printer.")
