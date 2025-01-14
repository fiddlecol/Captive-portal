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
@app.route('/', methods=['GET', 'POST'])  # Corrected to lowercase
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

# process  buy voucher
@app.route('/buy-voucher', methods=['POST'])
def buy_voucher():
    data = request.get_json()
    phone_number = data.get('phone_number')
    amount = data.get('amount')
    voucher_data = data.get('data')
    duration = data.get('duration')

    # Process the voucher purchase logic here (e.g., interacting with M-Pesa API)
    # For now, just send a success message
    return jsonify({"message": f"Purchased successful: {voucher_data} for {duration}."})



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

# Define format_phone_number first
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
        raise ValueError("Phone number must start with '0' or '+254' or '254'")
    return phone_number

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
            "BusinessShortCode": "174379",  # Your Business Shortcode
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": 1,
            "PartyA": "254746919779",  # Formatted phone number
            "PartyB": "174379",  # Your PartyB (business shortcode)
            "PhoneNumber": "254746919779", # customer's  phone number
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

# Example usage: Initiating STK Push
phone_number = "254708374149"  # Replace with the customer's phone number
amount = 50  # Amount to charge

response = initiate_stk_push(phone_number, amount)
print(response)


if __name__ == "__main__":
    app.run(debug=True, port=5000)

