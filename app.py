from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime
import requests
import os
import base64
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

MPESA_SHORTCODE = os.getenv("BUSINESS_SHORT_CODE")
MPESA_PASSKEY = os.getenv("PASSKEY")
MPESA_CONSUMER_KEY = os.getenv("CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
CALLBACK_URL = os.getenv("CALLBACK_URL")
OAUTH_URL = os.getenv("OAUTH_URL")
LIPA_NA_MPESA_URL = os.getenv("LIPA_NA_MPESA_URL")

def get_db_connection():
    conn = sqlite3.connect('transactions.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_reference TEXT NOT NULL UNIQUE,
        phone_number TEXT NOT NULL,
        amount REAL NOT NULL,
        timestamp TEXT NOT NULL,
        is_used INTEGER DEFAULT 0
    )''')
    conn.commit()
    conn.close()

def get_mpesa_token():
    auth = (MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET)
    response = requests.get(OAUTH_URL, auth=auth)
    response_data = response.json()
    return response_data.get("access_token")

def initiate_stk_push(phone_number, amount, transaction_reference):
    try:
        # Sanitize phone number
        if phone_number.startswith("+"):
            phone_number = phone_number[1:]
        if phone_number.startswith("0"):
            phone_number = f"254{phone_number[1:]}"
        elif not phone_number.startswith("254"):
            return {"error": "Invalid phone number format"}

        access_token = get_mpesa_token()
        headers = {"Authorization": f"Bearer {access_token}"}
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        password = base64.b64encode(f"{MPESA_SHORTCODE}{MPESA_PASSKEY}{timestamp}".encode('utf-8')).decode('utf-8')

        payload = {
            "BusinessShortCode": MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": MPESA_SHORTCODE,
            "PhoneNumber": phone_number,
            "CallBackURL": CALLBACK_URL,
            "AccountReference": transaction_reference,
            "TransactionDesc": "Voucher Purchase"
        }

        response = requests.post(LIPA_NA_MPESA_URL, json=payload, headers=headers)
        return response.json()
    except requests.exceptions.JSONDecodeError:
        return {"error": "Invalid response from M-Pesa API"}

@app.route('/')
def home():
    return render_template('login.html')

@app.route('/validate', methods=['POST'])
def validate_transaction():
    data = request.json
    transaction_reference = data.get('transaction_reference')

    if not transaction_reference:
        return jsonify({"success": False, "message": "Transaction reference is required"}), 400

    conn = get_db_connection()
    transaction = conn.execute(
        'SELECT * FROM transactions WHERE transaction_reference = ? AND is_used = 0',
        (transaction_reference,)
    ).fetchone()

    if transaction:
        conn.execute(
            'UPDATE transactions SET is_used = 1 WHERE transaction_reference = ?',
            (transaction_reference,)
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Access granted"}), 200
    else:
        conn.close()
        return jsonify({"success": False, "message": "Invalid or already used transaction reference"}), 400

@app.route('/buy-voucher', methods=['POST'])
def buy_voucher():
    data = request.json
    phone_number = data.get('phone_number')
    amount = data.get('amount')
    data_plan = data.get('data')
    duration = data.get('duration')
    transaction_reference = f"TXN{datetime.now().strftime('%Y%m%d%H%M%S')}"

    if not all([phone_number, amount, data_plan, duration]):
        return jsonify({"success": False, "message": "All fields are required"}), 400

    # Sanitize phone number
    if phone_number.startswith("+"):
        phone_number = phone_number[1:]
    if phone_number.startswith("0"):
        phone_number = f"254{phone_number[1:]}"
    elif not phone_number.startswith("254"):
        return jsonify({"success": False, "message": "Invalid phone number format"}), 400

    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = get_db_connection()
    try:
        conn.execute(
            'INSERT INTO transactions (transaction_reference, phone_number, amount, timestamp) VALUES (?, ?, ?, ?)',
            (transaction_reference, phone_number, amount, timestamp)
        )
        conn.commit()
        conn.close()

        # Initiate STK Push
        stk_response = initiate_stk_push(phone_number, amount, transaction_reference)
        if "error" in stk_response:
            return jsonify({"success": False, "message": stk_response.get("errorMessage", "Failed to initiate STK Push")}), 400

        return jsonify({"success": True, "voucher_code": transaction_reference}), 201
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"success": False, "message": "Failed to generate voucher"}), 400

@app.route('/get-voucher', methods=['GET'])
def get_voucher():
    return jsonify({"success": False, "message": "Not implemented"}), 404

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)
