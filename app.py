import os
import sqlite3
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, g
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "market.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "market-secret-key-change-in-production")

CATEGORIES = [
    ("electronic", "ئەلیکترۆنیان (Electronic)"),
    ("grocery", "کەرەبای و سەوزەوات (Groceries)"),
    ("construction", "بیناسازی (Construction)"),
    ("equipment", "کەلوپەل و ئامێر (Equipment)"),
    ("clothing", "جلوبەرگ (Clothing)"),
    ("furniture", "ئەثات و کەلوپەلی ناوماڵ (Furniture)"),
    ("beauty", "جوانکاری (Beauty)"),
    ("other", "هیتر (Other)"),
]

CATEGORY_LABELS = dict(CATEGORIES)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role          TEXT NOT NULL DEFAULT 'user',
            created_at    TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS shops (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL UNIQUE REFERENCES users(id),
            shop_name  TEXT NOT NULL,
            showroom   TEXT,
            company    TEXT,
            phone      TEXT,
            email      TEXT,
            category   TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );

        CREATE TABLE IF NOT EXISTS products (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id    INTEGER NOT NULL REFERENCES shops(id),
            name       TEXT NOT NULL,
            price      REAL NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        );
    """)
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
    cur = conn.execute("SELECT id FROM users WHERE role = 'admin'")
    if cur.fetchone() is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
            (admin_user, generate_password_hash(admin_pass)),
        )
    conn.commit()
    conn.close()


init_db()


# ---------- helpers ----------

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session or session.get("role") == "admin":
            flash("تکایە سەرەتا بچۆ ژوورەوە", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            flash("تەنها بەڕێوەبەر دەتوانێت بچێتە ژوورەوە", "error")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapper


def parse_price(value):
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price < 0:
        return None
    return price


def get_user_shop(db, user_id):
    return db.execute("SELECT * FROM shops WHERE user_id = ?", (user_id,)).fetchone()


def ensure_shop(db, user_id):
    shop = get_user_shop(db, user_id)
    if shop is None:
        cur = db.execute(
            "INSERT INTO shops (user_id, shop_name) VALUES (?, ?)",
            (user_id, request.form.get("shop_name", "فرۆشگاکەم")),
        )
        return db.execute("SELECT * FROM shops WHERE id = ?", (cur.lastrowid,)).fetchone()
    return shop


# ---------- public ----------

@app.route("/")
def index():
    db = get_db()
    stats = {
        "shops": db.execute("SELECT COUNT(*) AS c FROM shops").fetchone()["c"],
        "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
        "categories": len(CATEGORIES),
    }
    return render_template("index.html", stats=stats)


@app.route("/market")
def market():
    db = get_db()
    rows = db.execute("""
        SELECT p.id AS product_id, p.name AS name, p.price AS price,
               p.shop_id, s.shop_name, s.showroom, s.category
        FROM products p JOIN shops s ON p.shop_id = s.id
        ORDER BY p.name COLLATE NOCASE
    """).fetchall()
    return render_template("market.html", rows=rows, category_labels=CATEGORY_LABELS)


# ---------- auth ----------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        shop_name = request.form.get("shop_name", "").strip()
        showroom = request.form.get("showroom", "").strip()
        company = request.form.get("company", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        category = request.form.get("category", "")

        if not username or not password or not shop_name:
            flash("ناوی بەکارهێنەر، پاسورد و ناوی فرۆشگا زۆر پێویستن", "error")
            return redirect(url_for("register"))
        if password != confirm:
            flash("پاسۆردەکان یەک ناگرنەوە", "error")
            return redirect(url_for("register"))
        if len(password) < 4:
            flash("پاسورد دەبێت لانیکەم ٤ پیت بێت", "error")
            return redirect(url_for("register"))

        db = get_db()
        if db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone():
            flash("ئەم ناوە لەمەو پێش تۆمارکراوە", "error")
            return redirect(url_for("register"))

        pw_hash = generate_password_hash(password)
        cur = db.execute(
            "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'user')",
            (username, pw_hash),
        )
        db.execute(
            """INSERT INTO shops (user_id, shop_name, showroom, company, phone, email, category)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (cur.lastrowid, shop_name, showroom, company, phone, email, category),
        )
        db.commit()
        flash("تۆمارکردنت سەرکەوتوو بوو، ئێستا دەتوانیت بچیتە ژوورەوە", "success")
        return redirect(url_for("login"))

    return render_template("register.html", categories=CATEGORIES)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            if user["role"] == "admin":
                flash("بەخێربێیت بۆ داشبۆردی بەڕێوەبەر", "success")
                return redirect(url_for("admin_dashboard"))
            flash("بەخێربێیتەوە", "success")
            return redirect(url_for("dashboard"))
        flash("ناو یان پاسورد هەڵەیە", "error")
        return redirect(url_for("login"))
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("لە ژوورەوە چوویتە دەرەوە", "success")
    return redirect(url_for("index"))


