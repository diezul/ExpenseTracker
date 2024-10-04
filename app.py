from flask import Flask, render_template, request, redirect, url_for, session, g, flash, jsonify, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.secret_key = 'your_secret_key'
DATABASE = 'database.db'


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
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            currency TEXT NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE
        );
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            month TEXT NOT NULL,
            index_value INTEGER,
            amount REAL,
            is_paid BOOLEAN DEFAULT FALSE,
            service_name TEXT NOT NULL,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(month, service_name, index_value, user_id)
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS fixed_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            user_id INTEGER,
            UNIQUE(service_name, user_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS variable_services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_name TEXT NOT NULL,
            user_id INTEGER,
            UNIQUE(service_name, user_id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        ''')
        conn.commit()


@app.route('/register', methods=['GET', 'POST'])
def register():
    currencies = pd.read_excel('data/path_to_currency_file.xlsx').to_dict(
        orient='records')
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        currency = request.form['currency']
        hashed_password = generate_password_hash(password)
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM users')
            user_count = cursor.fetchone()[0]
            is_admin = user_count == 0  # First user is admin
            try:
                conn.execute(
                    'INSERT INTO users (username, password, currency, is_admin) VALUES (?, ?, ?, ?)',
                    (username, hashed_password, currency, is_admin))
                conn.commit()
                flash('Registration successful, please log in', 'success')
                return redirect(url_for('login'))
            except sqlite3.IntegrityError:
                flash('Username already exists', 'error')
                return redirect(url_for('register'))
    return render_template('register.html', currencies=currencies)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = query_db('select * from users where username = ?', [username],
                        one=True)
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            flash(f'You are logged in as: {username}', 'success')
            return redirect(url_for('index'))
        flash('Invalid username or password', 'error')
        return redirect(url_for('login'))
    return render_template('login.html')


@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))


@app.route('/')
def index():
    if not g.user:
        return redirect(url_for('login'))
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT service_name FROM fixed_services WHERE user_id = ?",
            (user_id, ))
        fixed_services = [row['service_name'] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT DISTINCT service_name FROM variable_services WHERE user_id = ?",
            (user_id, ))
        variable_services = [row['service_name'] for row in cursor.fetchall()]
        cursor.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND category = 'Fixe' ORDER BY month",
            (user_id, ))
        fixed_expenses = cursor.fetchall()
        cursor.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND category = 'Variabile' ORDER BY month",
            (user_id, ))
        variable_expenses = cursor.fetchall()
        cursor.execute(
            "SELECT DISTINCT month, service_name, index_value FROM expenses WHERE user_id = ? AND category = 'Variabile' AND amount IS NULL ORDER BY month",
            (user_id, ))
        variable_months = cursor.fetchall()
    return render_template('index.html',
                           fixed_expenses=fixed_expenses,
                           variable_expenses=variable_expenses,
                           fixed_services=fixed_services,
                           variable_services=variable_services,
                           variable_months=variable_months)


@app.route('/users')
def manage_users():
    if not g.user or not g.user['is_admin']:
        return redirect(url_for('index'))
    users = query_db('SELECT id, username, is_admin FROM users')
    return render_template('users.html', users=users)


@app.route('/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not g.user or not g.user['is_admin']:
        return redirect(url_for('index'))
    with get_db_connection() as conn:
        conn.execute('DELETE FROM users WHERE id = ?', (user_id, ))
        conn.commit()
    flash('User has been deleted', 'success')
    return redirect(url_for('manage_users'))


@app.route('/impersonate/<int:user_id>', methods=['POST'])
def impersonate(user_id):
    if not g.user or not g.user['is_admin']:
        return redirect(url_for('index'))
    session['user_id'] = user_id
    flash('You are now impersonating another user', 'success')
    return redirect(url_for('index'))


@app.route('/add_fixed', methods=['POST'])
def add_fixed():
    if not g.user:
        return redirect(url_for('login'))
    service_name = request.form['service_name']
    month = request.form['month']
    amount = request.form['amount']
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
        INSERT OR REPLACE INTO expenses (category, month, amount, service_name, user_id)
        VALUES ('Fixe', ?, ?, ?, ?)
        ''', (month, amount, service_name, user_id))
        cursor.execute(
            '''
        INSERT OR IGNORE INTO fixed_services (service_name, user_id)
        VALUES (?, ?)
        ''', (service_name, user_id))
        conn.commit()
    return redirect(url_for('index'))


@app.route('/add_variable', methods=['POST'])
def add_variable():
    if not g.user:
        return redirect(url_for('login'))
    service_name = request.form['service_name']
    month = request.form['month']
    index_value = request.form['index_value']
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
        INSERT INTO expenses (category, month, index_value, service_name, user_id)
        VALUES ('Variabile', ?, ?, ?, ?)
        ''', (month, index_value, service_name, user_id))
        cursor.execute(
            '''
        INSERT OR IGNORE INTO variable_services (service_name, user_id)
        VALUES (?, ?)
        ''', (service_name, user_id))
        conn.commit()
    return redirect(url_for('index'))


@app.route('/add_amount', methods=['POST'])
def add_amount():
    if not g.user:
        return redirect(url_for('login'))
    month_service_index = request.form['month']
    amount = request.form['amount']
    month, service_name, index_value = month_service_index.split('|')
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
        UPDATE expenses
        SET amount = ?
        WHERE month = ? AND service_name = ? AND user_id = ? AND index_value = ?
        ''', (amount, month, service_name, user_id, index_value))
        conn.commit()
    return redirect(url_for('index'))


