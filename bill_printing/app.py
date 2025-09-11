# app.py (updated)
from flask import Flask, render_template, request, jsonify
import sqlite3
import os
from datetime import datetime
import textwrap
import win32print
import win32ui
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
    """Initialize SQLite databases with required tables"""
    # Initialize customers database
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

    # Initialize bills database
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
    """Get customer details by mobile number from SQLite database"""
    try:
        conn = sqlite3.connect(CUSTOMERS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT mobile, name, address, points, balance FROM customers WHERE mobile = ?', (mobile,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'mobile': row[0],
                'name': row[1],
                'address': row[2] or '',
                'points': float(row[3] or 0),
                'balance': float(row[4] or 0)
            }
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    return None

def create_customer(mobile, name, address=''):
    """Create new customer with 0 balance and points"""
    try:
        conn = sqlite3.connect(CUSTOMERS_DB)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO customers (mobile, name, address, points, balance)
            VALUES (?, ?, ?, 0, 0)
        ''', (mobile, name, address))
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def update_customer(customer_data):
    """Update or create customer in SQLite database"""
    try:
        conn = sqlite3.connect(CUSTOMERS_DB)
        cursor = conn.cursor()

        # Check if customer exists
        cursor.execute('SELECT mobile FROM customers WHERE mobile = ?', (customer_data['mobile'],))
        exists = cursor.fetchone()

        if exists:
            # Update existing customer
            cursor.execute('''
                UPDATE customers 
                SET name = ?, address = ?, points = ?, balance = ?
                WHERE mobile = ?
            ''', (customer_data['name'], customer_data['address'],
                  customer_data['points'], customer_data['balance'], customer_data['mobile']))
        else:
            # Create new customer
            cursor.execute('''
                INSERT INTO customers (mobile, name, address, points, balance)
                VALUES (?, ?, ?, ?, ?)
            ''', (customer_data['mobile'], customer_data['name'], customer_data['address'],
                  customer_data['points'], customer_data['balance']))

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def get_product_by_barcode(barcode):
    """Get product details by barcode from products.db"""
    try:
        conn = sqlite3.connect(PRODUCTS_DB)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, tamil_name, measure, mrp, retail_price 
            FROM products WHERE barcode = ?
        ''', (barcode,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'name': row[1] if row[1] else row[0],  # Prefer Tamil name
                'measure': row[2],
                'mrp': float(row[3]),
                'retail_price': float(row[4])
            }
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    return None

