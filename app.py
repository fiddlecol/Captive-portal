import random
import string
import os
import requests
import base64
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import sqlite3

# Initialize Flask app
app = Flask(__name__)

# Load environment variables from .env file
load_dotenv()

# M-Pesa credentials from .env file
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
BUSINESS_SHORT_CODE = os.getenv("BUSINESS_SHORT_CODE")
PASSKEY = os.getenv("PASSKEY")
OAUTH_URL = os.getenv("OAUTH_URL")
LIPA_NA_MPESA_URL = os.getenv("LIPA_NA_MPESA_URL")

# SQLite Database setup
DATABASE = 'vouchers.db'

# Function to get a database connection
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row  # To access columns by name
    return conn

# Function to initialize the database
def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS vouchers (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            voucher_code TEXT UNIQUE,
                            used BOOLEAN DEFAULT 0,
                            data TEXT,
                            duration TEXT,
                            phone_number TEXT
                        )''')
        conn.commit()

# Function to generate unique voucher codes
def generate_voucher():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Function to format phone number
def format_phone_number(phone_number):
    phone_number = phone_number.strip()
    if phone_number.startswith("0"):
        phone_number = "254" + phone_number[1:]
    elif phone_number.startswith("+"):
        phone_number = phone_number[1:]
    elif not phone_number.startswith("254"):
        raise ValueError("Phone number must start with '0', '+254', or '254'")
    return phone_number

# Get unused voucher
def get_unused_voucher():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT voucher_code FROM vouchers WHERE used = 0 LIMIT 1")
        voucher = cursor.fetchone()
    return voucher[0] if voucher else None

# Function to get access token
def get_access_token():
    response = requests.get(OAUTH_URL, auth=(CONSUMER_KEY, CONSUMER_SECRET))
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        raise Exception(f"Failed to get access token: {response.json()}")

# Function to generate password for STK Push
def generate_password():
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password_str = f"{BUSINESS_SHORT_CODE}{PASSKEY}{timestamp}"
    password = base64.b64encode(password_str.encode()).decode()
    return password, timestamp

# Function to initiate STK Push
def initiate_stk_push(phone_number, amount):
    try:
        phone_number = format_phone_number(phone_number)
        access_token = get_access_token()
        password, timestamp = generate_password()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        payload = {
            "BusinessShortCode": BUSINESS_SHORT_CODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone_number,
            "PartyB": BUSINESS_SHORT_CODE,
            "PhoneNumber": phone_number,
            "CallBackURL": "https://yourdomain.com/callback",
            "AccountReference": "WiFi Voucher",
            "TransactionDesc": "Purchase WiFi Voucher",
        }

        print("STK Push Payload:", payload)
        response = requests.post(LIPA_NA_MPESA_URL, headers=headers, json=payload)
        print("STK Push Response:", response.status_code, response.text)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json()}
    except Exception as e:
        return {"error": str(e)}

# Route for captive portal login
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT voucher_code FROM vouchers WHERE used = 0 LIMIT 1")
            result = cursor.fetchone()

        if result:
            voucher_code = result[0]
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE vouchers SET used = 1 WHERE voucher_code = ?", (voucher_code,))
                conn.commit()

            return jsonify({
                "message": "Login successful! Enjoy your WiFi.",
                "voucher_code": voucher_code
            })
        else:
            return jsonify({"error": "No unused vouchers available."}), 400

    return render_template('login.html')

# Route to process voucher purchase
@app.route('/buy-voucher', methods=['POST'])
def buy_voucher():
    data = request.get_json()
    phone_number = data.get('phone_number')
    amount = data.get('amount')
    voucher_data = data.get('data')
    duration = data.get('duration')

    try:
        with get_db() as conn:
            voucher_code = generate_voucher()
            response = initiate_stk_push(phone_number, amount)

            if "error" in response:
                raise Exception(f"STK Push failed: {response['error']}")

            conn.execute(
                "INSERT INTO vouchers (voucher_code, used, data, duration, phone_number) VALUES (?, 0, ?, ?, ?)",
                (voucher_code, voucher_data, duration, phone_number),
            )
            conn.commit()

            return jsonify({
                "message": "Sent successfully. Enter PIN on your phone to complete payment.",
                "voucher_code": voucher_code,
            })

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    try:
        callback_data = request.get_json()
        print("Callback Data:", callback_data)

        result_code = callback_data.get("Body", {}).get("stkCallback", {}).get("ResultCode")
        if result_code == 0:
            reference_code = callback_data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][1]["Value"]

            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE vouchers SET used = 1 WHERE voucher_code = ?", (reference_code,))
                conn.commit()
                return jsonify({"message": "Payment verified and voucher activated."})

        else:
            return jsonify({"error": "Payment failed or canceled."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
