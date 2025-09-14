"""pip install googletrans==4.0.0-rc1
pip install legacy-cgi
pip install flask
"""

from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, uuid, datetime
from googletrans import Translator   # pip install googletrans==4.0.0-rc1
import uuid, base64

app = Flask(__name__)
app.secret_key = "super_secret_key"
DB_NAME = "Data/products.db"
translator = Translator()

# ---------- CREATE DB ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            barcode TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            tamil_name TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            measure TEXT NOT NULL,
            quantity REAL NOT NULL,
            mrp REAL NOT NULL,
            retail_price REAL NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

@app.route('/')
def home():
    if "temp_products" not in session:
        session["temp_products"] = []
    return render_template("index.html", temp_products=session["temp_products"])

@app.route('/delete_temp/<barcode>', methods=['POST'])
def delete_temp(barcode):
    if "temp_products" in session:
        session["temp_products"] = [p for p in session["temp_products"] if p["barcode"] != barcode]
        session.modified = True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True), 200

    return redirect('/')

@app.route("/api/all_products")
def api_all_products():
    """Return full product list as JSON."""
    try:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT barcode, name, tamil_name, measure, quantity, mrp, retail_price
            FROM products
            ORDER BY name
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return jsonify(rows)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/add_temp', methods=['POST'])
def add_temp():
    name = request.form["name"].capitalize()

    # Translate English -> Tamil using googletrans (legacy behavior)
    try:
        
        tamil_name = translator.translate(name, src='en', dest='ta').text
        print(f"to tamil {tamil_name}")
    except Exception as e:
        print(f"falling back to english{e}")
        tamil_name = name  # fallback if translation fails

    measure = request.form["measure"]
    quantity = float(request.form["quantity"])
    mrp = float(request.form["mrp"])
    retail_price = float(request.form["retail_price"])


    timestamp = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    new = datetime.datetime.now()
    barcode = int(new.strftime("%Y%m%d%H%M%S"))
    product = {
        "barcode": barcode,
        "name": name,
        "tamil_name": tamil_name,
        "timestamp": timestamp,
        "measure": measure,
        "quantity": quantity,
        "mrp": mrp,
        "retail_price": retail_price
    }

    if "temp_products" not in session:
        session["temp_products"] = []
    session["temp_products"].append(product)
    session.modified = True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True, product=product), 200

    return redirect('/')


@app.route('/add_by_barcode', methods=['POST'])
def add_by_barcode():
    """
    New endpoint: accepts barcode from scanner/input and rest of the product fields.
    Per user requirement, tamil_name is created from english name "as it is" (no translation).
    """
    # Basic validation
    barcode = request.form.get("barcode", "").strip()
    name = request.form.get("name", "").strip()
    measure = request.form.get("measure", "").strip()
    q = request.form.get("quantity", "").strip()
    mrp = request.form.get("mrp", "").strip()
    retail_price = request.form.get("retail_price", "").strip()

    if not (barcode and name and measure and q and mrp and retail_price):
        # If AJAX/XHR expect JSON error, otherwise redirect
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=False, error="Missing required fields"), 400
        return redirect('/')

    try:
        quantity = float(q)
        mrp_f = float(mrp)
        retail_price_f = float(retail_price)
    except ValueError:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(ok=False, error="Invalid numeric values"), 400
        return redirect('/')

    # Use english name as tamil name "as it is" per requirement
    name_cap = name.capitalize()
    # tamil_name = name_cap
    tamil_name = translator.translate(name_cap, src='en', dest='ta').text

    timestamp = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    product = {
        "barcode": barcode,
        "name": name_cap,
        "tamil_name": tamil_name,
        "timestamp": timestamp,
        "measure": measure,
        "quantity": quantity,
        "mrp": mrp_f,
        "retail_price": retail_price_f
    }

    # ensure session list exists
    if "temp_products" not in session:
        session["temp_products"] = []

    # avoid duplicate barcode in temp list
    existing = [p for p in session["temp_products"] if p["barcode"] == barcode]
    if existing:
        # replace existing item with new data (keep idempotent)
        session["temp_products"] = [p for p in session["temp_products"] if p["barcode"] != barcode]
        session["temp_products"].append(product)
        session.modified = True
    else:
        session["temp_products"].append(product)
        session.modified = True

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify(ok=True, product=product), 200

    return redirect('/')