def get_product_by_name(name):
    """Get product details by name from products.db"""
    try:
        conn = sqlite3.connect(PRODUCTS_DB)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, tamil_name, measure, mrp, retail_price 
            FROM products WHERE name LIKE ? OR tamil_name LIKE ?
        ''', (f'%{name}%', f'%{name}%'))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                'name': row[1] if row[1] else row[0],  # Prefer Tamil name
                'measure': row[2],
                'mrp': float(row[3]),
                'retail_price': float(row[4])
            }
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    return None

def get_product_list():
    """Get list of all product names from products.db"""
    try:
        conn = sqlite3.connect(PRODUCTS_DB)
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT tamil_name, name FROM products')
        rows = cursor.fetchall()
        conn.close()

        products = []
        for row in rows:
            # Add Tamil name if available, otherwise use English name
            if row[0]:
                products.append(row[0])
            else:
                products.append(row[1])
        return sorted(list(set(products)))  # Remove duplicates and sort
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []

def save_bill(bill_data, items_data):
    """Save bill and items to SQLite database"""
    try:
        conn = sqlite3.connect(BILLS_DB)
        cursor = conn.cursor()

        # Save bill
        cursor.execute('''
            INSERT INTO bills (
                bill_number, customer_mobile, date, time, total_items, 
                total_unique_products, subtotal, total_savings, payment_type, 
                cash_received, cash_balance, old_balance, new_balance, points_earned
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            bill_data['bill_number'], bill_data['customer_mobile'], bill_data['date'],
            bill_data['time'], bill_data['total_items'], bill_data['total_unique_products'],
            bill_data['subtotal'], bill_data['total_savings'], bill_data['payment_type'],
            bill_data['cash_received'], bill_data['cash_balance'], bill_data['old_balance'],
            bill_data['new_balance'], bill_data['points_earned']
        ))

        # Save bill items
        for item in items_data:
            cursor.execute('''
                INSERT INTO bill_items (
                    bill_number, product_name, quantity, unit, mrp, retail_price, total_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                item['bill_number'], item['product_name'], item['quantity'],
                item['unit'], item['mrp'], item['retail_price'], item['total_price']
            ))

        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

def format_thermal_bill(items, width=38):
    header = f"{'Item':<18}{'Qty':>4}{'Rate':>8}{'Total':>8}"
    line_sep = '=' * width
    lines = [line_sep, header, line_sep]

    for item in items:
        # Wrap name to width of about 18 chars
        name_lines = textwrap.wrap(item['product_name'], width=18) or ['']
        qty = str(item['quantity']).rjust(4)
        rate = f"{float(item['retail_price']):.2f}".rjust(8)
        total = f"{float(item['total_price']):.2f}".rjust(8)

        # First line: product name + data
        lines.append(f"{name_lines[0]:<18}{qty}{rate}{total}")

        # Remaining name lines (if any): just the name
        for extra_line in name_lines[1:]:
            lines.append(f"{extra_line:<18}")
        lines.append('-' * width)

    return '\n'.join(lines)

def generate_bill_string(bill_data, customer_data, items_data):
    WIDTH = 38  # For 58mm printer
    SEP = '_' * WIDTH
    SEP2 = '-' * WIDTH

    # Header centered with minimal padding
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
    # Only show mobile if provided
    if customer_data.get('mobile') and customer_data.get('mobile') != 'N/A':
        bill_string += f"மொபைல்  : {customer_data['mobile']}\n"
        bill_string += f"புள்ளிகள்: {customer_data.get('points', 0)}\n"
    bill_string += SEP2 + '\n'

    bill_box = format_thermal_bill(items_data, WIDTH)
    bill_string += bill_box + '\n'

    bill_string += SEP2 + '\n'
    bill_string += f"மொத்த பொருட்கள் : {bill_data['total_unique_products']}\n"
    bill_string += f"மொத்த அளவு     : {bill_data['total_items']}\n"
    bill_string += f"மொத்தம்        : ₹{bill_data['subtotal']:.2f}\n"
    bill_string += f"சேமிப்பு       : ₹{bill_data['total_savings']:.2f}\n"

    # Only show old/new balance when customer mobile exists
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

    # strip any leading/trailing blank lines
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
    """Create new customer immediately when not found"""
    try:
        data = request.json
        mobile = data.get('mobile')
        name = data.get('name')
        address = data.get('address', '')

        if not mobile or not name:
            return jsonify({'error': 'Mobile and name are required'}), 400

        # Create customer with 0 balance and points
        customer_data = {
            'mobile': mobile,
            'name': name,
            'address': address,
            'points': 0,
            'balance': 0
        }

        if update_customer(customer_data):
            return jsonify({
                'success': True,
                'customer': customer_data,
                'message': 'New customer created successfully'
            })
        else:
            return jsonify({'error': 'Failed to create customer'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_product_by_barcode/<barcode>')
def get_product_by_barcode_route(barcode):
    product = get_product_by_barcode(barcode)
    if product:
        return jsonify({
            'success': True,
            'product': product
        })
    return jsonify({'success': False, 'error': 'Product not found'})

@app.route('/get_product_by_name/<name>')
def get_product_by_name_route(name):
    product = get_product_by_name(name)
    if product:
        return jsonify({
            'success': True,
            'product': product
        })
    return jsonify({'success': False, 'error': 'Product not found'})

@app.route('/update_balance', methods=['POST'])
def update_balance():
    """Update customer balance"""
    try:
        data = request.json
        mobile = data.get('mobile')
        new_balance = float(data.get('balance', 0))

        customer = get_customer(mobile)
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404

        # Update balance
        customer['balance'] = new_balance
        if update_customer(customer):
            return jsonify({
                'success': True,
                'message': 'Balance updated successfully',
                'customer': customer
            })
        else:
            return jsonify({'error': 'Failed to update balance'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/get_products')
def get_products():
    """Get list of all products"""
    products = get_product_list()
    return jsonify({'products': products})

@app.route('/today_totals')
def today_totals():
    """Return total items sold today and total sales amount"""
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

        # Generate bill number
        bill_number = f"INV{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Get current date and time
        now = datetime.now()
        current_date = now.strftime('%d/%m/%Y')
        current_time = now.strftime('%H:%M:%S')

        # Calculate totals
        total_items = sum(int(item['quantity']) for item in data['items'])
        total_unique_products = len(data['items'])
        subtotal = sum(float(item['retail_price']) * int(item['quantity']) for item in data['items'])
        total_savings = sum((float(item['mrp']) - float(item['retail_price'])) * int(item['quantity']) for item in data['items'])

        # Calculate points (1 point per Rs 100)
        points_earned = int(subtotal // 100)

        # Get or create customer data
        customer = None
        old_balance = 0
        old_points = 0

        if data['customer']['mobile']:
            customer = get_customer(data['customer']['mobile'])
            if customer:
                old_balance = customer['balance']
                old_points = customer['points']
            else:
                # Create new customer immediately
                create_customer(data['customer']['mobile'], data['customer']['name'], data['customer']['address'])
                customer = get_customer(data['customer']['mobile'])
                if customer:
                    old_balance = customer['balance']
                    old_points = customer['points']

        # Calculate new balance based on debt management
        new_debt = float(data['balance'].get('new_debt', 0))
        settle_debt = float(data['balance'].get('settle_debt', 0))

        new_balance = old_balance
        new_balance = old_balance + new_debt - settle_debt

        # Handle payment
        cash_received = float(data['payment']['cash_received']) if data['payment']['cash_received'] else 0
        cash_balance = cash_received - subtotal

        # If cash_balance negative => customer still owes money -> add to new_balance
        new_balance = new_balance + abs(cash_balance) if cash_balance < 0 else new_balance

        # Update customer data if mobile provided
        if data['customer']['mobile']:
            customer_data = {
                'mobile': data['customer']['mobile'],
                'name': data['customer']['name'],
                'address': data['customer']['address'],
                'points': old_points + points_earned,
                'balance': new_balance
            }
            update_customer(customer_data)
        else:
            customer_data = {
                'mobile': 'N/A',
                'name': 'பதிவில்லா வாடிக்கையாளர்',
                'address': '-',
                'points': 0,
                'balance': 0
            }

        # Prepare bill data
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

        # Prepare items data
        items_data = []
        for item in data['items']:
            items_data.append({
                'bill_number': bill_number,
                'product_name': item['name'],
                'quantity': item['quantity'],
                'unit': item.get('unit', 'count'),
                'mrp': item['mrp'],
                'retail_price': item['retail_price'],
                'total_price': float(item['retail_price']) * int(item['quantity'])
            })

        # Save to database
        if save_bill(bill_data, items_data):
            # Generate bill string
            bill_string = generate_bill_string(bill_data, customer_data, items_data)

            # Print bill automatically (try/catch; if fails simply return bill_string)
            try:
                receipt_text = bill_string
                printer_name = win32print.GetDefaultPrinter()
                hDC = win32ui.CreateDC()
                hDC.CreatePrinterDC(printer_name)
                hDC.StartDoc("Supermarket Bill")
                hDC.StartPage()

                # Create and select a font - measured line height will be taken from GetTextExtent
                # Use a small fixed-pitch font (Courier) for receipts
                font = win32ui.CreateFont({
                    "name": "Courier New",
                    "height": 18,     # font height in logical units; tweak if needed
                    "weight": 400,
                })
                hDC.SelectObject(font)

                y = 100
                x = 50

                # Use measured height for each line to avoid overlapping
                for raw_line in receipt_text.split("\n"):
                    line = raw_line.rstrip()
                    try:
                        # Ensure unicode text is passed
                        hDC.TextOut(x, y, line)
                        size = hDC.GetTextExtent(line)
                        line_height = size[1] + 4  # small padding
                        y += line_height
                    except pywintypes.error as texterr:
                        # If a particular line causes error, try safe fallback
                        try:
                            hDC.TextOut(x, y, line.encode('ascii', errors='replace').decode('ascii'))
                            size = hDC.GetTextExtent(line[:40])
                            y += size[1] + 4
                        except Exception:
                            y += 20

                hDC.EndPage()
                hDC.EndDoc()
                hDC.DeleteDC()
            except Exception as print_error:
                # Keep process running even if printing fails; log error
                print(f"Print error: {print_error}")

            return jsonify({
                'success': True,
                'bill_number': bill_number,
                'bill_string': bill_string,
                'customer_data': customer_data
            })
        else:
            return jsonify({'error': 'Failed to save bill'}), 500

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    init_databases()
    app.run(debug=True, port=5002)
