"""pip install python-escpos
"""
"""On Windows
1.Plug your printer into the USB port and turn it on.

2.Open Device Manager (Press Windows key, type "Device Manager", and hit Enter).

3.Find your printer under "Universal Serial Bus controllers", "Other devices", or possibly "Printers".

4.Right-click on the device and select Properties.

5.Go to the Details tab.

6. In the Property dropdown, select Hardware Ids.

6. Look for a string like USB\VID_XXXX&PID_YYYY. The four characters after VID_ are your Vendor ID, and the four after PID_ are your Product ID.

"""

from escpos.printer import Usb

# Replace these values with your printer's vendor/product ID (use 'lsusb' on Linux or Device Manager on Windows)
VENDOR_ID = "0xXXXX"   # e.g., 0x04b8 for Epson, check RTP-82UE specifics
PRODUCT_ID = "0xXXXX"  # e.g., 0x0xxx for your device

# Initialize printer (USB)
p = Usb(VENDOR_ID, PRODUCT_ID)

# Header in bold and double size
p.set(align='center', font='a', width=2, height=2, bold=True)
p.text("VRINDHA MART\n")
p.text("Mobile: XXXXXXXXXX\n")
p.text("Bill No: 001\n")
p.text("Date: 25-09-2025 11:30\n")
p.text("--------------------------------\n")

# Table header
p.set(align='left', font='a', width=1, height=1, bold=True)
header = f"{'SN.':<3}{'ITEMS':<20}{'QTY':>4}{'MRP':>5}{'RATE':>6}{'TOTAL':>8}\n"
p.text(header)
p.text("--------------------------------\n")

# Example item rows (populate dynamically as needed)
items = [
    ("1", "Sesame Oil",   "1", "130", "130.00", "130.00"),
    ("2", "Kaikugu 250g", "2", "80",  "78.00",  "156.00"),
    ("3", "Vendhayam 1kg","1", "150", "150.00", "150.00"),
    # ... add remaining items here following the same tuple format
]

for sn, name, qty, mrp, rate, total in items:
    line = f"{sn:<3}{name:<20}{qty:>4}{mrp:>5}{rate:>6}{total:>8}\n"
    p.set(bold=False)
    p.text(line)

p.text("--------------------------------\n")

# Totals in bold and double size
p.set(bold=True, width=2, height=2, align='right')
p.text("SUB TOTAL:  3875.00\n")
p.text("DIS AMT  :   386.00\n")
p.text("NET GST INCLUDED:  3875.00\n")
p.text("THANK YOU VISIT AGAIN!\n")
p.cut()
