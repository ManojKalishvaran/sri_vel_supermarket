"""
print_receipt_rtp82ue.py

Production-friendly script to print a receipt to a USB ESC/POS printer (RTP-82UE).
Features:
 - Auto-detect USB ESC/POS printers via pyusb
 - Text-mode printing with bold / double-size, column alignment
 - Raster/image-mode printing from a PNG (exact visual fidelity)
 - Helpful error messages & fallback
"""

import sys
import io
from time import sleep
from typing import Optional, Tuple, List

from PIL import Image, ImageOps
import usb.core
import usb.util

from escpos.printer import Usb
from escpos import EscposException

# ---------- Configuration ----------
# Optional: override with exact VID/PID if auto-detect fails (hex integers)
MANUAL_VID = None  # e.g. 0x0fe6
MANUAL_PID = None  # e.g. 0x811e

# Path to the receipt PNG you provided in the container
RECEIPT_IMAGE_PATH = "/mnt/data/27154992-58c3-4c81-b01e-16b2ee4356be.png"

# Number of characters per line to assume for formatted text mode.
# 3-inch (80mm) printers are commonly 42-48 chars depending on font. Tune if needed.
LINE_CHARS = 42 # tuned for 72mm roll; adjust +/- a few chars if lines wrap
# -----------------------------------

def find_candidate_usb_printers() -> List[Tuple[int, int, str]]:
    """Return list of (vid, pid, manufacturer/product) for USB devices that look like printers."""
    devices = []
    for d in usb.core.find(find_all=True):
        vid = d.idVendor
        pid = d.idProduct
        # Try to read manufacturer/product strings (safe-guard)
        try:
            manu = usb.util.get_string(d, d.iManufacturer) or ""
            prod = usb.util.get_string(d, d.iProduct) or ""
            name = f"{manu} {prod}".strip()
        except Exception:
            name = ""
        # Commonly ESC/POS printers don't always expose class; include everything and we'll try open.
        devices.append((vid, pid, name))
    return devices

def auto_detect_printer(manual_vid: Optional[int] = None, manual_pid: Optional[int] = None) -> Usb:
    """
    Try to auto-detect a usable ESC/POS USB printer and return escpos.printer.Usb instance.
    If manual_vid/pid supplied, try only that.
    """
    tried = []
    def try_create(vid, pid):
        try:
            # usb_interface argument might need tweaking (0 or 1). 0 is common.
            p = Usb(vid, pid, 0, timeout=2000)
            # quick smoke test - do not cut paper unexpectedly if not desired:
            p._raw(b'')  # ensure driver openable
            return p
        except EscposException as e:
            raise
        except Exception as e:
            return None

    if manual_vid and manual_pid:
        p = try_create(manual_vid, manual_pid)
        if p:
            return p
        raise RuntimeError(f"Failed to open manual VID/PID {manual_vid:#04x}/{manual_pid:#04x}")

    candidates = find_candidate_usb_printers()
    if not candidates:
        raise RuntimeError("No USB devices found. Make sure the printer is connected.")

    # try each candidate until one constructs an escpos.Usb successfully
    last_err = None
    for vid, pid, name in candidates:
        tried.append((vid, pid, name))
        try:
            p = try_create(vid, pid)
            if p:
                print(f"Auto-detected printer: VID={vid:#04x} PID={pid:#04x} name='{name}'")
                return p
        except Exception as e:
            last_err = e
            # continue to next device
            continue

    raise RuntimeError(f"Could not open an ESC/POS printer from USB devices: {tried}. "
                       "Try supplying MANUAL_VID/MANUAL_PID or run as root / set udev rules. "
                       f"Last error: {last_err}")

# ------------------ Text formatting helpers ------------------

def format_line_columns(cols: List[Tuple[str,int]], widths: List[int]) -> str:
    """
    Build a single line with left/center/right alignment based on widths.
    cols: list of (text, alignment) where alignment: 0=left,1=center,2=right
    widths: list of ints specifying each column width
    Returns a concatenated string sized to sum(widths).
    """
    pieces = []
    for (text, align), w in zip(cols, widths):
        if len(text) > w:
            text = text[:w]
        if align == 0:
            pieces.append(text.ljust(w))
        elif align == 1:
            pieces.append(text.center(w))
        else:
            pieces.append(text.rjust(w))
    return "".join(pieces)

def format_item_line(sno:int, name:str, qty:int, rate:float, total:float) -> str:
    """Return a single item line tuned for LINE_CHARS width. Adjust column widths if needed."""
    # Define column widths roughly: sno(3) name(var) qty(5) rate(10) total(10)
    # Ensure sum equals LINE_CHARS or less
    w_sno = 3
    w_total = 10
    w_rate = 10
    w_qty = 5
    w_name = max(5, LINE_CHARS - (w_sno + w_qty + w_rate + w_total))
    return format_line_columns(
        [
            (str(sno), 2),
            (name, 0),
            (str(qty), 2),
            (f"{rate:.2f}", 2),
            (f"{total:.2f}", 2),
        ],
        [w_sno, w_name, w_qty, w_rate, w_total]
    )

# ------------------ Printing functions ------------------

