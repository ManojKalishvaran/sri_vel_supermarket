"""pip install googletrans==4.0.0-rc1
pip install legacy-cgi
pip install flask
"""

from flask import Flask, render_template, request, redirect, session, jsonify
import sqlite3, uuid, datetime
from googletrans import Translator   # pip install googletrans==4.0.0-rc1
import uuid, base64
# translit_phoneme_pipeline_improved.py
import re
from g2p_en import G2p
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

g2p = G2p()


app = Flask(__name__)
app.secret_key = "super_secret_key"
DB_NAME = "Data/products.db"
translator = Translator()


# --- Improved vowel diacritics (for consonant+vowel composition) ---
VOWEL_SIGN = {
    # ARPAbet -> Tamil vowel sign (diacritic, appended after consonant base without virama)
    "AA": "ா",   # long a as diacritic
    "AE": "ெ",   # short e (diacritic placed before sound but we append it; rendering is handled by font)
    "AH": "",    # schwa / implicit vowel -> no diacritic
    "AO": "ொ",   # o (short) -> use ஒ diacritic form (works for many cases)
    "AW": "ாவ்",  # diphthong approximations
    "AY": "ை",   # ai diphthong
    "EH": "ெ",
    "ER": "ர்",  # r-colored vowel -> use explicit ர் (heuristic)
    "EY": "ே",
    "IH": "ி",
    "IY": "ீ",
    "OW": "ோ",   # long o
    "OY": "ொய்",
    "UH": "ு",
    "UW": "ூ",
}

# --- Independent vowels for word-initial vowels (full letters) ---
INDEPENDENT_VOWEL = {
    "AA": "ஆ", "AE": "எ", "AH": "அ", "AO": "ஒ", "AW": "அவ்",
    "AY": "ஐ", "EH": "எ", "ER": "அர்", "EY": "ஏ",
    "IH": "இ", "IY": "ஈ", "OW": "ஓ", "OY": "ஐ",
    "UH": "உ", "UW": "ஊ",
}

# --- Consonant base forms (with virama-like form removed for composition convenience) ---
# We'll keep the canonical consonant (without an explicit trailing virama) so we can add diacritics.
CONSONANT_BASE = {
    "P": "ப", "B": "ப", "T": "ட", "D": "ட",
    "K": "க", "G": "க", "CH": "ச", "JH": "ஜ",
    "F": "ஃப்", "V": "வ", "TH": "த", "DH": "த",
    "S": "ஸ்", "Z": "ஸ்", "SH": "ஷ", "ZH": "ஷ",
    "HH": "ஹ", "M": "ம", "N": "ன", "NG": "ங",
    "L": "ல", "R": "ர", "Y": "ய", "W": "வ",
}

# final-consonant marker (virama) to show consonant-ending when no vowel follows
VIRAMA = "்"


def normalize_phone(tok: str) -> str:
    tok = re.sub(r'\d', '', tok)
    tok = re.sub(r'[^A-Za-z]', '', tok)
    return tok.upper()

def compose_cons_vowel(cons_base: str, vowel_code: str) -> str:
    """
    cons_base: consonant glyph without virama (e.g. 'க')
    vowel_code: ARPAbet code (e.g. 'IH', 'AH', None)
    returns: combined syllable (e.g. 'கி', 'கா', 'க்' if final)
    """
    if vowel_code is None or vowel_code == "AH":  # implicit schwa -> treat as final consonant with virama
        return cons_base + VIRAMA
    vsign = VOWEL_SIGN.get(vowel_code, "")
    if not vsign:  # unknown vowel -> keep consonant + virama
        return cons_base + VIRAMA
    # Many vowel signs in Tamil render correctly when appended after the consonant base,
    # even if their visual placement is before the consonant in Unicode rendering.
    return cons_base + vsign