# ---------- user dashboard ----------

@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    shop = ensure_shop(db, session["user_id"])
    db.commit()
    products = db.execute(
        "SELECT * FROM products WHERE shop_id = ? ORDER BY name COLLATE NOCASE",
        (shop["id"],),
    ).fetchall()
    return render_template(
        "dashboard.html",
        shop=shop,
        products=products,
        categories=CATEGORIES,
        category_labels=CATEGORY_LABELS,
    )


@app.route("/dashboard/shop", methods=["POST"])
@login_required
def update_shop():
    db = get_db()
    shop = ensure_shop(db, session["user_id"])
    shop_name = request.form.get("shop_name", "").strip()
    if not shop_name:
        flash("ناوی فرۆشگا پێویستە", "error")
        return redirect(url_for("dashboard"))
    db.execute(
        """UPDATE shops SET shop_name = ?, showroom = ?, company = ?, phone = ?,
           email = ?, category = ?, updated_at = datetime('now') WHERE id = ?""",
        (
            shop_name,
            request.form.get("showroom", "").strip(),
            request.form.get("company", "").strip(),
            request.form.get("phone", "").strip(),
            request.form.get("email", "").strip(),
            request.form.get("category", ""),
            shop["id"],
        ),
    )
    db.commit()
    flash("زانیاری فرۆشگاکەت نوێکرایەوە", "success")
    return redirect(url_for("dashboard"))


@app.route("/products/add", methods=["POST"])
@login_required
def add_product():
    name = request.form.get("name", "").strip()
    price = parse_price(request.form.get("price"))
    if not name:
        flash("ناوی کاڵا پێویستە", "error")
        return redirect(url_for("dashboard"))
    if price is None:
        flash("نرخەکە دروست نییە (دەبێت ژمارە بێت)", "error")
        return redirect(url_for("dashboard"))
    db = get_db()
    shop = ensure_shop(db, session["user_id"])
    db.execute(
        "INSERT INTO products (shop_id, name, price) VALUES (?, ?, ?)",
        (shop["id"], name, price),
    )
    db.commit()
    flash("کاڵاکە زیادی کرا", "success")
    return redirect(url_for("dashboard"))


@app.route("/products/update/<int:pid>", methods=["POST"])
@login_required
def update_product(pid):
    db = get_db()
    shop = ensure_shop(db, session["user_id"])
    product = db.execute(
        "SELECT * FROM products WHERE id = ? AND shop_id = ?", (pid, shop["id"])
    ).fetchone()
    if product is None:
        flash("کاڵاکە نەدۆزرایەوە", "error")
        return redirect(url_for("dashboard"))
    name = request.form.get("name", "").strip()
    price = parse_price(request.form.get("price"))
    if not name:
        flash("ناوی کاڵا پێویستە", "error")
        return redirect(url_for("dashboard"))
    if price is None:
        flash("نرخەکە دروست نییە (دەبێت ژمارە بێت)", "error")
        return redirect(url_for("dashboard"))
    db.execute(
        "UPDATE products SET name = ?, price = ?, updated_at = datetime('now') WHERE id = ?",
        (name, price, pid),
    )
    db.commit()
    flash("نرخی کاڵاکە نوێکرایەوە", "success")
    return redirect(url_for("dashboard"))


@app.route("/products/delete/<int:pid>", methods=["POST"])
@login_required
def delete_product(pid):
    db = get_db()
    shop = ensure_shop(db, session["user_id"])
    db.execute("DELETE FROM products WHERE id = ? AND shop_id = ?", (pid, shop["id"]))
    db.commit()
    flash("کاڵاکە سڕایەوە", "success")
    return redirect(url_for("dashboard"))