@app.route('/add_service_direct/<service_type>/<service_name>',
           methods=['POST'])
def add_service_direct(service_type, service_name):
    if not g.user:
        return redirect(url_for('login'))
    user_id = g.user['id']
    table = 'fixed_services' if service_type == 'fixed' else 'variable_services'
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f'''
            INSERT INTO {table} (service_name, user_id)
            VALUES (?, ?)
            ''', (service_name, user_id))
            conn.commit()
            return jsonify({
                'message':
                f'The service {service_name} has been successfully added to your list'
            })
        except sqlite3.IntegrityError:
            return jsonify({
                'message':
                f'The service {service_name} already exists in your list'
            })


@app.route('/delete_service/<service_type>', methods=['POST'])
def delete_service(service_type):
    if not g.user:
        return redirect(url_for('login'))
    service_name = request.form['service_name']
    user_id = g.user['id']
    table = 'fixed_services' if service_type == 'fixed' else 'variable_services'
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f'''
        DELETE FROM {table}
        WHERE service_name = ? AND user_id = ?
        ''', (service_name, user_id))
        conn.commit()
    return '', 204


@app.route('/search_service/<service_type>', methods=['GET'])
def search_service(service_type):
    if not g.user:
        return jsonify({'error': 'Unauthorized access'}), 401
    query = request.args.get('q', '')
    user_id = g.user['id']
    table = 'fixed_services' if service_type == 'fixed' else 'variable_services'
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f'''
        SELECT service_name FROM {table}
        WHERE user_id = ? AND service_name LIKE ?
        ''', (user_id, f'{query}%'))
        services = [row['service_name'] for row in cursor.fetchall()]
    return jsonify({'services': services})


@app.route('/pay/<int:expense_id>', methods=['POST'])
def pay_expense(expense_id):
    if not g.user:
        return redirect(url_for('login'))
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            '''
        UPDATE expenses
        SET is_paid = TRUE
        WHERE id = ? AND user_id = ?
        ''', (expense_id, user_id))
        conn.commit()
    flash('The service has been marked as paid!', 'success')
    return redirect(url_for('index'))


@app.route('/delete/<int:expense_id>', methods=['POST'])
def delete_expense(expense_id):
    if not g.user:
        return redirect(url_for('login'))
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM expenses WHERE id = ? AND user_id = ?',
                       (expense_id, user_id))
        conn.commit()
    flash('The bill has been successfully deleted!', 'success')
    return redirect(url_for('index'))


@app.route('/export_expenses')
def export_expenses():
    if not g.user:
        return redirect(url_for('login'))
    user_id = g.user['id']
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT service_name, month, index_value, amount, is_paid FROM expenses WHERE user_id = ?",
            (user_id, ))
        expenses = cursor.fetchall()

    user_currency = g.user['currency']
    df = pd.DataFrame(expenses,
                      columns=["Service", "Month", "Index", "Amount", "Paid"])
    df['Paid'] = df['Paid'].apply(lambda x: 'Yes' if x else 'No')
    df['Amount'] = df.apply(
        lambda x: format_amount(x['Amount'], user_currency), axis=1)
    output = BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Expenses')
    writer.close()  # Corrected line
    output.seek(0)

    return send_file(output, download_name="expenses.xlsx", as_attachment=True)


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')