@app.route('/save_all', methods=['POST'])
def save_all():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    for p in session["temp_products"]:
        cursor.execute('''INSERT OR REPLACE INTO products 
            (barcode, name, tamil_name, timestamp, measure, quantity, mrp, retail_price) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (p["barcode"], p["name"], p["tamil_name"], p["timestamp"],
             p["measure"], p["quantity"], p["mrp"], p["retail_price"]))
    conn.commit()
    conn.close()
    session["temp_products"] = []
    return redirect('/')


@app.before_request
def clear_old_session():
    if "temp_products" in session:
        # clear if old schema found
        if session["temp_products"] and "mrp" not in session["temp_products"][0]:
            session["temp_products"] = []
            session.modified = True


@app.route("/search", methods=["GET", "POST"])
def search_products():
    query = request.args.get("q", "").strip()
    results = []
    if query:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM products 
            WHERE name LIKE ? OR tamil_name LIKE ? OR barcode LIKE ?
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
    return render_template("index.html", temp_products=session.get("temp_products", []), results=results, search_query=query)


@app.route("/api/search")
def api_search():
    query = request.args.get("q", "").strip()
    results = []
    if len(query) >= 2:  # only start after 2+ chars
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT barcode, name, tamil_name, measure, quantity, mrp, retail_price 
            FROM products
            WHERE name LIKE ? OR tamil_name LIKE ?
            ORDER BY name LIMIT 10
        """, (f"%{query}%", f"%{query}%"))
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
    return jsonify(results)


@app.route("/edit/<barcode>", methods=["POST"])
def edit_product(barcode):
    # legacy form-based edit for compatibility
    name = request.form["name"].capitalize()
    tamil_name = request.form["tamil_name"]
    measure = request.form["measure"]
    quantity = float(request.form["quantity"])
    mrp = float(request.form["mrp"])
    retail_price = float(request.form["retail_price"])

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products 
        SET name=?, tamil_name=?, measure=?, quantity=?, mrp=?, retail_price=? 
        WHERE barcode=?
    """, (name, tamil_name, measure, quantity, mrp, retail_price, barcode))
    conn.commit()
    conn.close()

    return redirect(f"/search?q={name}")

# ---------------- New JSON API endpoints for modal edit/delete ----------------
@app.route("/api/edit/<barcode>", methods=["POST"])
def api_edit(barcode):
    """AJAX-friendly edit endpoint. Accepts form-encoded fields and returns JSON."""
    try:
        name = request.form.get("name", "").strip()
        tamil_name = request.form.get("tamil_name", "").strip()
        measure = request.form.get("measure", "").strip()
        quantity = float(request.form.get("quantity", "0"))
        mrp = float(request.form.get("mrp", "0"))
        retail_price = float(request.form.get("retail_price", "0"))
    except Exception as e:
        return jsonify(ok=False, error="Invalid input"), 400

    if not name:
        return jsonify(ok=False, error="Name required"), 400

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE products 
        SET name=?, tamil_name=?, measure=?, quantity=?, mrp=?, retail_price=? 
        WHERE barcode=?
    """, (name.capitalize(), tamil_name, measure, quantity, mrp, retail_price, barcode))
    conn.commit()

    # return the updated row
    cursor.execute("SELECT barcode, name, tamil_name, measure, quantity, mrp, retail_price FROM products WHERE barcode=?", (barcode,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return jsonify(ok=False, error="Product not found"), 404

    product = {
        "barcode": row[0],
        "name": row[1],
        "tamil_name": row[2],
        "measure": row[3],
        "quantity": row[4],
        "mrp": row[5],
        "retail_price": row[6]
    }
    return jsonify(ok=True, product=product), 200

@app.route("/api/delete/<barcode>", methods=["POST"])
def api_delete(barcode):
    """AJAX-friendly delete."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE barcode=?", (barcode,))
    conn.commit()
    changed = cursor.rowcount
    conn.close()
    if changed:
        return jsonify(ok=True), 200
    else:
        return jsonify(ok=False, error="Product not found"), 404

# ---------------------------------------------------------------------------

@app.route("/api/search")
def api_search_dup():
    # Note: this duplicate isn't ideal but left for safety; actual earlier function is used.
    query = request.args.get("q", "").strip()
    results = []
    if len(query) >= 2:
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT barcode, name, tamil_name, measure, quantity, mrp, retail_price 
            FROM products
            WHERE name LIKE ? OR tamil_name LIKE ?
            ORDER BY name LIMIT 10
        """, (f"%{query}%", f"%{query}%"))
        results = [dict(row) for row in cursor.fetchall()]
        conn.close()
    return jsonify(results)

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
