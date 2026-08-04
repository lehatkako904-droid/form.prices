from flask import Flask, request, jsonify, session, render_template
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ڕێگەدان بە هەموو سەرچاوەکان بۆ CORS (بە پشتگیری credentials)
CORS(app, supports_credentials=True)

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS shops (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            location TEXT,
            password TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT,
            price REAL NOT NULL,
            image TEXT,
            FOREIGN KEY(shop_id) REFERENCES shops(id)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    conn = get_db()
    try:
        conn.execute('INSERT INTO shops (name, phone, location, password) VALUES (?, ?, ?, ?)',
                     (data['name'], data['phone'], data['location'], data['password']))
        conn.commit()
        return jsonify({'success': True})
    except sqlite3.IntegrityError:
        return jsonify({'success': False, 'message': 'ئەم ژمارە پێشتر تۆمارکراوە'})
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    conn = get_db()
    user = conn.execute('SELECT * FROM shops WHERE phone = ? AND password = ?',
                        (data['phone'], data['password'])).fetchone()
    conn.close()
    if user:
        session['user_id'] = user['id']
        return jsonify({
            'success': True,
            'seller': {
                'id': user['id'],
                'name': user['name'],
                'phone': user['phone'],
                'location': user['location']
            }
        })
    return jsonify({'success': False, 'message': 'ژمارە یان وشەی تێپەڕ هەڵەیە'})

@app.route('/api/products', methods=['POST'])
def add_products():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'تکایە بچۆ ژوورەوە'})
    data = request.json
    shop_id = session['user_id']
    conn = get_db()
    for p in data['products']:
        conn.execute('INSERT INTO products (shop_id, name, category, price, image) VALUES (?, ?, ?, ?, ?)',
                     (shop_id, p['name'], p['category'], p['price'], p['image']))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    if data['username'] == 'admin' and data['password'] == 'admin123':
        session['admin'] = True
        return jsonify({'success': True})
    return jsonify({'success': False})

@app.route('/api/admin/data', methods=['GET'])
def admin_data():
    if not session.get('admin'):
        return jsonify({'success': False, 'message': 'دەستپێگەیشتن ڕەتکراوە'})
    conn = get_db()
    products = conn.execute('''
        SELECT p.id, p.name, p.category, p.price, p.image,
               s.name as shop_name, s.phone, s.location
        FROM products p JOIN shops s ON p.shop_id = s.id
    ''').fetchall()
    conn.close()
    return jsonify({
        'success': True,
        'products': [dict(row) for row in products]
    })

@app.route('/api/admin/product/<int:pid>', methods=['DELETE'])
def delete_product(pid):
    if not session.get('admin'):
        return jsonify({'success': False, 'message': 'دەستپێگەیشتن ڕەتکراوە'})
    conn = get_db()
    conn.execute('DELETE FROM products WHERE id = ?', (pid,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/session', methods=['GET'])
def get_session():
    if session.get('admin'):
        return jsonify({'logged_in': True, 'is_admin': True})
    if 'user_id' in session:
        conn = get_db()
        user = conn.execute('SELECT id, name, phone, location FROM shops WHERE id = ?',
                            (session['user_id'],)).fetchone()
        conn.close()
        if user:
            return jsonify({'logged_in': True, 'seller': dict(user)})
    return jsonify({'logged_in': False})

@app.route('/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

if __name__ == '__main__':
    # بۆ پڕۆداکشن، debug=False یان لابە
    app.run(debug=False)
