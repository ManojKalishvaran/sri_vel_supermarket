# barcode_print.py
import os
import sys

try:
    import win32print
    import win32ui
    from PIL import Image, ImageWin
    WINDOWS_PRINTING_AVAILABLE = True
except Exception:
    from PIL import Image
    WINDOWS_PRINTING_AVAILABLE = False


def print_image(image_path: str, title: str = "Label Print", printer_name: str = None):
    """
    Prints an image to the specified Windows printer using win32 and PIL ImageWin.
    If no printer_name is given, it falls back to the system default printer.
    """
    if not WINDOWS_PRINTING_AVAILABLE:
        raise RuntimeError("Windows printing is not available on this system.")

    # Use default printer if none provided
    if not printer_name:
        printer_name = win32print.GetDefaultPrinter()

    img = Image.open(image_path)

    # Create a printer device context
    hDC = win32ui.CreateDC()
    hDC.CreatePrinterDC(printer_name)

    # HORZRES, VERTRES = printable area in pixels
    printable_area = hDC.GetDeviceCaps(8), hDC.GetDeviceCaps(10)

    img_w, img_h = img.size
    max_w, max_h = printable_area

    # Scale image proportionally to fit within printable area
    ratio = min(max_w / img_w, max_h / img_h, 1.0)
    target_w = int(img_w * ratio)
    target_h = int(img_h * ratio)

    if img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize((target_w, target_h))

    # Start printing
    hDC.StartDoc(title)
    hDC.StartPage()

    dib = ImageWin.Dib(img)
    x = int((max_w - target_w) / 2)   # center horizontally
    y = 0
    dib.draw(hDC.GetHandleOutput(), (x, y, x + target_w, y + target_h))

    hDC.EndPage()
    hDC.EndDoc()
    hDC.DeleteDC()
