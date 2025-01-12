import random
import string
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv
import os
import requests
import base64
from datetime import datetime


app = Flask(__name__)

# In-memory database for vouchers
vouchers = {}

# Function to generate unique voucher codes
def generate_voucher():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Route for captive portal login
@app.route('/login', methods=['GET', 'POST'])  # Corrected to lowercase
def login():
    if request.method == 'POST':
        voucher_code = request.form.get("voucher_code")

        # Check if voucher exists and is not used
        if voucher_code in vouchers and not vouchers[voucher_code]["used"]:
            vouchers[voucher_code]["used"] = True  # Mark voucher as used
            return jsonify({"message": "Login successful! Enjoy your WiFi."})
        else:
            return jsonify({"error": "Invalid or already used voucher code."}), 400

    # Render login form
    return render_template('login.html')

# Route to simulate voucher purchase (for testing)
@app.route('/buy-voucher', methods=['POST'])
def buy_voucher():
    data = request.json
    phone_number = data.get("phone_number")
    amount = data.get("amount")

    if not phone_number or not amount:
        return jsonify({"error": "Phone number and amount are required"}), 400

    # Generate a voucher code and store it
    voucher_code = generate_voucher()
    vouchers[voucher_code] = {"phone": phone_number, "used": False}
    return jsonify({
        "message": "Voucher purchased successfully.",
        "voucher_code": voucher_code
    })


# Load environment variables from .env file
load_dotenv()

# M-Pesa credentials from .env file
CONSUMER_KEY = os.getenv("CONSUMER_KEY")
CONSUMER_SECRET = os.getenv("CONSUMER_SECRET")
BUSINESS_SHORT_CODE = os.getenv("BUSINESS_SHORT_CODE")
PASSKEY = os.getenv("PASSKEY")
OAUTH_URL = os.getenv("OAUTH_URL")
LIPA_NA_MPESA_URL = os.getenv("LIPA_NA_MPESA_URL")

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
            "PartyA": phone_number,  # Customer's phone number
            "PartyB": BUSINESS_SHORT_CODE,
            "PhoneNumber": phone_number,
            "CallBackURL": "https://yourdomain.com/callback",  # Replace with your callback URL
            "AccountReference": "WiFi Voucher",
            "TransactionDesc": "Purchase WiFi Voucher",
        }

        response = requests.post(LIPA_NA_MPESA_URL, headers=headers, json=payload)

        if response.status_code == 200:
            return response.json()
        else:
            return {"error": response.json()}
    except Exception as e:
        return {"error": str(e)}

# Example usage: Initiating STK Push
phone_number = "2547XXXXXXXX"  # Replace with the customer's phone number
amount = 50  # Amount to charge

response = initiate_stk_push(phone_number, amount)
print(response)

app = Flask(__name__)

# Callback endpoint to handle M-Pesa payment responses
@app.route('/callback', methods=['POST'])
def callback():
    data = request.json
    print("Callback Data:", data)  # Log callback data for debugging

    # Extract necessary details from callback
    result_code = data.get("Body", {}).get("stkCallback", {}).get("ResultCode")
    result_desc = data.get("Body", {}).get("stkCallback", {}).get("ResultDesc")

    if result_code == 0:
        print("Payment successful:", result_desc)
        # Handle successful payment logic (e.g., generate voucher, activate Wi-Fi)
    else:
        print("Payment failed:", result_desc)
        # Handle failed payment logic (e.g., notify user)

    return jsonify({"message": "Callback received successfully"}), 200

if __name__ == "__main__":
    app.run(debug=True, port=5000)


if __name__ == "__main__":
    app.run(debug=True, port=5000)
