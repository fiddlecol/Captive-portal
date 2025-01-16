import random
import string
import os
import requests
import base64
from datetime import datetime
# from diffusers import DiffusionPipeline
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
                            used BOOLEAN,
                            data TEXT,
                            duration TEXT)''')
        conn.commit()

# Function to generate unique voucher codes
def generate_voucher():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Function to format phone number
def format_phone_number(phone_number):
    """
    Formats a phone number to the international format required by Safaricom API.
    Example: Converts '07XXXXXXXX' to '2547XXXXXXXX'
    """
    phone_number = phone_number.strip()  # Remove extra spaces
    if phone_number.startswith("0"):  # Local format to international
        phone_number = "254" + phone_number[1:]
    elif phone_number.startswith("+"):
        phone_number = phone_number[1:]  # Remove '+' sign
    elif not phone_number.startswith("254"):
        raise ValueError("Phone number must start with '0', '+254', or '254'")
    return phone_number

# Get unused voucher
def get_unused_voucher():
    conn = sqlite3.connect('vouchers.db')
    cursor = conn.cursor()
    cursor.execute("SELECT voucher_code FROM vouchers WHERE used = 0 LIMIT 1")
    voucher = cursor.fetchone()
    conn.close()
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
        phone_number = format_phone_number(phone_number)  # Ensure correct format
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
            "PartyA": phone_number,  # Formatted phone number
            "PartyB": BUSINESS_SHORT_CODE,
            "PhoneNumber": phone_number,
            "CallBackURL": "https://yourdomain.com/callback",  # Replace with your callback URL
            "AccountReference": "WiFi Voucher",
            "TransactionDesc": "Purchase WiFi Voucher",
        }

        # Log the payload
        print("STK Push Payload:", payload)

        # Make the STK Push request
        response = requests.post(LIPA_NA_MPESA_URL, headers=headers, json=payload)

        # Log the response status and body
        print("STK Push Response Status:", response.status_code)
        print("STK Push Response Text:", response.text)

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
        # Automatically fetch an unused voucher
        conn = sqlite3.connect('vouchers.db')
        cursor = conn.cursor()
        cursor.execute("SELECT voucher_code FROM vouchers WHERE used = 0 LIMIT 1")
        result = cursor.fetchone()

        if result:
            voucher_code = result[0]
            # Mark the voucher as used
            cursor.execute("UPDATE vouchers SET used = 1 WHERE voucher_code = ?", (voucher_code,))
            conn.commit()
            conn.close()

            return jsonify({
                "message": "Login successful! Enjoy your WiFi.",
                "voucher_code": voucher_code
            })
        else:
            conn.close()
            return jsonify({"error": "No unused vouchers available."}), 400

    # Render the login page
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
        # Initiate STK Push
        response = initiate_stk_push(phone_number, amount)

        if "error" in response:
            return jsonify({"error": response["error"]}), 400

        # Generate voucher and store in SQLite database
        voucher_code = generate_voucher()
        with get_db() as conn:
            conn.execute("INSERT INTO vouchers (voucher_code, used, data, duration) VALUES (?, 0, ?, ?)",
                         (voucher_code, voucher_data, duration))
            conn.commit()

        return jsonify({
            "message": "Sent successfully. Enter PIN on your phone to complete payment.",
            "voucher_code": voucher_code,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Route to get an unused voucher
@app.route('/get-voucher')
def get_voucher():
    voucher_code = get_unused_voucher()
    if voucher_code:
        return jsonify({
            "voucher_code": voucher_code
        })
    else:
        return jsonify({"error": "No unused vouchers available."}), 400

@app.route('/mpesa-callback', methods=['POST'])
def mpesa_callback():
    try:
        # Parse the callback data
        callback_data = request.get_json()
        print("Callback Data:", callback_data)

        # Extract the M-Pesa reference code
        result_code = callback_data.get("Body", {}).get("stkCallback", {}).get("ResultCode")
        if result_code == 0:  # Payment successful
            reference_code = callback_data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][1]["Value"]
            amount = callback_data["Body"]["stkCallback"]["CallbackMetadata"]["Item"][0]["Value"]

            # Create a new voucher using the reference code
            voucher_data = {
                "used": False,
                "amount": amount,
                "data": "1 GB",  # Example data plan
                "duration": "1 Hour",  # Example duration
            }
            with get_db() as conn:
                conn.execute("INSERT INTO vouchers (voucher_code, used, data, duration) VALUES (?, 0, ?, ?)",
                             (reference_code, voucher_data["data"], voucher_data["duration"]))
                conn.commit()

            print(f"Voucher created: {reference_code}")
            return jsonify({"message": "Callback received and voucher created."})
        else:
            print("Payment failed or canceled.")
            return jsonify({"error": "Payment failed or canceled."}), 400
    except Exception as e:
        print("Error processing callback:", str(e))
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Initialize the database
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)