def print_text_receipt(p: Usb):
    """Print the receipt using ESC/POS text commands and style toggles."""
    # Header - bigger + bold
    p.set(align="center", bold=True, double_height=True, double_width=True)
    p.text("SHOP NAME / SUPERMARKET\n")
    p.set(align="center", bold=True, double_height=False, double_width=False)
    p.text("STORE ADDRESS LINE 1\n")
    p.text("STORE ADDRESS LINE 2\n\n")

    p.set(align="left", bold=False, double_width=False, double_height=False)
    p.text(f"Bill No: 1110    Date: 25-09-2025\n")
    p.text("Customer: Walk-in\n")
    p.text("-" * LINE_CHARS + "\n")

    # Items header
    p.set(bold=True)
    # We'll construct a header line compatible with format_item_line widths
    # Reuse format_item_line to match row layout
    # A simple header:
    p.text(format_item_line(0, "ITEM", "QTY", 0.0, 0.0).replace("0.0","RATE").replace("0.0","TOTAL") + "\n")
    p.set(bold=False)

    # Example items (use real data to iterate)
    items = [
        (1, "Sesame oil", 2, 380.0, 760.0),
        (2, "Kandala 250g", 2, 35.0, 70.0),
        (3, "Vellakkaai 1kg", 1, 150.0, 150.0),
        (4, "Kadal Paruppu 500g", 2, 45.0, 90.0),
        (5, "Milagai 100g", 24, 20.0, 480.0),
        # add remaining items...
    ]

    for sno, name, qty, rate, total in items:
        line = format_item_line(sno, name, qty, rate, total)
        p.text(line + "\n")

    p.text("-" * LINE_CHARS + "\n")

    # Totals in bold and double width for emphasis
    p.set(bold=True, double_width=True)
    # Right-align the totals
    subtotal_label = "SUBTOTAL:"
    subtotal_val = "3,875.00"
    line = subtotal_label.rjust(LINE_CHARS - len(subtotal_val)) + subtotal_val
    p.text(line + "\n")

    p.set(bold=True, double_height=True)
    discount_label = "DISCOUNT:"
    discount_val = "338.00"
    line = discount_label.rjust(LINE_CHARS - len(discount_val)) + discount_val
    p.text(line + "\n")

    p.set(bold=False, double_height=False, double_width=False)
    p.text("\nT.QTY: 29\n")
    p.text("\nNEFT/GST Included: ₹3,875.00\n")
    p.text("\nTHANK YOU, VISIT AGAIN!\n")
    p.text("\n\n")
    try:
        p.cut()
    except Exception:
        # some printers don't have cutter - ignore
        pass

def print_image_receipt(p: Usb, image_path: str, max_width_px: Optional[int] = None):
    """
    Print the receipt image as a raster.
    - Converts to monochrome, optionally scales to max_width_px if provided.
    - Centered on paper.
    """
    im = Image.open(image_path).convert("L")  # grayscale
    # convert to 1-bit monochrome (dither may help)
    im = ImageOps.autocontrast(im)
    bw = im.convert("1")  # 1 bit
    # ESC/POS printers expect certain dpi; let escpos library handle internal conversion
    # Optionally resize if printer is limited width (escape commands expect device width)
    if max_width_px:
        w, h = bw.size
        if w > max_width_px:
            new_h = int(max_width_px * h / w)
            bw = bw.resize((max_width_px, new_h), Image.LANCZOS)

    # center the image by adding margins to fit LINE_CHARS (optional)
    p.set(align="center")
    p.image(bw)  # python-escpos does internal raster conversion
    p.text("\n")
    try:
        p.cut()
    except Exception:
        pass

# ------------------ Main ------------------

def main():
    # If you know vid/pid, set MANUAL_VID and MANUAL_PID (hex ints) above OR set env/args.
    manual_vid = MANUAL_VID
    manual_pid = MANUAL_PID
    if manual_vid is None or manual_pid is None:
        # try reading env-style strings if provided
        pass

    try:
        printer = auto_detect_printer(manual_vid, manual_pid)
    except Exception as e:
        print("Failed to find/open USB printer:", e, file=sys.stderr)
        print("Recommendations:")
        print(" - Run lsusb (Linux) or check Device Manager (Windows) to see VID/PID.")
        print(" - On Linux, either run as root (sudo) or add a udev rule for printer device permissions.")
        print(" - If auto-detect fails, set MANUAL_VID and MANUAL_PID in the script.")
        sys.exit(1)

    # Choose mode: text or image. Use text first; image mode is a fallback for exact layout
    try:
        print("Printing text-mode receipt...")
        print_text_receipt(printer)
        sleep(1)
    except Exception as e:
        print("Text-mode failed:", e, file=sys.stderr)
        print("Attempting raster/image printing as fallback...")

        try:
            print_image_receipt(printer, RECEIPT_IMAGE_PATH, max_width_px=576)  # 576 px is common for 80mm @ 203dpi
        except Exception as e2:
            print("Image printing also failed:", e2, file=sys.stderr)
            sys.exit(2)

    print("Done.")

if __name__ == "__main__":
    main()
