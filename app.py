import random
import string
from flask import Flask, request, jsonify, render_template

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

if __name__ == "__main__":
    app.run(debug=True, port=5000)
