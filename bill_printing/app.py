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

def format_thermal_bill(items, width=38):
    # Adjusted widths for better alignment on 7.5cm thermal paper
    name_w = 16
    qty_w = 4
    mrp_w = 7
    rate_w = 7
    tot_w = 6
    
    # Create properly spaced header
    header = f"{'பொருள்':<{name_w}}{'அளவு':>{qty_w}}{'MRP':>{mrp_w}}{'விலை':>{rate_w}}{'தொகை':>{tot_w}}"
    line_sep = '=' * width
    lines = [line_sep, header, line_sep]
    
    for item in items:
        qty = str(int(item.get('quantity', 0))) if float(item.get('quantity', 0)).is_integer() else str(item.get('quantity'))
        mrp_val = f"{float(item.get('mrp',0)):.2f}"
        rate_val = f"{float(item.get('retail_price',0)):.2f}"
        total_val = f"{float(item.get('total_price',0)):.2f}"
        
        name_lines = wrap_text_to_max_lines(str(item.get('product_name','')), name_w, max_lines=2)
        
        # First line with all details
        left_part = name_lines[0].ljust(name_w)
        qty_part = qty.rjust(qty_w)
        mrp_part = mrp_val.rjust(mrp_w)
        rate_part = rate_val.rjust(rate_w)
        total_part = total_val.rjust(tot_w)
        
        first_line = left_part + qty_part + mrp_part + rate_part + total_part
        lines.append(first_line)
        
        # Additional name lines if product name is long
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
    WIDTH = 38
    SEP = '_' * WIDTH
    SEP2 = '-' * WIDTH
    header_lines = [
        SEP,
        "   SRI VELAVAN SUPERMARKET",
        "   2/136A, Pillaiyar Koil Street",
        "   A.Kottarakuppam, Virudhachalam",
        "   Ph: 9626475471  GST:33FLEPM3791Q1ZD",
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
    bill_string += SEP + '\n'
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
def create_bill():
    try:
        data = request.json
        bill_number = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"
        now = datetime.now()
        current_date = now.strftime('%d/%m/%Y')
        current_time = now.strftime('%H:%M:%S')

        total_items = sum(int(item['quantity']) for item in data['items'])
        total_unique_products = len(data['items'])
        subtotal = sum(float(item['retail_price']) * int(item['quantity']) for item in data['items'])
        total_savings = sum((float(item['mrp']) - float(item['retail_price'])) * int(item['quantity']) for item in data['items'])
        points_earned = int(subtotal // 100)

        customer = None
        old_balance = 0
        old_points = 0
        if data['customer']['mobile']:
            customer = get_customer(data['customer']['mobile'])
            if customer:
                old_balance = customer['balance']
                old_points = customer['points']
            else:
                create_customer(data['customer']['mobile'], data['customer']['name'], data['customer']['address'])
                customer = get_customer(data['customer']['mobile'])
                if customer:
                    old_balance = customer['balance']
                    old_points = customer['points']

        new_debt = float(data['balance'].get('new_debt', 0))
        settle_debt = float(data['balance'].get('settle_debt', 0))
        new_balance = old_balance + new_debt - settle_debt

        cash_received = float(data['payment']['cash_received']) if data['payment']['cash_received'] else 0
        cash_balance = cash_received - subtotal
        if cash_balance < 0:
            new_balance = new_balance + abs(cash_balance)

        if data['customer']['mobile']:
            customer_data = {'mobile': data['customer']['mobile'], 'name': data['customer']['name'], 'address': data['customer']['address'], 'points': old_points + points_earned, 'balance': new_balance}
            update_customer(customer_data)
        else:
            customer_data = {'mobile': 'N/A', 'name': 'பதிவில்லா வாடிக்கையாளர்', 'address': '-', 'points': 0, 'balance': 0}

        bill_data = {
            'bill_number': bill_number,
            'customer_mobile': data['customer']['mobile'] if data['customer']['mobile'] else 'N/A',
            'date': current_date,
            'time': current_time,
            'total_items': total_items,
            'total_unique_products': total_unique_products,
            'subtotal': subtotal,
            'total_savings': total_savings,
            'payment_type': data['payment']['payment_type'],
            'cash_received': cash_received,
            'cash_balance': cash_balance,
            'old_balance': old_balance,
            'new_balance': new_balance,
            'points_earned': points_earned if data['customer']['mobile'] else 0
        }

        items_data = []
        for item in data['items']:
            display_name = item.get('tamil_name') or item.get('name') or ''
            items_data.append({'bill_number': bill_number, 'product_name': display_name, 'quantity': item['quantity'], 'unit': item.get('unit', 'count'), 'mrp': item['mrp'], 'retail_price': item['retail_price'], 'total_price': float(item['retail_price']) * int(item['quantity'])})

        if not save_bill(bill_data, items_data):
            return jsonify({'error': 'Failed to save bill'}), 500

        bill_string = generate_bill_string(bill_data, customer_data, items_data)

                   # Printing: use printer HORZRES (printable width) and left-aligned layout
        try:
            printer_name = win32print.GetDefaultPrinter()
            hDC = win32ui.CreateDC()
            hDC.CreatePrinterDC(printer_name)
            hDC.StartDoc("Supermarket Bill")
            hDC.StartPage()

            # Fonts: bold for headings/names, normal for numbers/body
            bold_font = win32ui.CreateFont({"name": "Nirmala UI", "height": 16, "weight": 700})
            normal_font = win32ui.CreateFont({"name": "Nirmala UI", "height": 14, "weight": 400})
            # default to normal for measurements & numbers
            hDC.SelectObject(normal_font)

            def pixel_width(s):
                return hDC.GetTextExtent(str(s))[0]

            def pixel_height(s='A'):
                return hDC.GetTextExtent(str(s))[1]

            # Use the printer's reported printable width when possible
            try:
                printable_width_px = hDC.GetDeviceCaps(win32con.HORZRES)
            except Exception:
                printable_width_px = None

            # fallback to DPI * inches if HORZRES isn't available
            if not printable_width_px or printable_width_px <= 0:
                try:
                    dpi_x = hDC.GetDeviceCaps(win32con.LOGPIXELSX) or 203
                except Exception:
                    dpi_x = 203
                paper_cm = 7.5
                printable_width_px = int(dpi_x * (paper_cm / 2.54))

            # left/right margins (small)
            margin_px = max(8, int(0.03 * printable_width_px))
            x0 = margin_px
            content_px = max(120, printable_width_px - margin_px * 2)

            # column distribution tuned for names + numbers on narrow paper (sum ~=1.0)
            pct = {'name': 0.50, 'qty': 0.10, 'mrp': 0.13, 'rate': 0.13, 'total': 0.14}
            name_px = int(content_px * pct['name'])
            qty_px = int(content_px * pct['qty'])
            mrp_px = int(content_px * pct['mrp'])
            rate_px = int(content_px * pct['rate'])
            total_px = int(content_px * pct['total'])

            name_x = x0
            qty_right = name_x + name_px + qty_px
            mrp_right = qty_right + mrp_px
            rate_right = mrp_right + rate_px
            total_right = rate_right + total_px

            # separators based on character count (monospace approx)
            zero_w = pixel_width('0') or 6
            sep_chars = max(10, content_px // zero_w)
            sep_line = '-' * sep_chars
            sep_line2 = '_' * sep_chars

            y = 20
            lh = pixel_height() + 6

            # Header: bold supermarket name, normal for remaining header lines
            hDC.SelectObject(bold_font)
            hDC.TextOut(x0, y, "SRI VELAVAN SUPERMARKET")
            y += lh
            hDC.SelectObject(normal_font)
            for hl in [
                "2/136A, Pillaiyar Koil Street",
                "A.Kottarakuppam, Virudhachalam",
                "Ph: 9626475471  GST:33FLEPM3791Q1ZD",
            ]:
                hDC.TextOut(x0, y, hl)
                y += lh
            hDC.TextOut(x0, y, sep_line)
            y += lh

            # bill meta
            hDC.TextOut(x0, y, f"பில் எண் : {bill_data['bill_number']}")
            y += lh
            hDC.TextOut(x0, y, f"தேதி     : {bill_data['date']} {bill_data['time']}")
            y += lh
            hDC.TextOut(x0, y, sep_line)
            y += lh

            # customer
            hDC.TextOut(x0, y, "வாடிக்கையாளர்:")
            y += lh
            hDC.TextOut(x0, y, f"பெயர்    : {customer_data['name']}")
            y += lh
            if customer_data.get('mobile') and customer_data.get('mobile') != 'N/A':
                hDC.TextOut(x0, y, f"மொபைல்  : {customer_data['mobile']}")
                y += lh
                hDC.TextOut(x0, y, f"புள்ளிகள்: {customer_data.get('points', 0)}")
                y += lh
            hDC.TextOut(x0, y, sep_line)
            y += lh

            # column headers (numbers right-aligned)
            hDC.SelectObject(bold_font)
            hDC.TextOut(name_x, y, "பொருள்")
            hDC.SelectObject(normal_font)
            t = "அளவு"; w = pixel_width(t); hDC.TextOut(qty_right - w, y, t)
            t = "MRP"; w = pixel_width(t); hDC.TextOut(mrp_right - w, y, t)
            t = "விலை"; w = pixel_width(t); hDC.TextOut(rate_right - w, y, t)
            t = "தொகை"; w = pixel_width(t); hDC.TextOut(total_right - w, y, t)
            y += lh
            hDC.TextOut(x0, y, sep_line)
            y += lh

            # items
            for item in items_data:
                qty_text = str(int(item.get('quantity', 0))) if float(item.get('quantity', 0)).is_integer() else str(item.get('quantity'))
                mrp_text = f"{float(item.get('mrp', 0)):.2f}"
                rate_text = f"{float(item.get('retail_price', 0)):.2f}"
                total_text = f"{float(item.get('total_price', 0)):.2f}"

                # measure and wrap name using bold font so visual matches printed bold name
                hDC.SelectObject(bold_font)
                name_lines = split_text_to_pixel_width(str(item.get('product_name', '')), name_px, hDC, max_lines=2, ellipsis='...')
                for idx, nl in enumerate(name_lines):
                    hDC.TextOut(name_x, y, nl)
                    # for the first name line, print the numeric columns aligned with normal font
                    if idx == 0:
                        hDC.SelectObject(normal_font)
                        w = pixel_width(qty_text); hDC.TextOut(qty_right - w, y, qty_text)
                        w = pixel_width(mrp_text); hDC.TextOut(mrp_right - w, y, mrp_text)
                        w = pixel_width(rate_text); hDC.TextOut(rate_right - w, y, rate_text)
                        w = pixel_width(total_text); hDC.TextOut(total_right - w, y, total_text)
                        hDC.SelectObject(bold_font)  # switch back for continuation lines (name)
                    y += lh

                # separator after item
                hDC.SelectObject(normal_font)
                hDC.TextOut(x0, y, sep_line)
                y += lh

            # footer
            hDC.TextOut(x0, y, sep_line); y += lh
            hDC.TextOut(x0, y, f"மொத்த பொருட்கள் : {bill_data['total_unique_products']}"); y += lh
            hDC.TextOut(x0, y, f"மொத்த அளவு     : {bill_data['total_items']}"); y += lh
            hDC.TextOut(x0, y, f"மொத்தம்        : ₹{bill_data['subtotal']:.2f}"); y += lh
            hDC.TextOut(x0, y, f"சேமிப்பு       : ₹{bill_data['total_savings']:.2f}"); y += lh

            if bill_data.get('customer_mobile') and bill_data.get('customer_mobile') != 'N/A':
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
            print(f"Print error: {print_error}")

        return jsonify({'success': True, 'bill_number': bill_number, 'bill_string': bill_string, 'customer_data': customer_data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_databases()
    app.run(debug=True, port=5002)
