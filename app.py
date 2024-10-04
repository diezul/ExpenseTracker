from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pandas as pd
from io import BytesIO
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Initialize Firebase with your service account key
cred = credentials.Certificate("serviceAccountKey.json")  # Replace with environment var on Vercel if needed
firebase_admin.initialize_app(cred)
db = firestore.client()

# Helper function to fetch user by ID
def get_user_by_id(user_id):
    user_ref = db.collection('users').document(user_id)
    return user_ref.get().to_dict()

# Helper function to fetch user by username
def get_user_by_username(username):
    users_ref = db.collection('users')
    query = users_ref.where('username', '==', username).stream()
    return next(query, None)

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = get_user_by_id(session['user_id'])

# Register user
@app.route('/register', methods=['GET', 'POST'])
def register():
    currencies = pd.read_excel('data/path_to_currency_file.xlsx').to_dict(orient='records')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        currency = request.form['currency']
        hashed_password = generate_password_hash(password)

        if get_user_by_username(username):
            flash('Username already exists', 'error')
            return redirect(url_for('register'))

        # Add the new user to Firestore
        new_user_ref = db.collection('users').document()
        new_user_ref.set({
            'username': username,
            'password': hashed_password,
            'currency': currency,
            'is_admin': False
        })

        flash('Registration successful, please log in', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', currencies=currencies)

# Login user
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = get_user_by_username(username)
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            flash(f'You are logged in as: {username}', 'success')
            return redirect(url_for('index'))
        
        flash('Invalid username or password', 'error')
        return redirect(url_for('login'))

    return render_template('login.html')

# Logout user
@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

# Index route
@app.route('/')
def index():
    if not g.user:
        return redirect(url_for('login'))

    user_id = g.user['id']

    fixed_services = db.collection('fixed_services').where('user_id', '==', user_id).stream()
    variable_services = db.collection('variable_services').where('user_id', '==', user_id).stream()
    fixed_expenses = db.collection('expenses').where('user_id', '==', user_id).where('category', '==', 'Fixe').stream()
    variable_expenses = db.collection('expenses').where('user_id', '==', user_id).where('category', '==', 'Variabile').stream()

    variable_months = db.collection('expenses').where('user_id', '==', user_id).where('category', '==', 'Variabile').where('amount', '==', None).stream()

    return render_template('index.html',
                           fixed_expenses=[doc.to_dict() for doc in fixed_expenses],
                           variable_expenses=[doc.to_dict() for doc in variable_expenses],
                           fixed_services=[doc.to_dict() for doc in fixed_services],
                           variable_services=[doc.to_dict() for doc in variable_services],
                           variable_months=[doc.to_dict() for doc in variable_months])

# Add fixed expense
@app.route('/add_fixed', methods=['POST'])
def add_fixed():
    if not g.user:
        return redirect(url_for('login'))

    user_id = g.user['id']
    service_name = request.form['service_name']
    month = request.form['month']
    amount = request.form['amount']

    db.collection('expenses').add({
        'category': 'Fixe',
        'month': month,
        'amount': float(amount),
        'service_name': service_name,
        'user_id': user_id
    })

    db.collection('fixed_services').add({'service_name': service_name, 'user_id': user_id})
    
    return redirect(url_for('index'))

# Add variable expense
@app.route('/add_variable', methods=['POST'])
def add_variable():
    if not g.user:
        return redirect(url_for('login'))

    user_id = g.user['id']
    service_name = request.form['service_name']
    month = request.form['month']
    index_value = request.form['index_value']

    db.collection('expenses').add({
        'category': 'Variabile',
        'month': month,
        'index_value': index_value,
        'service_name': service_name,
        'user_id': user_id
    })

    db.collection('variable_services').add({'service_name': service_name, 'user_id': user_id})
    
    return redirect(url_for('index'))

# Export expenses to Excel
@app.route('/export_expenses')
def export_expenses():
    if not g.user:
        return redirect(url_for('login'))

    user_id = g.user['id']
    expenses = db.collection('expenses').where('user_id', '==', user_id).stream()
    
    user_currency = g.user['currency']
    df = pd.DataFrame([doc.to_dict() for doc in expenses], columns=["service_name", "month", "index_value", "amount", "is_paid"])
    df['Paid'] = df['is_paid'].apply(lambda x: 'Yes' if x else 'No')
    df['Amount'] = df['amount'].apply(lambda x: format_amount(x, user_currency))

    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Expenses')
    writer.save()
    output.seek(0)

    return send_file(output, download_name="expenses.xlsx", as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
