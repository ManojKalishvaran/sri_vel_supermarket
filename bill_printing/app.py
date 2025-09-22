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
def truncate_text_to_pixel_width(text, max_px, font, hdc, ellipsis='...'):
    """
    Return a single-line string that fits into max_px pixels when drawn with `font`.
    Adds ellipsis if truncated.
    """
    hdc.SelectObject(font)
    # quick full-check
    full_w = hdc.GetTextExtent(text)[0]
    if full_w == max_px:
        return text
    elif full_w < max_px:
        return text+ " "*(max_px - len(text))

    # binary-search by chars for speed
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi) // 2
        candidate = text[:mid].rstrip()
        w = hdc.GetTextExtent(candidate + ellipsis)[0]
        if w <= max_px:
            lo = mid + 1
        else:
            hi = mid
    # lo is first too-large index, so keep lo-1
    cut = max(0, lo - 1)
    result = text[:cut].rstrip()
    if not result:
        # fallback: return ellipsis if nothing fits
        return ellipsis if hdc.GetTextExtent(ellipsis)[0] <= max_px else ''
    # ensure final check
    while hdc.GetTextExtent(result + ellipsis)[0] > max_px and result:
        result = result[:-1]
    return (result + ellipsis) if result and hdc.GetTextExtent(result + ellipsis)[0] <= max_px else result


def format_thermal_bill(items, width=42, hDC=None):
    """
    Character fallback: single-line product name truncated to name_w chars (ellipsis).
    Numbers are strictly right-aligned so columns are consistent across rows.
    """
    name_w = 20   # product name column (left) - tweak if needed
    qty_w = 6
    mrp_w = 8
    rate_w = 8
    tot_w = 8

    header = (
        f"{'பொருள்'.ljust(name_w)}"
        f"{'அளவு'.rjust(qty_w)}"
        f"{'MRP'.rjust(mrp_w)}"
        f"{'விலை'.rjust(rate_w)}"
        f"{'தொகை'.rjust(tot_w)}"
    )

    lines = ['-' * width, header, '-' * width]

    for item in items:
        qty = str(int(item.get('quantity', 0))) if float(item.get('quantity', 0)).is_integer() else str(item.get('quantity', 0))
        mrp_val = f"{float(item.get('mrp', 0)):.2f}"
        rate_val = f"{float(item.get('retail_price', 0)):.2f}"
        total_val = f"{float(item.get('total_price', 0)):.2f}"

        # Truncate name to single line of name_w characters
        raw_name = str(item.get('product_name', ''))
        if len(raw_name) > name_w:
            name_display = ellipsize_line_by_chars(raw_name, name_w)
        else:
            name_display = raw_name

        line = (
            f"{name_display.ljust(name_w)}"
            f"{qty.rjust(qty_w)}"
            f"{mrp_val.rjust(mrp_w)}"
            f"{rate_val.rjust(rate_w)}"
            f"{total_val.rjust(tot_w)}"
        )
        lines.append(line)
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