# ---------- admin ----------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username = ? AND role = 'admin'", (username,)
        ).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = "admin"
            flash("بەخێربێیت بۆ داشبۆردی بەڕێوەبەر", "success")
            return redirect(url_for("admin_dashboard"))
        flash("ناو یان پاسوردی بەڕێوەبەر هەڵەیە", "error")
        return redirect(url_for("admin_login"))
    return render_template("admin_login.html")


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    shops = db.execute("""
        SELECT s.*,
               (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id) AS product_count
        FROM shops s ORDER BY s.shop_name COLLATE NOCASE
    """).fetchall()
    stats = {
        "shops": db.execute("SELECT COUNT(*) AS c FROM shops").fetchone()["c"],
        "products": db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"],
        "users": db.execute("SELECT COUNT(*) AS c FROM users WHERE role='user'").fetchone()["c"],
    }
    return render_template(
        "admin.html", shops=shops, stats=stats, category_labels=CATEGORY_LABELS
    )


@app.route("/admin/shop/<int:sid>")
@admin_required
def admin_shop(sid):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (sid,)).fetchone()
    if shop is None:
        flash("فرۆشگاکە نەدۆزرایەوە", "error")
        return redirect(url_for("admin_dashboard"))
    products = db.execute(
        "SELECT * FROM products WHERE shop_id = ? ORDER BY name COLLATE NOCASE", (sid,)
    ).fetchall()
    return render_template(
        "admin_shop.html", shop=shop, products=products, category_labels=CATEGORY_LABELS
    )


@app.route("/admin/shop/<int:sid>/product/add", methods=["POST"])
@admin_required
def admin_add_product(sid):
    name = request.form.get("name", "").strip()
    price = parse_price(request.form.get("price"))
    if not name or price is None:
        flash("ناو یان نرخەکە دروست نییە", "error")
        return redirect(url_for("admin_shop", sid=sid))
    db = get_db()
    db.execute(
        "INSERT INTO products (shop_id, name, price) VALUES (?, ?, ?)", (sid, name, price)
    )
    db.commit()
    flash("کاڵاکە زیادی کرا", "success")
    return redirect(url_for("admin_shop", sid=sid))


@app.route("/admin/product/<int:pid>/update", methods=["POST"])
@admin_required
def admin_update_product(pid):
    name = request.form.get("name", "").strip()
    price = parse_price(request.form.get("price"))
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if product is None:
        flash("کاڵاکە نەدۆزرایەوە", "error")
        return redirect(url_for("admin_dashboard"))
    if not name or price is None:
        flash("ناو یان نرخەکە دروست نییە", "error")
        return redirect(url_for("admin_shop", sid=product["shop_id"]))
    db.execute(
        "UPDATE products SET name = ?, price = ?, updated_at = datetime('now') WHERE id = ?",
        (name, price, pid),
    )
    db.commit()
    flash("نرخی کاڵاکە نوێکرایەوە", "success")
    return redirect(url_for("admin_shop", sid=product["shop_id"]))


@app.route("/admin/product/<int:pid>/delete", methods=["POST"])
@admin_required
def admin_delete_product(pid):
    db = get_db()
    product = db.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    if product is not None:
        db.execute("DELETE FROM products WHERE id = ?", (pid,))
        db.commit()
        flash("کاڵاکە سڕایەوە", "success")
        return redirect(url_for("admin_shop", sid=product["shop_id"]))
    flash("کاڵاکە نەدۆزرایەوە", "error")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/compare")
@admin_required
def admin_compare():
    db = get_db()
    rows = db.execute("""
        SELECT p.id AS pid, p.name AS name, p.price AS price,
               s.shop_name, s.showroom
        FROM products p JOIN shops s ON p.shop_id = s.id
        ORDER BY p.name COLLATE NOCASE, p.price
    """).fetchall()

    groups = {}
    for r in rows:
        key = r["name"].strip().lower()
        entry = groups.setdefault(key, {"name": r["name"], "prices": []})
        entry["prices"].append({
            "price": r["price"],
            "shop": r["shop_name"],
            "showroom": r["showroom"],
        })

    items = []
    for key, entry in groups.items():
        entry["prices"].sort(key=lambda x: x["price"])
        entry["min"] = entry["prices"][0]
        entry["max"] = entry["prices"][-1]
        entry["count"] = len(entry["prices"])
        entry["diff"] = round(entry["max"]["price"] - entry["min"]["price"], 2)
        items.append(entry)

    items.sort(key=lambda x: x["name"])
    return render_template("compare.html", items=items)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)