def eng_to_tamil_g2p_better(eng: str) -> str:
    if not eng:
        return ""

    raw = g2p(eng)
    words = []
    cur = []
    for tok in raw:
        if tok == " ":
            if cur:
                words.append(cur)
            cur = []
        else:
            n = normalize_phone(tok)
            if n == "":
                continue
            cur.append(n)
    if cur:
        words.append(cur)

    tamil_words = []
    unknown = set()

    for w in words:
        i = 0
        tam = ""
        # If first phone is vowel -> independent vowel
        if i < len(w) and w[0] in INDEPENDENT_VOWEL:
            tam += INDEPENDENT_VOWEL[w[0]]
            i = 1
        while i < len(w):
            phone = w[i]
            # vowel-only inside word -> attach to previous consonant if possible, else independent
            if phone in VOWEL_SIGN:
                if tam and tam[-1] not in (VIRAMA,):  # previous likely a consonant base or already combined
                    # naive heuristic: append vowel sign to last consonant cluster if possible
                    # find last consonant base index:
                    # simple: just append sign (since consonant base stored without virama earlier)
                    tam += VOWEL_SIGN[phone]
                else:
                    tam += INDEPENDENT_VOWEL.get(phone, "")
                i += 1
                continue

            # consonant handling
            if phone in CONSONANT_BASE:
                cons = CONSONANT_BASE[phone]
                next_p = w[i+1] if i+1 < len(w) else None
                if next_p and next_p in VOWEL_SIGN:
                    tam_piece = compose_cons_vowel(cons, next_p)
                    tam += tam_piece
                    i += 2
                else:
                    # final consonant (no following vowel)
                    tam += cons + VIRAMA
                    i += 1
                continue

            # fallback
            unknown.add(phone)
            # fallback: transliterate raw phone token letters (best-effort)
            fb = transliterate(phone, sanscript.ITRANS, sanscript.TAMIL)
            tam += fb
            i += 1

        # postprocess: collapse repeated virama+consonant clusters into geminates if pattern matches
        # simple replacements for common geminates:
        tam = re.sub(r'ன்' + VIRAMA + r'ன', 'ன்ன', tam)  # n + n -> ன்ன
        tam = re.sub(r'ட்' + VIRAMA + r'ட', 'ட்ட', tam)
        tamil_words.append(tam)

    tamil = " ".join(tamil_words)
    tamil = re.sub(r'\s+', ' ', tamil).strip()
    # (in production, log `unknown` so you can expand maps)
    return tamil



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
    return render_template("index2.html", temp_products=session["temp_products"])


@app.route('/delete_temp/<barcode>', methods=['POST'])
def delete_temp(barcode):
    if "temp_products" in session:
        # compare as strings to avoid int/string mismatch
        session["temp_products"] = [
            p for p in session["temp_products"]
            if str(p.get("barcode")) != str(barcode)
        ]
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


# --- add_temp endpoint (paste replacing existing add_temp) ---
@app.route('/add_temp', methods=['POST'])
def add_temp():
    name = request.form["name"].capitalize()
    print("Temporary product adding...")
    print(f"{name = }")
    # choose which tamil-name generator to use:
    use_g2p = request.form.get("use_g2p")  # returns 'on' if checkbox checked, otherwise None
    if not use_g2p:
        try:
            tamil_name = eng_to_tamil_g2p_better(name)
        except Exception as e:
            # fallback to translator if g2p fails
            print(f"g2p failed: {e}; falling back to google translate")
            try:
                tamil_name = translator.translate(name, src='en', dest='ta').text
            except Exception as ex:
                print(f"google translate fallback failed: {ex}")
                tamil_name = name
    else:
        # default path: use googletrans translator
        try:
            tamil_name = translator.translate(name, src='en', dest='ta').text
        except Exception as e:
            print(f"translation failed, falling back to english: {e}")
            tamil_name = name

    measure = request.form["measure"]
    quantity = float(request.form["quantity"])
    mrp = float(request.form["mrp"])
    retail_price = float(request.form["retail_price"])

    timestamp = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")

    new = datetime.datetime.now()
    barcode = new.strftime("%Y%m%d%H%M%S")
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


# --- add_by_barcode endpoint (paste replacing existing add_by_barcode) ---
@app.route('/add_by_barcode', methods=['POST'])
def add_by_barcode():
    """
    New endpoint: accepts barcode from scanner/input and rest of the product fields.
    Per user requirement, tamil_name is created from english name "as it is" (no translation) unless g2p requested.
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

    name_cap = name.capitalize()

    # Decide which tamil-name generator to use
    use_g2p = request.form.get("use_g2p")
    if not use_g2p:
        try:
            tamil_name = eng_to_tamil_g2p_better(name_cap)
        except Exception as e:
            print(f"g2p failed for barcode add: {e}; falling back to google translate")
            try:
                tamil_name = translator.translate(name_cap, src='en', dest='ta').text
            except Exception as ex:
                print(f"google translate fallback failed: {ex}")
                tamil_name = name_cap
    else:
        try:
            tamil_name = translator.translate(name_cap, src='en', dest='ta').text
        except Exception as e:
            print(f"translation failed, falling back to english: {e}")
            tamil_name = name_cap

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
    existing = [p for p in session["temp_products"] if str(p.get("barcode")) == str(barcode)]
    if existing:
        session["temp_products"] = [p for p in session["temp_products"] if str(p.get("barcode")) != str(barcode)]
        session["temp_products"].append(product)

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
    return render_template("index2.html", temp_products=session.get("temp_products", []), results=results, search_query=query)


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
    app.run(debug=True, port=5001)
