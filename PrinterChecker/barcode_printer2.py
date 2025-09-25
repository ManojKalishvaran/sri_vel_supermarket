import barcode
from barcode.writer import ImageWriter
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from PIL import Image

# Label sheet config
LABEL_WIDTH = 32  # mm
LABEL_HEIGHT = 20 # mm
LABELS_PER_ROW = 3
LABEL_ROW_GAP = 3 # mm

# Content for 3 labels (update as needed)
labels = [
    {"shop": "Shri Velavan Super Market", "name": "Perun Seeragam 100g", "price": "₹ 24.00", "barcode_data": "123456789012"},
    {"shop": "Shri Velavan Super Market", "name": "Perun Seeragam 100g", "price": "₹ 24.00", "barcode_data": "123456789013"},
    {"shop": "Shri Velavan Super Market", "name": "Perun Seeragam 100g", "price": "₹ 24.00", "barcode_data": "123456789014"},
]

def generate_barcode_img(data, filename):
    CODE128 = barcode.get_barcode_class('code128')
    code = CODE128(data, writer=ImageWriter())
    code.save(filename, options={'write_text': False, 'module_height': 10, 'module_width': 0.3})

for idx, label in enumerate(labels):
    img_file = f'barcode_{idx}.png'
    generate_barcode_img(label['barcode_data'], img_file)
    labels[idx]['barcode_img'] = img_file

# Create PDF for R220 printing
c = canvas.Canvas("label_sheet.pdf", pagesize=(LABELS_PER_ROW*LABEL_WIDTH*mm, LABEL_HEIGHT*mm))
for i, label in enumerate(labels):
    x_offset = i * LABEL_WIDTH * mm
    # Shop Name - bold, large
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x_offset+2, LABEL_HEIGHT*mm-6, label['shop'])
    # Barcode
    barcode_img = Image.open(label['barcode_img'])
    c.drawInlineImage(barcode_img, x_offset+2, LABEL_HEIGHT*mm-14, LABEL_WIDTH*mm-4, 10*mm)
    # Product Name - bold
    c.setFont("Helvetica-Bold", 8)
    c.drawString(x_offset+2, LABEL_HEIGHT*mm-17, label['name'])
    # Price - big, bold
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x_offset+2, LABEL_HEIGHT*mm-20, f"Price: {label['price']}")

c.showPage()
c.save()
