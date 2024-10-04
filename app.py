from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, send_file
import firebase_admin
from firebase_admin import credentials, auth, firestore
from firebase_admin.credentials import AnonymousCredentials
from datetime import datetime
import pandas as pd
from io import BytesIO
import os

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")

# Firebase Config directly in app.py
firebaseConfig = {
    "apiKey": "AIzaSyA_E_cD3tN8IY_i-plRcloBjuNq7oydDrE",
    "authDomain": "expensetracker-afc73.firebaseapp.com",
    "projectId": "expensetracker-afc73",
    "storageBucket": "expensetracker-afc73.appspot.com",
    "messagingSenderId": "283545335538",
    "appId": "1:283545335538:web:bc38233888deea7c69c26b",
    "measurementId": "G-FM7Z2E0DHQ"
}

# Initialize Firebase Admin SDK without service account file
cred = credentials.ApplicationDefault()  # Use default credentials
firebase_admin.initialize_app(cred, {
    'projectId': firebaseConfig['projectId']
})
db = firestore.client()

# Helper Functions (same as before)
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

# Firebase Authentication for login and registration
@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        user_ref = db.collection('users').document(session['user_id'])
        g.user = user_ref.get().to_dict()

# Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    currencies = pd.read_excel('data/path_to_currency_file.xlsx').to_dict(orient='records')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        currency = request.form['currency']

        # Register the user with Firebase Auth
        try:
            user = auth.create_user(email=username, password=password)
            db.collection('users').document(user.uid).set({
                'username': username,
                'currency': currency,
                'is_admin': False
            })
            flash('Registration successful, please log in', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(str(e), 'error')
            return redirect(url_for('register'))
    return render_template('register.html', currencies=currencies)

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Sign in using Firebase Auth
        try:
            user = auth.get_user_by_email(username)
            session['user_id'] = user.uid
            flash(f'You are logged in as: {username}', 'success')
            return redirect(url_for('index'))
        except Exception as e:
            flash('Invalid username or password', 'error')
            return redirect(url_for('login'))
    return render_template('login.html')

# Logout
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

# Index
@app.route('/')
def index():
    if not g.user:
        return redirect(url_for('login'))
    
    user_id = g.user['id']
    fixed_services = db.collection('fixed_services').where('user_id', '==', user_id).stream()
    variable_services = db.collection('variable_services').where('user_id', '==', user_id).stream()
    fixed_expenses = db.collection('expenses').where('user_id', '==', user_id).where('category', '==', 'Fixe').stream()
    variable_expenses = db.collection('expenses').where('user_id', '==', user_id).where('category', '==', 'Variabile').stream()

    return render_template('index.html', fixed_expenses=fixed_expenses, variable_expenses=variable_expenses, fixed_services=fixed_services, variable_services=variable_services)

# Add Expense Functions (update based on Firebase DB)
@app.route('/add_fixed', methods=['POST'])
def add_fixed():
    if not g.user:
        return redirect(url_for('login'))
    service_name = request.form['service_name']
    month = request.form['month']
    amount = request.form['amount']
    user_id = g.user['id']

    # Add to Firestore
    try:
        db.collection('expenses').add({
            'category': 'Fixe',
            'month': month,
            'amount': amount,
            'service_name': service_name,
            'user_id': user_id
        })
        db.collection('fixed_services').add({
            'service_name': service_name,
            'user_id': user_id
        })
        flash('Fixed service added!', 'success')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')

    return redirect(url_for('index'))

# Export expenses
@app.route('/export_expenses')
def export_expenses():
    if not g.user:
        return redirect(url_for('login'))
    user_id = g.user['id']
    expenses = db.collection('expenses').where('user_id', '==', user_id).stream()

    user_currency = g.user['currency']
    df = pd.DataFrame([e.to_dict() for e in expenses], columns=["Service", "Month", "Index", "Amount", "Paid"])
    df['Paid'] = df['Paid'].apply(lambda x: 'Yes' if x else 'No')
    df['Amount'] = df.apply(lambda x: format_amount(x['Amount'], user_currency), axis=1)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Expenses')
    writer.close()
    output.seek(0)

    return send_file(output, download_name="expenses.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
