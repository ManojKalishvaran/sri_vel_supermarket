# barcode_print.py
import os
import sys

try:
    import win32print
    import win32ui
    from PIL import Image, ImageWin
    WINDOWS_PRINTING_AVAILABLE = True
except Exception:
    # Non-Windows or pywin32 not installed
    from PIL import Image
    WINDOWS_PRINTING_AVAILABLE = False


def print_image_to_default_printer(image_path: str, title: str = "Barcode Print"):
    """
    Prints an image to the default Windows printer using win32 and PIL ImageWin.
    Scales image to fit printable area while preserving aspect ratio.
    """
    if not WINDOWS_PRINTING_AVAILABLE:
        raise RuntimeError("Windows printing is not available on this system.")

    img = Image.open(image_path)

    printer_name = win32print.GetDefaultPrinter()
    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    # HORZRES, VERTRES
    printable_area = hDC.GetDeviceCaps(8), hDC.GetDeviceCaps(10)
    # LOGPIXELSX, LOGPIXELSY
    printer_dpi = hDC.GetDeviceCaps(88), hDC.GetDeviceCaps(90)

    img_w, img_h = img.size
    max_w, max_h = printable_area
    ratio = min(max_w / img_w, max_h / img_h, 1.0)
    target_w = int(img_w * ratio)
    target_h = int(img_h * ratio)

    if img.mode != "RGB":
        img = img.convert("RGB")

    img = img.resize((target_w, target_h))

    hDC.StartDoc(title)
    hDC.StartPage()

    dib = ImageWin.Dib(img)
    x = int((max_w - target_w) / 2)
    y = 0
    dib.draw(hDC.GetHandleOutput(), (x, y, x + target_w, y + target_h))

    hDC.EndPage()
    hDC.EndDoc()
    hDC.DeleteDC()
