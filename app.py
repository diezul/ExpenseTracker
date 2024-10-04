from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pandas as pd
from io import BytesIO
import requests

app = Flask(__name__)
app.secret_key = 'your_secret_key'
DATABASE = 'database.db'

# Firebase config
firebaseConfig = {
    "apiKey": "AIzaSyA_E_cD3tN8IY_i-plRcloBjuNq7oydDrE",
    "authDomain": "expensetracker-afc73.firebaseapp.com",
    "projectId": "expensetracker-afc73",
    "storageBucket": "expensetracker-afc73.appspot.com",
    "messagingSenderId": "283545335538",
    "appId": "1:283545335538:web:bc38233888deea7c69c26b",
    "measurementId": "G-FM7Z2E0DHQ"
}

FIREBASE_API_KEY = firebaseConfig['apiKey']

# Firebase Auth REST API endpoint for sign-up and sign-in
FIREBASE_SIGNUP_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_API_KEY}"
FIREBASE_SIGNIN_URL = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"

# Initialize the database connection
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        user = query_db('select * from users where id = ?',
                        [session['user_id']],
                        one=True)
        g.user = user

def query_db(query, args=(), one=False):
    with get_db_connection() as conn:
        cur = conn.execute(query, args)
        rv = cur.fetchall()
        cur.close()
        return (rv[0] if rv else None) if one else rv

def format_amount(value, currency_code):
    if value is None:
        return '-'
    return f"{value} {currency_code}"

def format_month(month):
    return datetime.strptime(month, "%Y-%m").strftime("%B / %Y")

def split_month(value):
    return value.split(' ')[0]

app.jinja_env.filters['format_amount'] = format_amount
app.jinja_env.filters['format_month'] = format_month
app.jinja_env.filters['split_month'] = split_month

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password TEXT NOT NULL, currency TEXT NOT NULL, is_admin BOOLEAN DEFAULT FALSE);''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL, month TEXT NOT NULL, index_value INTEGER, amount REAL, is_paid BOOLEAN DEFAULT FALSE, service_name TEXT NOT NULL, user_id INTEGER, FOREIGN KEY (user_id) REFERENCES users(id), UNIQUE(month, service_name, index_value, user_id));''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS fixed_services (id INTEGER PRIMARY KEY AUTOINCREMENT, service_name TEXT NOT NULL, user_id INTEGER, UNIQUE(service_name, user_id), FOREIGN KEY (user_id) REFERENCES users(id));''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS variable_services (id INTEGER PRIMARY KEY AUTOINCREMENT, service_name TEXT NOT NULL, user_id INTEGER, UNIQUE(service_name, user_id), FOREIGN KEY (user_id) REFERENCES users(id));''')
        conn.commit()

# Firebase sign-up route using Firebase REST API
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        currency = request.form['currency']

        # Sign up the user using Firebase Authentication REST API
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }
        response = requests.post(FIREBASE_SIGNUP_URL, json=payload)
        result = response.json()

        if 'error' in result:
            flash('Error registering with Firebase', 'error')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            user_count = cursor.fetchone()[0]
            is_admin = user_count == 0  # First user is admin
            try:
                conn.execute('INSERT INTO users (username, password, currency, is_admin) VALUES (?, ?, ?, ?)', (email, hashed_password, currency, is_admin))
                conn.commit()
                flash('Registration successful, please log in', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username already exists', 'error')
                return redirect(url_for('register'))
    return render_template('register.html')

# Firebase sign-in route using Firebase REST API
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        # Sign in using Firebase Authentication REST API
        payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }
        response = requests.post(FIREBASE_SIGNIN_URL, json=payload)
        result = response.json()

        if 'error' in result:
            flash('Invalid email or password', 'error')
            return redirect(url_for('login'))

        user = query_db('select * from users where username = ?', [email], one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            flash(f'You are logged in as: {email}', 'success')
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

# The rest of your routes remain the same

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')
