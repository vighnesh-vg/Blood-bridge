from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_cors import CORS
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
CORS(app)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))

def get_db_connection():
    conn = sqlite3.connect('blood_bank.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    return redirect(url_for('login'))
import requests  


GOOGLE_API_KEY = 'AIzaSyBhiP9yN50DLvUGoU9_q3XDEh_YvzOSHKk'  

def get_lat_lng_from_address(address):
    """Use Google Geocoding API to fetch lat/lng for a given address."""
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={GOOGLE_API_KEY}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['results']:
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    return None, None 

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = request.form
        app.logger.info(f"Received form data: {data}")
        
        try:
            name = data['name']
            email = data['email']
            address = data['address']
            license_number = data['license_number']
            password = data['password']
            latitude = data['latitude']
            longitude = data['longitude']

            if not latitude or not longitude:
                app.logger.error(f"Latitude/Longitude missing for address: {address}")
                flash("Please select a valid address from suggestions.", "danger")
                return render_template('signup.html')

            password_hash = generate_password_hash(password)

            conn = get_db_connection()
            conn.execute('''
                INSERT INTO pending_accounts (name, email, address, latitude, longitude, license_number, password)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, email, address, latitude, longitude, license_number, password_hash))
            conn.commit()
            conn.close()

            flash("Signup successful! Await verification.", "success")
            return redirect(url_for('login'))

        except KeyError as e:
            app.logger.error(f"Missing key in form data: {e}")
            flash("Form submission error. Please fill in all required fields.", "danger")
            return render_template('signup.html')
        except sqlite3.Error as e:
            app.logger.error(f"Database error: {e}")
            flash("Database error. Please try again later.", "danger")
            return render_template('signup.html')
        except Exception as e:
            app.logger.error(f"Unexpected error: {e}")
            flash("An unexpected error occurred. Please try again later.", "danger")
            return render_template('signup.html')

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        user = conn.execute('SELECT * FROM main_table WHERE email = ?', (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            session['user_email'] = user['email']
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid email or password.", "danger")

    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    email = session.get('user_email')

    if not email:
        flash("Please log in first.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM main_table WHERE email = ?', (email,)).fetchone()
    conn.close()

    if user:
        return render_template('dashboard.html', 
                               bank_name=user['name'],
                               bank_id=user['id'],
                               address=user['address'],
                               license_number=user['license_number'])
    else:
        flash("User details not found.", "danger")
        return redirect(url_for('login'))

@app.route('/admin')
def admin_panel():
    conn = get_db_connection()
    pending_accounts = conn.execute('SELECT * FROM pending_accounts').fetchall()
    conn.close()
    return render_template('admin.html', pending_accounts=pending_accounts)

@app.route('/verify/<int:account_id>', methods=['POST'])
def verify_account(account_id):
    conn = get_db_connection()
    account = conn.execute('SELECT * FROM pending_accounts WHERE id = ?', (account_id,)).fetchone()
    
    if account:
        
        conn.execute(
            'INSERT INTO main_table (name, email, address, latitude, longitude, license_number, password) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (account['name'], account['email'], account['address'], account['latitude'], account['longitude'], account['license_number'], account['password'])
        )
        
        
        new_account = conn.execute('SELECT id FROM main_table WHERE email = ?', (account['email'],)).fetchone()
        bloodbank_id = new_account['id']
        blood_bank_table_name = f'blood_bank_{bloodbank_id}'
        
        
        conn.execute(f'''
            CREATE TABLE {blood_bank_table_name} (
                blood_type TEXT PRIMARY KEY,
                number_of_units INTEGER NOT NULL DEFAULT 0
            )
        ''')

        blood_types = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']
        conn.executemany(
            f'INSERT INTO {blood_bank_table_name} (blood_type, number_of_units) VALUES (?, ?)',
            [(blood_type, 0) for blood_type in blood_types]
        )
        
        
        conn.execute('DELETE FROM pending_accounts WHERE id = ?', (account_id,))
        conn.commit()
        flash("Account verified and inventory table created.", "success")
    else:
        flash("Account not found.", "danger")
    
    conn.close()
    return redirect(url_for('admin_panel'))



@app.route('/inventory')
def inventory():
    email = session.get('user_email')

    if not email:
        flash("Please log in first.", "danger")
        return redirect(url_for('login'))

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM main_table WHERE email = ?', (email,)).fetchone()
    conn.close()

    if user:
        bloodbank_id = user['id']
        blood_bank_table_name = f'blood_bank_{bloodbank_id}'

        conn = get_db_connection()
        inventory_data = conn.execute(f'SELECT * FROM {blood_bank_table_name}').fetchall()
        conn.close()

        return render_template('inventory.html', 
                               inventory=inventory_data, 
                               bloodbank_id=bloodbank_id)
    else:
        flash("User details not found.", "danger")
        return redirect(url_for('login'))

@app.route('/update_inventory/<int:bloodbank_id>', methods=['POST'])
def update_inventory(bloodbank_id):
    conn = get_db_connection()
    blood_bank_table_name = f'blood_bank_{bloodbank_id}'

    blood_type = request.form['blood_type']
    units = int(request.form['units'])

    existing_data = conn.execute(f'SELECT * FROM {blood_bank_table_name} WHERE blood_type = ?', (blood_type,)).fetchone()

    if existing_data:
        current_units = existing_data['number_of_units']
        new_units = current_units + units
        conn.execute(f'UPDATE {blood_bank_table_name} SET number_of_units = ? WHERE blood_type = ?', (new_units, blood_type))
    else:
        conn.execute(f'INSERT INTO {blood_bank_table_name} (blood_type, number_of_units) VALUES (?, ?)', (blood_type, units))

    conn.commit()
    conn.close()

    flash("Inventory updated successfully!", "success")
    return redirect(url_for('inventory'))

@app.route('/delete_inventory/<int:bloodbank_id>', methods=['POST'])
def delete_inventory(bloodbank_id):
    conn = get_db_connection()
    blood_bank_table_name = f'blood_bank_{bloodbank_id}'

    blood_type = request.form['blood_type']
    units = int(request.form['units'])

    existing_data = conn.execute(f'SELECT * FROM {blood_bank_table_name} WHERE blood_type = ?', (blood_type,)).fetchone()

    if existing_data:
        current_units = existing_data['number_of_units']
        new_units = max(0, current_units - units)
        conn.execute(f'UPDATE {blood_bank_table_name} SET number_of_units = ? WHERE blood_type = ?', (new_units, blood_type))
    else:
        flash(f"{blood_type} not found in the inventory.", "warning")

    conn.commit()
    conn.close()

    flash("Inventory updated successfully!", "success")
    return redirect(url_for('inventory'))



# ------------------ API ENDPOINTS ------------------

@app.route('/api/blood_banks', methods=['GET'])
def api_get_blood_banks():
    conn = get_db_connection()
    banks = conn.execute('SELECT id, name, address FROM main_table').fetchall()
    conn.close()

    return {
        "status": "success",
        "blood_banks": [dict(bank) for bank in banks]
    }, 200


@app.route('/api/blood_availability/<int:bank_id>', methods=['GET'])
def api_get_blood_availability(bank_id):
    table_name = f"blood_bank_{bank_id}"
    conn = get_db_connection()
    try:
        data = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        conn.close()
        return {
            "status": "success",
            "blood_availability": [dict(row) for row in data]
        }, 200
    except sqlite3.Error as e:
        conn.close()
        return {
            "status": "error",
            "message": str(e)
        }, 500


@app.route('/api/search_blood_type/<blood_type>', methods=['GET'])
def api_search_blood_type(blood_type):
    conn = get_db_connection()
    bank_ids = conn.execute("SELECT id, name, address FROM main_table").fetchall()

    result = []

    for bank in bank_ids:
        bank_id = bank['id']
        table_name = f"blood_bank_{bank_id}"

        try:
            row = conn.execute(f"SELECT number_of_units FROM {table_name} WHERE blood_type = ?", (blood_type,)).fetchone()
            if row and row['number_of_units'] > 0:
                result.append({
                    "bank_id": bank_id,
                    "name": bank['name'],
                    "address": bank['address'],
                    "units_available": row['number_of_units']
                })
        except sqlite3.Error:
            continue

    conn.close()

    return {
        "status": "success",
        "matching_banks": result
    }, 200


if __name__ == '__main__':
    app.run(debug=True)
