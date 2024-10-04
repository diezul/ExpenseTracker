from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import firebase_admin
from firebase_admin import credentials, auth, firestore
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pandas as pd
from io import BytesIO

# Initialize Firebase
cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)

# Firestore DB setup
db = firestore.client()

app = Flask(__name__)
app.secret_key = 'your_secret_key'


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        currency = request.form['currency']

        try:
            # Firebase Authentication
            user = auth.create_user(email=username, password=password)
            flash('Registration successful, please log in', 'success')

            # Storing user details in Firestore
            db.collection('users').document(user.uid).set({
                'username': username,
                'currency': currency,
                'is_admin': False
            })

            return redirect(url_for('login'))

        except Exception as e:
            flash(f"Error during registration: {str(e)}", 'error')
            return redirect(url_for('register'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            # Firebase Authentication Login
            user = auth.get_user_by_email(username)

            # Mimicking password check since Firebase doesn't allow direct password verification
            # Assume you have client-side Firebase auth to manage this step.

            session['user_id'] = user.uid
            flash(f'You are logged in as: {username}', 'success')
            return redirect(url_for('index'))

        except Exception as e:
            flash(f"Login failed: {str(e)}", 'error')
            return redirect(url_for('login'))

    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))


@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    user_data = db.collection('users').document(user_id).get().to_dict()

    # Fetching services and expenses for the user from Firestore
    fixed_services = db.collection('expenses').where('category', '==', 'Fixe').where('user_id', '==', user_id).stream()
    variable_services = db.collection('expenses').where('category', '==', 'Variabile').where('user_id', '==', user_id).stream()

    return render_template('index.html', fixed_services=fixed_services, variable_services=variable_services, user_data=user_data)


@app.route('/add_fixed', methods=['POST'])
def add_fixed():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    service_name = request.form['service_name']
    month = request.form['month']
    amount = request.form['amount']
    user_id = session['user_id']

    # Adding fixed service to Firestore
    db.collection('expenses').add({
        'category': 'Fixe',
        'month': month,
        'amount': amount,
        'service_name': service_name,
        'user_id': user_id
    })

    return redirect(url_for('index'))


@app.route('/add_variable', methods=['POST'])
def add_variable():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    service_name = request.form['service_name']
    month = request.form['month']
    index_value = request.form['index_value']
    user_id = session['user_id']

    # Adding variable service to Firestore
    db.collection('expenses').add({
        'category': 'Variabile',
        'month': month,
        'index_value': index_value,
        'service_name': service_name,
        'user_id': user_id
    })

    return redirect(url_for('index'))


@app.route('/export_expenses')
def export_expenses():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    # Fetching expenses from Firestore
    expenses = db.collection('expenses').where('user_id', '==', user_id).stream()
    user_data = db.collection('users').document(user_id).get().to_dict()

    user_currency = user_data['currency']
    expense_list = [expense.to_dict() for expense in expenses]

    df = pd.DataFrame(expense_list, columns=["service_name", "month", "index_value", "amount", "is_paid"])
    df['amount'] = df.apply(lambda x: f"{x['amount']} {user_currency}", axis=1)

    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Expenses')
    writer.save()
    output.seek(0)

    return send_file(output, download_name="expenses.xlsx", as_attachment=True)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')
