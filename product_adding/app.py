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

    # Translate English -> Tamil
    try:
        tamil_name = translator.translate(name, src='en', dest='ta').text
    except Exception as e:
        tamil_name = name  # fallback if translation fails

    measure = request.form["measure"]
    quantity = float(request.form["quantity"])
    mrp = float(request.form["mrp"])
    retail_price = float(request.form["retail_price"])

    u = uuid.uuid4()

    # Base64 encode to shorten (22 chars instead of 36)
    barcode = base64.urlsafe_b64encode(u.bytes).rstrip(b' ').decode('ascii')
    # print("Short UUID:", short_id, "Length:", len(short_id))

    # barcode = str(uuid.uuid4())
    timestamp = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

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


if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)