def print_bill_strong(bill_data, items_data, customer_data, printer_name):
    """
    Pixel-precise, large & bold printing for Tamil + numeric columns.
    Call: print_bill_strong(bill_data, items_data, customer_data, BILL_PRINTER_NAME)
    """
    # Uses win32ui / win32con which are already imported at top of file.
    # Keep errors local to avoid breaking bill saving.
    try:
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)

        hDC.StartDoc("Supermarket Bill")
        hDC.StartPage()

        # Choose Tamil-capable fonts. Increase heights to make text very big.
        # If Noto Sans Tamil installed, replace "Nirmala UI" with "Noto Sans Tamil".
        header_font = win32ui.CreateFont({"name": "Nirmala UI", "height": 48, "weight": 900})
        bold_font   = win32ui.CreateFont({"name": "Nirmala UI", "height": 42, "weight": 900})
        normal_font = win32ui.CreateFont({"name": "Nirmala UI", "height": 40, "weight": 900})

        # small helpers
        def measure_px(s, font):
            hDC.SelectObject(font)
            return hDC.GetTextExtent(str(s))[0]

        def line_h(font):
            hDC.SelectObject(font)
            # use a Tamil glyph to estimate realistic height
            return hDC.GetTextExtent("ப")[1] + 8

        # strong draw: draw twice with 1px offset to force visible boldness
        def draw_strong(x, y, text, font):
            hDC.SelectObject(font)
            # primary draw
            hDC.TextOut(int(x), int(y), str(text))
            # second draw offset to strengthen strokes
            try:
                hDC.TextOut(int(x) + 1, int(y), str(text))
                # small vertical offset also helps on some printers:
                hDC.TextOut(int(x), int(y) + 1, str(text))
            except Exception:
                pass

        # pad/truncate by pixel width using NBSP (guarantees next column starts at fixed X)
        def fit_and_pad(text, px_target, font, ellipsis='...'):
            hDC.SelectObject(font)
            txt = str(text)
            if measure_px(txt, font) <= px_target:
                out = txt
                nb = '\u00A0'
                # append NBSP until visually >= px_target (safeguarded loop)
                tries = 0
                while measure_px(out, font) < px_target and tries < 500:
                    out += nb
                    tries += 1
                return out
            # binary search for longest prefix that fits with ellipsis
            lo, hi, best = 0, len(txt), ''
            while lo < hi:
                mid = (lo + hi) // 2
                cand = txt[:mid].rstrip() + ellipsis
                if measure_px(cand, font) <= px_target:
                    best = cand
                    lo = mid + 1
                else:
                    hi = mid
            return best if best else (ellipsis if measure_px(ellipsis, font) <= px_target else '')

        # split name into up to two lines constrained by pixel width
        def split_name_lines(raw_text, px_target, font, max_lines=2, ellipsis='...'):
            raw = str(raw_text)
            lines = []
            cur = ''
            for ch in raw:
                if measure_px(cur + ch, font) <= px_target:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
                    if len(lines) >= max_lines:
                        break
            if cur and len(lines) < max_lines:
                lines.append(cur)
            if not lines:
                lines = ['']
            # if unconsumed characters exist, ellipsize last line to fit
            consumed_len = sum(len(l) for l in lines)
            if consumed_len < len(raw):
                last = lines[-1]
                # trim last until it fits with ellipsis
                while last and measure_px(last + ellipsis, font) > px_target:
                    last = last[:-1]
                lines[-1] = (last + ellipsis) if last else ellipsis
            # pad each line to exact pixel width using NBSP
            nb = '\u00A0'
            for i in range(len(lines)):
                tries = 0
                while measure_px(lines[i] + nb, font) <= px_target and tries < 500:
                    lines[i] += nb
                    tries += 1
                # ensure at least close to px_target; rare case add one more NBSP
                if measure_px(lines[i], font) < px_target:
                    lines[i] += nb
            # ensure length == max_lines by appending empty padded strings if needed
            while len(lines) < max_lines:
                lines.append('') 
            return lines[:max_lines]

        # compute printable width (dpi-aware)
        try:
            printable_width_px = hDC.GetDeviceCaps(win32con.HORZRES)
        except Exception:
            dpi_x = hDC.GetDeviceCaps(win32con.LOGPIXELSX) or 203
            paper_cm = 7.5
            printable_width_px = int(dpi_x * (paper_cm / 2.54))

        margin = max(8, int(0.03 * printable_width_px))
        x0 = margin
        content_px = max(200, printable_width_px - margin * 2)

        # column pixel allocation: name gets most of the space
        name_px  = int(content_px * 0.56)
        qty_px   = int(content_px * 0.10)
        mrp_px   = int(content_px * 0.10)
        rate_px  = int(content_px * 0.12)
        total_px = content_px - (name_px + qty_px + mrp_px + rate_px)

        # column start Xs
        name_x  = x0
        qty_x   = name_x + name_px
        mrp_x   = qty_x + qty_px
        rate_x  = mrp_x + mrp_px
        total_x = rate_x + rate_px

        # right anchors for numeric columns (slightly inset)
        qty_right   = qty_x + qty_px - 4
        mrp_right   = mrp_x + mrp_px - 4
        rate_right  = rate_x + rate_px - 4
        total_right = total_x + total_px - 4

        # vertical layout
        y = 20
        lh = line_h(normal_font)

        # header center
        title = "SRI VELAVAN SUPERMARKET"
        center_x = x0 + content_px // 2
        title_x = center_x - (measure_px(title, header_font) // 2)
        draw_strong(title_x, y, title, header_font)
        y += lh
        for line in ["2/136A, Pillaiyar Koil Street", "A.Kottarakuppam, Virudhachalam", "Ph: 9626475471  GST:33FLEPM3791Q1ZD"]:
            draw_strong(center_x - (measure_px(line, bold_font) // 2), y, line, bold_font)
            y += lh

        # separator
        zero_w = measure_px('0', normal_font) or 6
        sep_chars = max(12, content_px // zero_w)
        sep_line = '-' * sep_chars
        draw_strong(x0, y, sep_line, normal_font); y += lh

        # meta info
        draw_strong(x0, y, f"பில் எண் : {bill_data.get('bill_number','')}", normal_font); y += lh
        draw_strong(x0, y, f"தேதி     : {bill_data.get('date','')} {bill_data.get('time','')}", normal_font); y += lh
        draw_strong(x0, y, sep_line, normal_font); y += lh

        # column headers (pad name column)
        draw_strong(name_x, y, fit_and_pad("பொருள்", name_px, bold_font), bold_font)
        # right aligned column titles
        draw_strong(qty_right - measure_px("அளவு", bold_font), y, "அளவு", bold_font)
        draw_strong(mrp_right - measure_px("MRP", bold_font), y, "MRP", bold_font)
        draw_strong(rate_right - measure_px("விலை", bold_font), y, "விலை", bold_font)
        draw_strong(total_right - measure_px("தொகை", bold_font), y, "தொகை", bold_font)
        y += lh
        draw_strong(x0, y, sep_line, normal_font); y += lh

        # items
        for it in items_data:
            pname = it.get('product_name','') or ''
            qty = it.get('quantity', 0)
            qty_s = str(int(qty) if float(qty).is_integer() else qty)
            mrp_s = f"{float(it.get('mrp',0)):.2f}"
            rate_s = f"{float(it.get('retail_price',0)):.2f}"
            tot_s = f"{float(it.get('total_price',0)):.2f}"

            name_lines = split_name_lines(pname, name_px, normal_font, max_lines=2)
            # first line: name + right-aligned numbers
            draw_strong(name_x, y, name_lines[0], normal_font)
            draw_strong(qty_right - measure_px(qty_s, normal_font), y, qty_s, normal_font)
            draw_strong(mrp_right - measure_px(mrp_s, normal_font), y, mrp_s, normal_font)
            draw_strong(rate_right - measure_px(rate_s, normal_font), y, rate_s, normal_font)
            draw_strong(total_right - measure_px(tot_s, normal_font), y, tot_s, normal_font)
            y += lh

            # optional second name line
            if name_lines[1].strip():
                draw_strong(name_x, y, name_lines[1], normal_font)
                y += lh

            draw_strong(x0, y, sep_line, normal_font); y += lh

        # footer totals
        draw_strong(x0, y, sep_line, normal_font); y += lh
        draw_strong(x0, y, f"மொத்த பொருட்கள் : {bill_data.get('total_unique_products',0)}", bold_font); y += lh
        draw_strong(x0, y, f"மொத்தம்        : ₹{float(bill_data.get('subtotal',0)):.2f}", bold_font); y += lh
        draw_strong(x0, y, f"சேமிப்பு       : ₹{float(bill_data.get('total_savings',0)):.2f}", bold_font); y += lh

        # customer-specific balances if present
        if bill_data.get('customer_mobile') and bill_data.get('customer_mobile') != 'N/A':
            draw_strong(x0, y, sep_line, normal_font); y += lh
            draw_strong(x0, y, f"பழைய நிலுவை    : ₹{float(bill_data.get('old_balance',0)):.2f}", normal_font); y += lh
            draw_strong(x0, y, f"புதிய நிலுவை   : ₹{float(bill_data.get('new_balance',0)):.2f}", normal_font); y += lh

        draw_strong(x0, y, sep_line, normal_font); y += lh
        draw_strong(x0 + 12, y, "நன்றி! மீண்டும் வாருங்கள்!", bold_font); y += lh

        # finalize
        hDC.EndPage()
        hDC.EndDoc()
        try:
            hDC.DeleteDC()
        except Exception:
            pass

    except Exception as e:
        # bubble error to caller via exception (or print it locally)
        raise

# requires: pip install pillow
from PIL import Image, ImageDraw, ImageFont, ImageWin
import math

def print_bill_image(bill_data, items_data, customer_data, printer_name, font_path=None):
    """
    Renders the bill into a raster image (PIL) and prints it to the given Windows printer.
    - printer_name: exact Windows printer name (e.g. 'RETSOL RTP 82UE')
    - font_path: path to a Tamil-capable TTF (e.g. 'C:/Windows/Fonts/NotoSansTamil-Regular.ttf').
                 If None, the system default will be tried (may fail for Tamil).
    """
    try:
        # --- Create DC and get device metrics ---
        hDC = win32ui.CreateDC()
        hDC.CreatePrinterDC(printer_name)

        # get DPI and printable area (pixels)
        LOGPIXELSX = win32con.LOGPIXELSX
        LOGPIXELSY = win32con.LOGPIXELSY
        HORZRES = win32con.HORZRES
        VERTRES = win32con.VERTRES

        dpi_x = hDC.GetDeviceCaps(LOGPIXELSX) or 203
        dpi_y = hDC.GetDeviceCaps(LOGPIXELSY) or dpi_x
        printable_w = hDC.GetDeviceCaps(HORZRES) or int(dpi_x * (7.2/2.54))  # fallback width ~7.2 cm
        # height we will allocate dynamically based on content
        margin_px = max(8, int(0.03 * printable_w))
        content_w = printable_w - margin_px * 2

        # --- Fonts: pick sizes relative to DPI ---
        # prefer a Tamil-capable font (Noto Sans Tamil recommended). Adjust sizes to taste.
        if font_path is None:
            # try common Windows Tamil font fallback - better to supply NotoSansTamil path
            font_path = r"C:\Windows\Fonts\Nirmala.ttf"  # fallback
        # base sizes scaled by DPI/96
        scale = dpi_x / 96.0
        title_size = int(22 * scale)
        header_size = int(16 * scale)
        normal_size = int(14 * scale)
        small_size = int(12 * scale)

        title_font = ImageFont.truetype(font_path, title_size)
        header_font = ImageFont.truetype(font_path, header_size)
        normal_font = ImageFont.truetype(font_path, normal_size)
        small_font = ImageFont.truetype(font_path, small_size)

        # --- Build text lines and estimate height ---
        # column allocation (percent of content width) — tweak if needed
        name_px  = int(content_w * 0.56)
        qty_px   = int(content_w * 0.10)
        mrp_px   = int(content_w * 0.10)
        rate_px  = int(content_w * 0.12)
        total_px = content_w - (name_px + qty_px + mrp_px + rate_px)

        # helper to split text into up to n lines that fit px width
        def split_to_lines(text, font, max_px, max_lines=2, ellipsis='...'):
            lines = []
            cur = ''
            for ch in text:
                w = font.getsize(cur + ch)[0]
                if w <= max_px:
                    cur += ch
                else:
                    lines.append(cur)
                    cur = ch
                    if len(lines) >= max_lines:
                        break
            if cur and len(lines) < max_lines:
                lines.append(cur)
            # if text not fully consumed, ellipsize last line
            consumed = ''.join(lines)
            if len(consumed) < len(text):
                last = lines[-1] if lines else ''
                # trim last until fits with ellipsis
                while last and font.getsize(last + ellipsis)[0] > max_px:
                    last = last[:-1]
                lines[-1] = (last + ellipsis) if last else ellipsis
            # ensure length == max_lines
            while len(lines) < max_lines:
                lines.append('')
            return lines[:max_lines]

        # build content height estimate
        line_height = max(normal_font.getsize("ப")[1], header_font.getsize("ப")[1]) + int(4 * scale)
        prelim_lines = 8  # header + separators estimate
        for it in items_data:
            pname = str(it.get('product_name', '') or '')
            name_lines = split_to_lines(pname, normal_font, name_px, max_lines=2)
            prelim_lines += len([l for l in name_lines if l.strip()]) or 1
            prelim_lines += 1  # numeric row or separator

        estimated_h = margin_px*2 + prelim_lines * line_height + 300  # add footer safety margin
        # create white image
        img = Image.new("RGB", (printable_w, estimated_h), "white")
        draw = ImageDraw.Draw(img)

        # vertical cursor
        y = margin_px

        # draw centered title block
        title = "SRI VELAVAN SUPERMARKET"
        w_title = draw.textsize(title, font=title_font)[0]
        draw.text(((printable_w - w_title)//2, y), title, font=title_font, fill="black")
        y += title_font.getsize(title)[1] + int(6*scale)

        for line in ["2/136A, Pillaiyar Koil Street", "A.Kottarakuppam, Virudhachalam", "Ph: 9626475471  GST:33FLEPM3791Q1ZD"]:
            w_line = draw.textsize(line, font=header_font)[0]
            draw.text(((printable_w - w_line)//2, y), line, font=header_font, fill="black")
            y += header_font.getsize(line)[1] + int(2*scale)

        # separator
        draw.line((margin_px, y, printable_w - margin_px, y), fill="black")
        y += int(6*scale)

        # meta
        meta1 = f"பில் எண் : {bill_data.get('bill_number','')}"
        meta2 = f"தேதி     : {bill_data.get('date','')} {bill_data.get('time','')}"
        draw.text((margin_px, y), meta1, font=normal_font, fill="black")
        y += normal_font.getsize(meta1)[1] + int(2*scale)
        draw.text((margin_px, y), meta2, font=normal_font, fill="black")
        y += normal_font.getsize(meta2)[1] + int(6*scale)

        # table header
        # draw header titles aligned to their columns; numbers right aligned
        def draw_right(text, right_x, top_y, font):
            w = draw.textsize(text, font=font)[0]
            draw.text((right_x - w, top_y), text, font=font, fill="black")

        draw.text((margin_px, y), "பொருள்", font=header_font, fill="black")
        draw_right("அளவு", margin_px + name_px + qty_px - 4, y, header_font)
        draw_right("MRP", margin_px + name_px + qty_px + mrp_px - 4, y, header_font)
        draw_right("விலை", margin_px + name_px + qty_px + mrp_px + rate_px - 4, y, header_font)
        draw_right("தொகை", margin_px + name_px + qty_px + mrp_px + rate_px + total_px - 4, y, header_font)
        y += header_font.getsize("அ")[1] + int(6*scale)
        draw.line((margin_px, y, printable_w - margin_px, y), fill="black")
        y += int(4*scale)

        # items
        for it in items_data:
            pname = str(it.get('product_name','') or '')
            qty = str(int(it.get('quantity',0)) if float(it.get('quantity',0)).is_integer() else it.get('quantity',0))
            mrp = f"{float(it.get('mrp',0)):.2f}"
            rate = f"{float(it.get('retail_price',0)):.2f}"
            tot = f"{float(it.get('total_price',0)):.2f}"
            name_lines = split_to_lines(pname, normal_font, name_px, max_lines=2)
            # first line: draw name and numbers
            draw.text((margin_px, y), name_lines[0], font=normal_font, fill="black")
            draw_right(qty, margin_px + name_px + qty_px - 4, y, normal_font)
            draw_right(mrp, margin_px + name_px + qty_px + mrp_px - 4, y, normal_font)
            draw_right(rate, margin_px + name_px + qty_px + mrp_px + rate_px - 4, y, normal_font)
            draw_right(tot, margin_px + name_px + qty_px + mrp_px + rate_px + total_px - 4, y, normal_font)
            y += line_height

            # possible second line of product name
            if name_lines[1].strip():
                draw.text((margin_px, y), name_lines[1], font=normal_font, fill="black")
                y += line_height

            # small separator
            draw.line((margin_px, y, printable_w - margin_px, y), fill="black")
            y += int(4*scale)

        # footer totals
        y += int(6*scale)
        draw.line((margin_px, y, printable_w - margin_px, y), fill="black")
        y += int(6*scale)
        totals = [
            f"மொத்த பொருட்கள் : {bill_data.get('total_unique_products',0)}",
            f"மொத்தம்        : ₹{float(bill_data.get('subtotal',0)):.2f}",
            f"சேமிப்பு       : ₹{float(bill_data.get('total_savings',0)):.2f}"
        ]
        for t in totals:
            draw.text((margin_px, y), t, font=header_font, fill="black")
            y += header_font.getsize(t)[1] + int(4*scale)

        if bill_data.get('customer_mobile') and bill_data.get('customer_mobile') != 'N/A':
            draw.text((margin_px, y), f"பழைய நிலுவை    : ₹{float(bill_data.get('old_balance',0)):.2f}", font=normal_font, fill="black")
            y += normal_font.getsize("ப")[1] + int(2*scale)
            draw.text((margin_px, y), f"புதிய நிலுவை   : ₹{float(bill_data.get('new_balance',0)):.2f}", font=normal_font, fill="black")
            y += normal_font.getsize("ப")[1] + int(4*scale)

        draw.text((margin_px, y), "நன்றி! மீண்டும் வாருங்கள்!", font=header_font, fill="black")
        y += header_font.getsize("ப")[1] + int(6*scale)

        # crop to actual content height
        final_h = min(img.height, max(margin_px*2 + 50, int(y + margin_px)))
        img = img.crop((0, 0, printable_w, final_h))

        # --- Send image to printer using Win32 DC + ImageWin.Dib ---
        hDC.StartDoc("Supermarket Bill (image)")
        hDC.StartPage()

        dib = ImageWin.Dib(img)
        # Draw the image top-left at (0,0) in device coordinates
        dib.draw(hDC.GetHandleOutput(), (0, 0, printable_w, final_h))

        hDC.EndPage()
        hDC.EndDoc()
        try:
            hDC.DeleteDC()
        except Exception:
            pass

    except Exception as e:
        # Re-raise so caller (route) can log/fallback
        raise


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

        # totals (robust conversions)
        total_items = sum(int(float(item.get('quantity', 0))) for item in data['items'])
        total_unique_products = len(data['items'])
        subtotal = sum(float(item.get('retail_price', 0)) * float(item.get('quantity', 0)) for item in data['items'])
        total_savings = sum((float(item.get('mrp', 0)) - float(item.get('retail_price', 0))) * float(item.get('quantity', 0)) for item in data['items'])
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

        new_debt = float(data.get('balance', {}).get('new_debt', 0) or 0)
        settle_debt = float(data.get('balance', {}).get('settle_debt', 0) or 0)
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
            qty = float(item.get('quantity', 0) or 0)
            items_data.append({
                'bill_number': bill_number,
                'product_name': display_name,
                'quantity': qty,
                'unit': item.get('unit', 'count'),
                'mrp': float(item.get('mrp', 0) or 0),
                'retail_price': float(item.get('retail_price', 0) or 0),
                'total_price': float(item.get('retail_price', 0) or 0) * qty
            })

        if not save_bill(bill_data, items_data):
            return jsonify({'error': 'Failed to save bill'}), 500

        bill_string = generate_bill_string(bill_data, customer_data, items_data)

        # Printing section using Win32 DC with pixel-perfect columns
                # Printing: try image-based raster print first (best for Tamil + exact alignment).
        # If image printing fails, fall back to the Text/DC-based printer.
        # Make sure BILL_FONT_PATH points to a Tamil-capable TTF (NotoSansTamil recommended).
        try:
            print_bill_image(
                bill_data=bill_data,
                items_data=items_data,
                customer_data=customer_data,
                printer_name=BILL_PRINTER_NAME,
                font_path=os.environ.get('BILL_FONT_PATH', r"Fonts\nirmala-ui-bold.ttf")
            )
            print("Printed bill (image) to", BILL_PRINTER_NAME)
        except Exception as e_img:
            print("Image print failed:", e_img)
            # Fallback to text-DC strong printer (existing implementation)
            try:
                print_bill_strong(bill_data, items_data, customer_data, BILL_PRINTER_NAME)
                print("Printed bill (text/DC) to", BILL_PRINTER_NAME)
            except Exception as e_txt:
                print("Fallback text/DC print failed:", e_txt)



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