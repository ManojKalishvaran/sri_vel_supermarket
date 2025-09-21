# (Full file — replace your existing app.py with this)
from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from datetime import datetime
import textwrap
import win32print
import win32ui
import win32con
import pywintypes

app = Flask(__name__)

# explicit bill printer (use the exact name shown in Windows Printers)
BILL_PRINTER_NAME = os.environ.get('BILL_PRINTER', 'RETSOL RTP 82UE')


# Create Data directory if not exists
if not os.path.exists('Data'):
    os.makedirs('Data')

# Database file paths
CUSTOMERS_DB = 'Data/customers.db'
BILLS_DB = 'Data/bills.db'
PRODUCTS_DB = 'Data/products.db'

def init_databases():
    conn = sqlite3.connect(CUSTOMERS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            mobile TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            address TEXT,
            points REAL DEFAULT 0,
            balance REAL DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

    conn = sqlite3.connect(BILLS_DB)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bills (
            bill_number TEXT PRIMARY KEY,
            customer_mobile TEXT,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            total_items INTEGER NOT NULL,
            total_unique_products INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            total_savings REAL NOT NULL,
            payment_type TEXT NOT NULL,
            cash_received REAL DEFAULT 0,
            cash_balance REAL DEFAULT 0,
            old_balance REAL DEFAULT 0,
            new_balance REAL DEFAULT 0,
            points_earned INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS bill_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_number TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit TEXT NOT NULL,
            mrp REAL NOT NULL,
            retail_price REAL NOT NULL,
            total_price REAL NOT NULL,
            FOREIGN KEY (bill_number) REFERENCES bills (bill_number)
        )
    ''')
    conn.commit()
    conn.close()

def get_customer(mobile):
    try:
        conn = sqlite3.connect(CUSTOMERS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT mobile, name, address, points, balance FROM customers WHERE mobile = ?', (mobile,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'mobile': row[0], 'name': row[1], 'address': row[2] or '', 'points': float(row[3] or 0), 'balance': float(row[4] or 0)}
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    return None

def create_customer(mobile, name, address=''):
    try:
        conn = sqlite3.connect(CUSTOMERS_DB)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO customers (mobile, name, address, points, balance) VALUES (?, ?, ?, 0, 0)', (mobile, name, address))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def update_customer(customer_data):
    try:
        conn = sqlite3.connect(CUSTOMERS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT mobile FROM customers WHERE mobile = ?', (customer_data['mobile'],))
        exists = cursor.fetchone()
        if exists:
            cursor.execute('''
                UPDATE customers SET name = ?, address = ?, points = ?, balance = ? WHERE mobile = ?
            ''', (customer_data['name'], customer_data['address'], customer_data['points'], customer_data['balance'], customer_data['mobile']))
        else:
            cursor.execute('INSERT INTO customers (mobile, name, address, points, balance) VALUES (?, ?, ?, ?, ?)',
                           (customer_data['mobile'], customer_data['name'], customer_data['address'], customer_data['points'], customer_data['balance']))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def get_product_by_barcode(barcode):
    try:
        conn = sqlite3.connect(PRODUCTS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT name, tamil_name, measure, mrp, retail_price FROM products WHERE barcode = ?', (barcode,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'name': row[0] or '', 'tamil_name': row[1] or '', 'measure': row[2], 'mrp': float(row[3]), 'retail_price': float(row[4])}
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    return None

def get_product_by_name(name):
    try:
        conn = sqlite3.connect(PRODUCTS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT name, tamil_name, measure, mrp, retail_price FROM products WHERE name LIKE ? OR tamil_name LIKE ?', (f'%{name}%', f'%{name}%'))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {'name': row[0] or '', 'tamil_name': row[1] or '', 'measure': row[2], 'mrp': float(row[3]), 'retail_price': float(row[4])}
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    return None

def get_product_list():
    try:
        conn = sqlite3.connect(PRODUCTS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT name, tamil_name FROM products')
        rows = cursor.fetchall()
        conn.close()
        products = []
        for row in rows:
            products.append({'name': row[0] or '', 'tamil_name': row[1] or ''})
        return products
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

def save_bill(bill_data, items_data):
    try:
        conn = sqlite3.connect(BILLS_DB)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO bills (
                bill_number, customer_mobile, date, time, total_items, total_unique_products,
                subtotal, total_savings, payment_type, cash_received, cash_balance, old_balance, new_balance, points_earned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            bill_data['bill_number'], bill_data['customer_mobile'], bill_data['date'], bill_data['time'],
            bill_data['total_items'], bill_data['total_unique_products'], bill_data['subtotal'], bill_data['total_savings'],
            bill_data['payment_type'], bill_data['cash_received'], bill_data['cash_balance'], bill_data['old_balance'],
            bill_data['new_balance'], bill_data['points_earned']
        ))
        for item in items_data:
            cursor.execute('''
                INSERT INTO bill_items (bill_number, product_name, quantity, unit, mrp, retail_price, total_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (item['bill_number'], item['product_name'], item['quantity'], item['unit'], item['mrp'], item['retail_price'], item['total_price']))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

# Helpers for two-line ellipsize (character-based preview)
def ellipsize_line_by_chars(s, max_chars):
    if len(s) <= max_chars:
        return s
    if max_chars <= 3:
        return s[:max_chars]
    return s[:max_chars-3] + '...'

def wrap_text_to_max_lines(s, char_width, max_lines=2):
    wrapped = textwrap.wrap(s, width=char_width) or ['']
    if len(wrapped) <= max_lines:
        return wrapped
    result = wrapped[:max_lines]
    result[-1] = ellipsize_line_by_chars(result[-1], char_width)
    return result

# def format_thermal_bill(items, width=38):
#     # Adjusted widths for better alignment on 7.5cm thermal paper
#     name_w = 16
#     qty_w = 4
#     mrp_w = 7
#     rate_w = 7
#     tot_w = 6
    
#     # Create properly spaced header
#     header = f"{'பொருள்':<{name_w}}{'அளவு':>{qty_w}}{'MRP':>{mrp_w}}{'விலை':>{rate_w}}{'தொகை':>{tot_w}}"
#     line_sep = '=' * width
#     lines = [line_sep, header, line_sep]
    
#     for item in items:
#         qty = str(int(item.get('quantity', 0))) if float(item.get('quantity', 0)).is_integer() else str(item.get('quantity'))
#         mrp_val = f"{float(item.get('mrp',0)):.2f}"
#         rate_val = f"{float(item.get('retail_price',0)):.2f}"
#         total_val = f"{float(item.get('total_price',0)):.2f}"
        
#         name_lines = wrap_text_to_max_lines(str(item.get('product_name','')), name_w, max_lines=2)
        
#         # First line with all details
#         left_part = name_lines[0].ljust(name_w)
#         qty_part = qty.rjust(qty_w)
#         mrp_part = mrp_val.rjust(mrp_w)
#         rate_part = rate_val.rjust(rate_w)
#         total_part = total_val.rjust(tot_w)
        
#         first_line = left_part + qty_part + mrp_part + rate_part + total_part
#         lines.append(first_line)
        
#         # Additional name lines if product name is long
#         for cont in name_lines[1:]:
#             lines.append(cont.ljust(name_w))
            
#         lines.append('-' * width)
    
#     return '\n'.join(lines)

def format_thermal_bill(items, width=42, hDC=None):
    """
    Layout: product name at left (ljust), numeric columns right-aligned.
    This is the safe character-based fallback used for preview strings.
    If hDC is provided, the other pixel-accurate branch is used elsewhere.
    """
    # column widths in characters (tuned for narrow receipt)
    name_w = 24   # product name column (left)
    qty_w = 6     # quantity (right)
    mrp_w = 8     # mrp (right)
    rate_w = 8    # retail price (right)
    tot_w = 8     # total (right)

    header = (
        f"{'பொருள்'.ljust(name_w)}"
        f"{'அளவு'.rjust(qty_w)}"
        f"{'MRP'.rjust(mrp_w)}"
        f"{'விலை'.rjust(rate_w)}"
        f"{'தொகை'.rjust(tot_w)}"
    )

    lines = ['-' * width, header, '-' * width]

    for item in items:
        # numeric strings
        qty = str(int(item.get('quantity', 0))) if float(item.get('quantity', 0)).is_integer() else str(item.get('quantity', 0))
        mrp_val = f"{float(item.get('mrp', 0)):.2f}"
        rate_val = f"{float(item.get('retail_price', 0)):.2f}"
        total_val = f"{float(item.get('total_price', 0)):.2f}"

        # Wrap product name (2 lines max)
        name_lines = wrap_text_to_max_lines(str(item.get('product_name', '')), name_w, max_lines=2)

        # First line: product name left, numbers right
        first_line = (
            f"{name_lines[0].ljust(name_w)}"
            f"{qty.rjust(qty_w)}"
            f"{mrp_val.rjust(mrp_w)}"
            f"{rate_val.rjust(rate_w)}"
            f"{total_val.rjust(tot_w)}"
        )
        lines.append(first_line)

        # Continuation lines: only product name left (numbers already printed)
        for cont in name_lines[1:]:
            lines.append(cont.ljust(name_w))

        lines.append('-' * width)

    return '\n'.join(lines)


def split_text_to_pixel_width(text, max_px, hDC, max_lines=2, ellipsis='...'):
    lines = []
    cur = ''
    for ch in text:
        w = hDC.GetTextExtent(cur + ch)[0]
        if w <= max_px:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    consumed = ''.join(lines)
    if len(consumed) < len(text):
        last = lines[-1] if lines else ''
        ell_w = hDC.GetTextExtent(ellipsis)[0]
        while last and (hDC.GetTextExtent(last + ellipsis)[0] > max_px):
            last = last[:-1]
        lines[-1] = (last + ellipsis) if last else ellipsis
    return lines

def generate_bill_string(bill_data, customer_data, items_data):
    WIDTH = 70
    SEP = '_' * WIDTH
    SEP2 = '-' * WIDTH
    header_lines = [
        SEP,
        "SRI VELAVAN SUPERMARKET".center(60),
        "2/136A, Pillaiyar Koil Street".center(WIDTH),
        "A.Kottarakuppam, Virudhachalam".center(WIDTH),
        "Ph: 9626475471  GST:33FLEPM3791Q1ZD".center(WIDTH),
        SEP2
    ]

    bill_string = '\n'.join(header_lines) + '\n'
    bill_string += f"பில் எண் : {bill_data['bill_number']}\nதேதி     : {bill_data['date']} {bill_data['time']}\n{SEP2}\n"
    bill_string += "வாடிக்கையாளர்:\n"
    bill_string += f"பெயர்    : {customer_data['name']}\n"
    if customer_data.get('mobile') and customer_data.get('mobile') != 'N/A':
        bill_string += f"மொபைல்  : {customer_data['mobile']}\n"
        bill_string += f"புள்ளிகள்: {customer_data.get('points', 0)}\n"
    bill_string += SEP2 + '\n'
    bill_string += format_thermal_bill(items_data, WIDTH) + '\n'
    bill_string += SEP2 + '\n'
    bill_string += f"மொத்த பொருட்கள் : {bill_data['total_unique_products']}\n"
    bill_string += f"மொத்த அளவு     : {bill_data['total_items']}\n"
    bill_string += f"மொத்தம்        : ₹{bill_data['subtotal']:.2f}\n"
    bill_string += f"சேமிப்பு       : ₹{bill_data['total_savings']:.2f}\n"
    if bill_data.get('customer_mobile') and bill_data.get('customer_mobile') != 'N/A':
        bill_string += SEP2 + '\n'
        bill_string += f"பழைய நிலுவை    : ₹{bill_data['old_balance']:.2f}\n"
        bill_string += f"புதிய நிலுவை   : ₹{bill_data['new_balance']:.2f}\n"
    bill_string += SEP2 + '\n'
    bill_string += f"செலுத்தும் முறை: {bill_data['payment_type']}\n"
    bill_string += f"பெற்றது       : ₹{bill_data['cash_received']:.2f}\n"
    bill_string += f"திருப்பியது    : ₹{bill_data['cash_balance']:.2f}\n"
    bill_string += SEP2 + '\n'
    bill_string += f"சம்பாதித்த புள்ளிகள்: {bill_data['points_earned']}\n"
    bill_string += SEP2 + '\n'
    bill_string += "     நன்றி! மீண்டும் வாருங்கள்!\n"
    bill_string += '\n'
    return '\n'.join([line.rstrip() for line in bill_string.strip().splitlines()])

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_customer/<mobile>')
def get_customer_route(mobile):
    customer = get_customer(mobile)
    if customer:
        return jsonify(customer)
    return jsonify({'error': 'Customer not found'}), 404

@app.route('/create_customer', methods=['POST'])
def create_customer_route():
    try:
        data = request.json
        mobile = data.get('mobile')
        name = data.get('name')
        address = data.get('address', '')
        if not mobile or not name:
            return jsonify({'error': 'Mobile and name are required'}), 400
        customer_data = {'mobile': mobile, 'name': name, 'address': address, 'points': 0, 'balance': 0}
        if update_customer(customer_data):
            return jsonify({'success': True, 'customer': customer_data, 'message': 'New customer created successfully'})
        else:
            return jsonify({'error': 'Failed to create customer'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_product_by_barcode/<barcode>')
def get_product_by_barcode_route(barcode):
    product = get_product_by_barcode(barcode)
    if product:
        return jsonify({'success': True, 'product': product})
    return jsonify({'success': False, 'error': 'Product not found'})

@app.route('/get_product_by_name/<name>')
def get_product_by_name_route(name):
    product = get_product_by_name(name)
    if product:
        return jsonify({'success': True, 'product': product})
    return jsonify({'success': False, 'error': 'Product not found'})

@app.route('/update_balance', methods=['POST'])
def update_balance():
    try:
        data = request.json
        mobile = data.get('mobile')
        new_balance = float(data.get('balance', 0))
        customer = get_customer(mobile)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        customer['balance'] = new_balance
        if update_customer(customer):
            return jsonify({'success': True, 'message': 'Balance updated successfully', 'customer': customer})
        else:
            return jsonify({'error': 'Failed to update balance'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_products')
def get_products():
    products = get_product_list()
    return jsonify({'products': products})

@app.route('/today_totals')
def today_totals():
    try:
        conn = sqlite3.connect(BILLS_DB)
        cursor = conn.cursor()
        today = datetime.now().strftime('%d/%m/%Y')
        cursor.execute('SELECT IFNULL(SUM(total_items),0), IFNULL(SUM(subtotal),0) FROM bills WHERE date = ?', (today,))
        row = cursor.fetchone()
        conn.close()
        total_items = int(row[0] or 0)
        total_sales = float(row[1] or 0.0)
        return jsonify({'date': today, 'total_items': total_items, 'total_sales': total_sales})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/create_bill', methods=['POST'])
@app.route('/create_bill', methods=['POST'])
def create_bill():
    try:
        data = request.json
        bill_number = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"
        now = datetime.now()
        current_date = now.strftime('%d/%m/%Y')
        current_time = now.strftime('%H:%M:%S')

        # totals
        total_items = sum(int(item['quantity']) for item in data['items'])
        total_unique_products = len(data['items'])
        subtotal = sum(float(item['retail_price']) * int(item['quantity']) for item in data['items'])
        total_savings = sum((float(item['mrp']) - float(item['retail_price'])) * int(item['quantity']) for item in data['items'])
        points_earned = int(subtotal // 100)

        # customer handling
        customer = None
        old_balance = 0
        old_points = 0
        if data['customer'].get('mobile'):
            customer = get_customer(data['customer']['mobile'])
            if customer:
                old_balance = customer['balance']
                old_points = customer['points']
            else:
                create_customer(data['customer']['mobile'], data['customer']['name'], data['customer'].get('address', ''))
                customer = get_customer(data['customer']['mobile'])
                if customer:
                    old_balance = customer['balance']
                    old_points = customer['points']

        new_debt = float(data.get('balance', {}).get('new_debt', 0))
        settle_debt = float(data.get('balance', {}).get('settle_debt', 0))
        new_balance = old_balance + new_debt - settle_debt

        cash_received = float(data.get('payment', {}).get('cash_received') or 0)
        cash_balance = cash_received - subtotal
        if cash_balance < 0:
            new_balance = new_balance + abs(cash_balance)

        if data['customer'].get('mobile'):
            customer_data = {
                'mobile': data['customer']['mobile'],
                'name': data['customer']['name'],
                'address': data['customer'].get('address', ''),
                'points': old_points + points_earned,
                'balance': new_balance
            }
            update_customer(customer_data)
        else:
            customer_data = {'mobile': 'N/A', 'name': 'பதிவில்லா வாடிக்கையாளர்', 'address': '-', 'points': 0, 'balance': 0}

        bill_data = {
            'bill_number': bill_number,
            'customer_mobile': data['customer'].get('mobile') if data['customer'].get('mobile') else 'N/A',
            'date': current_date,
            'time': current_time,
            'total_items': total_items,
            'total_unique_products': total_unique_products,
            'subtotal': subtotal,
            'total_savings': total_savings,
            'payment_type': data.get('payment', {}).get('payment_type', 'CASH'),
            'cash_received': cash_received,
            'cash_balance': cash_balance,
            'old_balance': old_balance,
            'new_balance': new_balance,
            'points_earned': points_earned if data['customer'].get('mobile') else 0
        }

        items_data = []
        for item in data['items']:
            display_name = item.get('tamil_name') or item.get('name') or ''
            items_data.append({
                'bill_number': bill_number,
                'product_name': display_name,
                'quantity': item['quantity'],
                'unit': item.get('unit', 'count'),
                'mrp': item['mrp'],
                'retail_price': item['retail_price'],
                'total_price': float(item['retail_price']) * int(item['quantity'])
            })

        if not save_bill(bill_data, items_data):
            return jsonify({'error': 'Failed to save bill'}), 500

        bill_string = generate_bill_string(bill_data, customer_data, items_data)

        # Printing: Win32 hDC path (if available)
        try:
            printer_name = BILL_PRINTER_NAME
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)

            hDC.StartDoc("Supermarket Bill")
            hDC.StartPage()

            # Fonts (attempt bold + normal)
            bold_font = win32ui.CreateFont({"name": "Nirmala UI", "height": 16, "weight": 700})
            normal_font = win32ui.CreateFont({"name": "Nirmala UI", "height": 14, "weight": 400})

            # Helper to measure with a chosen font
            def px_width_with_font(s, font):
                hDC.SelectObject(font)
                return hDC.GetTextExtent(str(s))[0]

            def px_height_with_font(font):
                hDC.SelectObject(font)
                return hDC.GetTextExtent("A")[1]

            # Bold-draw helper: prefer font weight, fallback to 2-pass offset draw for emulated bold
            def draw_bold_text(x, y, text, preferred_font, fallback_normal_font):
                # Try preferred bold font first
                hDC.SelectObject(preferred_font)
                w_bold = hDC.GetTextExtent(text)[0]
                # Measure with normal font too to detect if bold changed metrics (simple heuristic)
                hDC.SelectObject(fallback_normal_font)
                w_norm = hDC.GetTextExtent(text)[0]
                # If bold font has same width as normal font, printer/font may ignore weight -> emulate
                if w_bold == w_norm:
                    # emulate bold by drawing twice (1px right)
                    hDC.SelectObject(preferred_font)
                    hDC.TextOut(x, y, text)
                    hDC.TextOut(x + 1, y, text)
                else:
                    hDC.SelectObject(preferred_font)
                    hDC.TextOut(x, y, text)

            # default font to normal for measurements initially
            hDC.SelectObject(normal_font)

            def pixel_width(s):
                return hDC.GetTextExtent(str(s))[0]

            def pixel_height(s='A'):
                return hDC.GetTextExtent(str(s))[1]

            # Get printable area in px
            try:
                printable_width_px = hDC.GetDeviceCaps(win32con.HORZRES)
            except Exception:
                printable_width_px = None

            if not printable_width_px or printable_width_px <= 0:
                try:
                    dpi_x = hDC.GetDeviceCaps(win32con.LOGPIXELSX) or 203
                except Exception:
                    dpi_x = 203
                paper_cm = 7.5
                printable_width_px = int(dpi_x * (paper_cm / 2.54))

            margin_px = max(8, int(0.03 * printable_width_px))
            x0 = margin_px
            content_px = max(120, printable_width_px - margin_px * 2)

            # Column widths in pixels (fractions of content area)
            pct = {'name': 0.50, 'qty': 0.10, 'mrp': 0.13, 'rate': 0.13, 'total': 0.14}
            name_px = int(content_px * pct['name'])
            qty_px = int(content_px * pct['qty'])
            mrp_px = int(content_px * pct['mrp'])
            rate_px = int(content_px * pct['rate'])
            total_px = int(content_px * pct['total'])

            # Compute right-edge coordinates from the far right (guarantees strict columns)
            content_right = x0 + content_px  # far right pixel of content area
            total_right = content_right
            rate_right = total_right - total_px
            mrp_right = rate_right - rate_px
            qty_right = mrp_right - mrp_px
            name_x = x0
            # name column width is name_px (from name_x to qty_right)

            # separators
            zero_w = px_width_with_font('0', normal_font) or 6
            sep_chars = max(10, content_px // zero_w)
            sep_line = '-' * sep_chars

            y = 20
            lh = px_height_with_font(normal_font) + 6

            # --- Header: center supermarket name and address ---
            center_x = x0 + content_px // 2

            # Title (bold)
            title = "SRI VELAVAN SUPERMARKET"
            # draw bold centered
            title_x = center_x - (px_width_with_font(title, bold_font) // 2)
            draw_bold_text(title_x, y, title, bold_font, normal_font)
            y += lh

            # Address lines (normal)
            for hl in [
                "2/136A, Pillaiyar Koil Street",
                "A.Kottarakuppam, Virudhachalam",
                "Ph: 9626475471  GST:33FLEPM3791Q1ZD",
            ]:
                tx = center_x - (px_width_with_font(hl, normal_font) // 2)
                hDC.SelectObject(normal_font)
                hDC.TextOut(tx, y, hl)
                y += lh

            # meta and separators (left-aligned)
            hDC.SelectObject(normal_font)
            hDC.TextOut(x0, y, sep_line); y += lh
            hDC.TextOut(x0, y, f"பில் எண் : {bill_data['bill_number']}"); y += lh
            hDC.TextOut(x0, y, f"தேதி     : {bill_data['date']} {bill_data['time']}"); y += lh
            hDC.TextOut(x0, y, sep_line); y += lh

            # customer block
            hDC.TextOut(x0, y, "வாடிக்கையாளர்:"); y += lh
            draw_bold_text(x0, y, f"பெயர்    : {customer_data['name']}", bold_font, normal_font); y += lh
            if customer_data.get('mobile') and customer_data.get('mobile') != 'N/A':
                hDC.SelectObject(normal_font)
                hDC.TextOut(x0, y, f"மொபைல்  : {customer_data['mobile']}"); y += lh
                hDC.TextOut(x0, y, f"புள்ளிகள்: {customer_data.get('points', 0)}"); y += lh
            hDC.TextOut(x0, y, sep_line); y += lh

            # column headers: product name at left, numbers right-aligned
            draw_bold_text(name_x, y, "பொருள்", bold_font, normal_font)
            # numbers headers measured with normal font
            t = "அளவு"; hDC.SelectObject(normal_font); hDC.TextOut(qty_right - px_width_with_font(t, normal_font), y, t)
            t = "MRP"; hDC.TextOut(mrp_right - px_width_with_font(t, normal_font), y, t)
            t = "விலை"; hDC.TextOut(rate_right - px_width_with_font(t, normal_font), y, t)
            t = "தொகை"; hDC.TextOut(total_right - px_width_with_font(t, normal_font), y, t)
            y += lh
            hDC.TextOut(x0, y, sep_line); y += lh

            # items: draw product name bold (real or emulated), numbers right-aligned
            for item in items_data:
                qty_text = str(int(item.get('quantity', 0))) if float(item.get('quantity', 0)).is_integer() else str(item.get('quantity', 0))
                mrp_text = f"{float(item.get('mrp', 0)):.2f}"
                rate_text = f"{float(item.get('retail_price', 0)):.2f}"
                total_text = f"{float(item.get('total_price', 0)):.2f}"

                # Split/wrap name into lines that fit name_px
                name_lines = split_text_to_pixel_width(str(item.get('product_name', '')), name_px, hDC, max_lines=2, ellipsis='...')

                for idx, nl in enumerate(name_lines):
                    # draw bold product name in left column
                    draw_bold_text(name_x, y, nl, bold_font, normal_font)

                    # On first line print numbers aligned to the right edges
                    if idx == 0:
                        hDC.SelectObject(normal_font)
                        hDC.TextOut(qty_right - px_width_with_font(qty_text, normal_font), y, qty_text)
                        hDC.TextOut(mrp_right - px_width_with_font(mrp_text, normal_font), y, mrp_text)
                        hDC.TextOut(rate_right - px_width_with_font(rate_text, normal_font), y, rate_text)
                        hDC.TextOut(total_right - px_width_with_font(total_text, normal_font), y, total_text)
                    y += lh

                # separator after item
                hDC.SelectObject(normal_font)
                hDC.TextOut(x0, y, sep_line)
                y += lh

            # footer totals (left aligned for labels)
            hDC.TextOut(x0, y, sep_line); y += lh
            hDC.TextOut(x0, y, f"மொத்த பொருட்கள் : {bill_data['total_unique_products']}"); y += lh
            hDC.TextOut(x0, y, f"மொத்த அளவு     : {bill_data['total_items']}"); y += lh
            hDC.TextOut(x0, y, f"மொத்தம்        : ₹{bill_data['subtotal']:.2f}"); y += lh
            hDC.TextOut(x0, y, f"சேமிப்பு       : ₹{bill_data['total_savings']:.2f}"); y += lh

            if bill_data.get('customer_mobile') and bill_data['customer_mobile'] != 'N/A':
                hDC.TextOut(x0, y, sep_line); y += lh
                hDC.TextOut(x0, y, f"பழைய நிலுவை    : ₹{bill_data['old_balance']:.2f}"); y += lh
                hDC.TextOut(x0, y, f"புதிய நிலுவை   : ₹{bill_data['new_balance']:.2f}"); y += lh

            hDC.TextOut(x0, y, sep_line); y += lh
            hDC.TextOut(x0, y, f"செலுத்தும் முறை: {bill_data['payment_type']}"); y += lh
            hDC.TextOut(x0, y, f"பெற்றது       : ₹{bill_data['cash_received']:.2f}"); y += lh
            hDC.TextOut(x0, y, f"திருப்பியது    : ₹{bill_data['cash_balance']:.2f}"); y += lh
            hDC.TextOut(x0, y, sep_line); y += lh
            hDC.TextOut(x0, y, f"சம்பாதித்த புள்ளிகள்: {bill_data['points_earned']}"); y += lh
            hDC.TextOut(x0, y, sep_line); y += lh
            hDC.TextOut(x0, y, "     நன்றி! மீண்டும் வாருங்கள்!"); y += lh

            hDC.EndPage()
            hDC.EndDoc()
            hDC.DeleteDC()

        except Exception as print_error:
            # keep API success (we still return bill_string) but log print error
            print(f"Print error: {print_error}")

        return jsonify({'success': True, 'bill_number': bill_number, 'bill_string': bill_string, 'customer_data': customer_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ---- Insert the following into app.py (after existing routes like /today_totals) ----

from flask import render_template_string  # add if not already imported at top

@app.route('/transactions')
def transactions():
    """
    Query params:
      period = 'today' or 'this_month'
    Returns JSON list of bills with required fields.
    """
    period = request.args.get('period', 'today')
    try:
        conn = sqlite3.connect(BILLS_DB)
        cursor = conn.cursor()
        if period == 'this_month':
            # bills.date format is 'dd/mm/YYYY' — extract mm/YYYY
            month_year = datetime.now().strftime('%m/%Y')
            cursor.execute('''
                SELECT bill_number, customer_mobile, date, time, total_items, subtotal, cash_balance, payment_type
                FROM bills
                WHERE substr(date,4,7) = ?
                ORDER BY date DESC, time DESC
            ''', (month_year,))
        else:
            # default -> today
            today = datetime.now().strftime('%d/%m/%Y')
            cursor.execute('''
                SELECT bill_number, customer_mobile, date, time, total_items, subtotal, cash_balance, payment_type
                FROM bills
                WHERE date = ?
                ORDER BY time DESC
            ''', (today,))
        rows = cursor.fetchall()
        conn.close()

        results = []
        for r in rows:
            bill_number, customer_mobile, date, time, total_items, subtotal, cash_balance, payment_type = r
            # customer id: using bill_number as unique id; customer phone is customer_mobile
            results.append({
                'bill_number': bill_number,
                'customer_id': bill_number,
                'customer_phone': customer_mobile if customer_mobile and customer_mobile != 'N/A' else '-',
                'date': date,
                'time': time,
                'total_products_sold': int(total_items or 0),
                'total_amount_received': float(subtotal or 0.0),
                'balance_given': float(cash_balance or 0.0),
                'payment_mode': payment_type
            })

        return jsonify({'period': period, 'count': len(results), 'transactions': results})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# @app.route('/get_bill/<bill_number>')
# def get_bill_json(bill_number):
#     """
#     Return bill metadata + items for a bill_number (JSON).
#     """
#     try:
#         conn = sqlite3.connect(BILLS_DB)
#         cursor = conn.cursor()
#         cursor.execute('SELECT bill_number, customer_mobile, date, time, total_items, total_unique_products, subtotal, total_savings, payment_type, cash_received, cash_balance, old_balance, new_balance, points_earned FROM bills WHERE bill_number = ?', (bill_number,))
#         b = cursor.fetchone()
#         if not b:
#             conn.close()
#             return jsonify({'error': 'Bill not found'}), 404

#         bill = {
#             'bill_number': b[0],
#             'customer_mobile': b[1],
#             'date': b[2],
#             'time': b[3],
#             'total_items': int(b[4] or 0),
#             'total_unique_products': int(b[5] or 0),
#             'subtotal': float(b[6] or 0.0),
#             'total_savings': float(b[7] or 0.0),
#             'payment_type': b[8],
#             'cash_received': float(b[9] or 0.0),
#             'cash_balance': float(b[10] or 0.0),
#             'old_balance': float(b[11] or 0.0),
#             'new_balance': float(b[12] or 0.0),
#             'points_earned': int(b[13] or 0)
#         }

#         cursor.execute('SELECT product_name, quantity, unit, mrp, retail_price, total_price FROM bill_items WHERE bill_number = ?', (bill_number,))
#         items_rows = cursor.fetchall()
#         conn.close()

#         items = []
#         for it in items_rows:
#             items.append({
#                 'product_name': it[0],
#                 'quantity': it[1],
#                 'unit': it[2],
#                 'mrp': float(it[3]),
#                 'retail_price': float(it[4]),
#                 'total_price': float(it[5])
#             })

#         return jsonify({'bill': bill, 'items': items})
#     except Exception as e:
#         return jsonify({'error': str(e)}), 500


# @app.route('/view_bill/<bill_number>')
# def view_bill(bill_number):
#     """
#     Small HTML view to open in a new tab showing the bill and list of products.
#     This is intentionally minimal and self-contained to avoid creating extra templates.
#     """
#     try:
#         res = get_bill_json.__wrapped__(bill_number)  # call underlying function quickly
#         # If previous call returned a Flask response (tuple), handle
#         if isinstance(res, tuple):
#             # means an error (response, status)
#             return res
#         data = res.get_json() if hasattr(res, 'get_json') else res
#         if data.get('error'):
#             return f"<h3>Bill not found: {bill_number}</h3>", 404

#         bill = data['bill']
#         items = data['items']

#         html = f"""
#         <html><head><title>Bill {bill_number}</title>
#         <style>
#           body {{ font-family: Arial, sans-serif; padding:16px; max-width:800px; }}
#           table {{ width:100%; border-collapse:collapse; margin-top:12px; }}
#           th,td {{ padding:8px; border:1px solid #ddd; text-align:left; }}
#           th {{ background:#f6f6f6; }}
#         </style>
#         </head><body>
#           <h2>Bill: {bill_number}</h2>
#           <div><strong>Date:</strong> {bill['date']} <strong>Time:</strong> {bill['time']}</div>
#           <div><strong>Customer phone:</strong> {bill['customer_mobile'] if bill['customer_mobile'] and bill['customer_mobile']!='N/A' else '-'}</div>
#           <div><strong>Payment:</strong> {bill['payment_type']}</div>
#           <div style="margin-top:12px;"><strong>Totals:</strong> Items: {bill['total_items']}, Unique: {bill['total_unique_products']}, Subtotal: ₹{bill['subtotal']:.2f}, Balance given: ₹{bill['cash_balance']:.2f}</div>
#           <h3 style="margin-top:18px">Products</h3>
#           <table>
#             <thead><tr><th>#</th><th>Product</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Total</th></tr></thead>
#             <tbody>
#         """
#         for idx,it in enumerate(items, start=1):
#             html += f"<tr><td>{idx}</td><td>{it['product_name']}</td><td>{it['quantity']}</td><td>{it['unit']}</td><td>₹{it['retail_price']:.2f}</td><td>₹{it['total_price']:.2f}</td></tr>"
#         html += "</tbody></table></body></html>"
#         return html
#     except Exception as e:
#         return f"<h3>Error: {e}</h3>", 500


def fetch_bill_data(bill_number):
    conn = sqlite3.connect(BILLS_DB)
    cursor = conn.cursor()
    cursor.execute('SELECT bill_number, customer_mobile, date, time, total_items, total_unique_products, subtotal, total_savings, payment_type, cash_received, cash_balance, old_balance, new_balance, points_earned FROM bills WHERE bill_number = ?', (bill_number,))
    b = cursor.fetchone()
    if not b:
        conn.close()
        return None, None
    bill = {
        'bill_number': b[0],
        'customer_mobile': b[1],
        'date': b[2],
        'time': b[3],
        'total_items': int(b[4] or 0),
        'total_unique_products': int(b[5] or 0),
        'subtotal': float(b[6] or 0.0),
        'total_savings': float(b[7] or 0.0),
        'payment_type': b[8],
        'cash_received': float(b[9] or 0.0),
        'cash_balance': float(b[10] or 0.0),
        'old_balance': float(b[11] or 0.0),
        'new_balance': float(b[12] or 0.0),
        'points_earned': int(b[13] or 0)
    }
    cursor.execute('SELECT product_name, quantity, unit, mrp, retail_price, total_price FROM bill_items WHERE bill_number = ?', (bill_number,))
    items_rows = cursor.fetchall()
    conn.close()
    items = [{
        'product_name': it[0],
        'quantity': it[1],
        'unit': it[2],
        'mrp': float(it[3]),
        'retail_price': float(it[4]),
        'total_price': float(it[5])
    } for it in items_rows]
    return bill, items

@app.route('/get_bill/<bill_number>')
def get_bill_json(bill_number):
    bill, items = fetch_bill_data(bill_number)
    if not bill:
        return jsonify({'error': 'Bill not found'}), 404
    return jsonify({'bill': bill, 'items': items})


@app.route('/view_bill/<bill_number>')
def view_bill(bill_number):
    """
    HTML view to open in a new tab showing the bill and list of products.
    Always returns a valid Flask response (string or tuple with status).
    """
    try:
        bill, items = fetch_bill_data(bill_number)
        if not bill:
            return f"<h3>Bill not found: {bill_number}</h3>", 404

        # Build simple but clean HTML for viewing in new tab
        html = f"""
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8">
          <meta name="viewport" content="width=device-width,initial-scale=1">
          <title>Bill {bill_number}</title>
          <style>
            body {{ font-family: Arial, sans-serif; padding:18px; color:#222; }}
            .container {{ max-width:900px; margin:0 auto; }}
            h2 {{ margin:0 0 8px 0; }}
            .meta {{ margin-bottom:12px; color:#333; }}
            table {{ width:100%; border-collapse:collapse; margin-top:8px; }}
            th,td {{ padding:8px; border:1px solid #e6e6e6; text-align:left; font-size:14px; }}
            th {{ background: linear-gradient(90deg,#2c3e50,#3498db); color:white; }}
            .totals {{ margin-top:12px; padding:10px; background:#fafafa; border:1px solid #eee; }}
            .small {{ font-size:13px; color:#555; }}
          </style>
        </head>
        <body>
          <div class="container">
            <h2>Bill: {bill_number}</h2>
            <div class="meta small">
              <strong>Date:</strong> {bill['date']} &nbsp;&nbsp;
              <strong>Time:</strong> {bill['time']} &nbsp;&nbsp;
              <strong>Customer:</strong> {(bill['customer_mobile'] if bill['customer_mobile'] and bill['customer_mobile'] != 'N/A' else '-')}
            </div>

            <div class="totals">
              <div><strong>Items:</strong> {bill['total_items']} &nbsp;&nbsp; <strong>Unique:</strong> {bill['total_unique_products']}</div>
              <div><strong>Subtotal:</strong> ₹{bill['subtotal']:.2f} &nbsp;&nbsp; <strong>Balance given:</strong> ₹{bill['cash_balance']:.2f}</div>
              <div><strong>Payment:</strong> {bill['payment_type']}</div>
            </div>

            <h3 style="margin-top:16px;">Products</h3>
            <table>
              <thead>
                <tr><th>#</th><th>Product</th><th>Qty</th><th>Unit</th><th>Rate</th><th>Total</th></tr>
              </thead>
              <tbody>
        """

        for idx, it in enumerate(items, start=1):
            pname = (it.get('product_name') or '')
            qty = it.get('quantity') or 0
            unit = it.get('unit') or ''
            rate = float(it.get('retail_price') or 0.0)
            total = float(it.get('total_price') or 0.0)
            html += f"<tr><td>{idx}</td><td>{pname}</td><td>{qty}</td><td>{unit}</td><td>₹{rate:.2f}</td><td>₹{total:.2f}</td></tr>"

        html += """
              </tbody>
            </table>

            <div class="totals" style="margin-top:16px;">
        """
        html += f"<div><strong>Subtotal:</strong> ₹{bill['subtotal']:.2f}</div>"
        html += f"<div><strong>Total savings:</strong> ₹{bill.get('total_savings', 0.0):.2f}</div>"
        if bill.get('customer_mobile') and bill['customer_mobile'] != 'N/A':
            html += f"<div><strong>Old balance:</strong> ₹{bill.get('old_balance',0.0):.2f} &nbsp;&nbsp; <strong>New balance:</strong> ₹{bill.get('new_balance',0.0):.2f}</div>"
        html += f"<div><strong>Cash received:</strong> ₹{bill.get('cash_received',0.0):.2f} &nbsp;&nbsp; <strong>Change:</strong> ₹{bill.get('cash_balance',0.0):.2f}</div>"
        html += "</div>"

        html += """
            <div style="margin-top:18px; font-size:13px; color:#666;">Generated by POS</div>
          </div>
        </body>
        </html>
        """

        return html

    except Exception as e:
        # Return an explicit error HTML rather than letting Flask return None
        return f"<h3>Error rendering bill: {e}</h3>", 500



if __name__ == '__main__':
    init_databases()
    app.run(debug=True, port=5002)