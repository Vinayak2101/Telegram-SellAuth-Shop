import requests
import json
import time
import threading
from dotenv import load_dotenv
import os
from database import save_transaction, update_transaction_status, get_transaction
from payments import fetch_sellauth_products, generate_sellauth_checkout, check_sellauth_transaction_status

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
BASE_URL = f"https://api.telegram.org/bot{TOKEN}/"

PRODUCTS = {}
PAYMENT_METHODS = ["BTC", "LTC", "PAYPAL", "STRIPE", "SQUARE", "CASHAPP", "VENMO", "PAYPALFF", "AMAZONPS", "SUMUP", "MOLLIE", "SKRILL", "AUTHORIZENET", "LEMONSQUEEZY"]
PENDING_PURCHASES = {}

def send_message(chat_id, text, reply_markup=None):
    url = f"{BASE_URL}sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def edit_message(chat_id, message_id, text, reply_markup=None):
    url = f"{BASE_URL}editMessageText"
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    requests.post(url, json=payload)

def handle_update(update):
    if "message" in update and "text" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"]["text"]
        user_id = update["message"]["from"]["id"]

        if text == "/start":
            if not PRODUCTS:
                send_message(chat_id, "No products available. Contact support.")
                return
            keyboard = {"inline_keyboard": [[{"text": name, "callback_data": f"purchase_{name}"}] for name in PRODUCTS.keys()]}
            send_message(chat_id, "Welcome to KeyShopBot! Choose a product:", keyboard)

        elif "@" in text and "." in text and user_id in PENDING_PURCHASES:  # Handle email input
            try:
                email = text.strip()
                print(f"Received email: {email} for user {user_id}")
                purchase = PENDING_PURCHASES.pop(user_id)
                product_name, variant_id, currency = purchase["product_name"], purchase["variant_id"], purchase["currency"]
                product = PRODUCTS.get(product_name)
                if not product:
                    send_message(chat_id, f"Product '{product_name}' not found!")
                    return
                checkout_response = generate_sellauth_checkout(
                    product_id=product["id"],
                    variant_id=variant_id,
                    quantity=1,
                    gateway=currency,
                    email=email
                )
                invoice_url = checkout_response.get("invoice_url")
                variant_name = next((v["name"] for v in product["variants"] if str(v["id"]) == variant_id), "Unknown")
                message = (
                    f"Payment initiated for {product_name} ({variant_name}) via {currency}.\n"
                    f"Please complete the payment here: [Invoice Link]({invoice_url})\n"
                    f"Invoice sent to `{email}`.\nYou’ll receive confirmation via email once paid."
                )
                send_message(chat_id, message)
                # No txid, so no polling; rely on Sellauth email confirmation
            except Exception as e:
                print(f"Error processing purchase: {str(e)}")
                send_message(chat_id, f"Payment setup failed: {str(e)}")
        elif user_id in PENDING_PURCHASES:
            send_message(chat_id, "Please enter a valid email address (e.g., your_email@gmail.com).")

    elif "callback_query" in update:
        query = update["callback_query"]
        chat_id = query["message"]["chat"]["id"]
        message_id = query["message"]["message_id"]
        data = query["data"]
        user_id = query["from"]["id"]

        requests.post(f"{BASE_URL}answerCallbackQuery", json={"callback_query_id": query["id"]})

        if data == "buy":
            keyboard = {"inline_keyboard": [[{"text": name, "callback_data": f"purchase_{name}"}] for name in PRODUCTS.keys()]}
            edit_message(chat_id, message_id, "Choose a product:", keyboard)

        elif data.startswith("purchase_"):
            product_name = data.split("_")[1]
            if product_name not in PRODUCTS:
                edit_message(chat_id, message_id, "Product not found!")
                return
            product = PRODUCTS[product_name]
            variants = product["variants"]
            if not variants:
                edit_message(chat_id, message_id, f"No variants available for {product_name}!")
                return
            if len(variants) > 1:
                keyboard = {"inline_keyboard": [[{"text": v["name"], "callback_data": f"variant_{product_name}_{v['id']}"}] for v in variants]}
                edit_message(chat_id, message_id, f"Choose a variant for {product_name}:", keyboard)
            else:
                keyboard = {"inline_keyboard": [[{"text": m, "callback_data": f"pay_{product_name}_{variants[0]['id']}_{m}"}] for m in PAYMENT_METHODS]}
                edit_message(chat_id, message_id, f"Choose payment method for {product_name} ({variants[0]['name']}):", keyboard)

        elif data.startswith("variant_"):
            _, product_name, variant_id = data.split("_")
            if product_name not in PRODUCTS:
                edit_message(chat_id, message_id, "Product not found!")
                return
            keyboard = {"inline_keyboard": [[{"text": m, "callback_data": f"pay_{product_name}_{variant_id}_{m}"}] for m in PAYMENT_METHODS]}
            variant_name = next((v["name"] for v in PRODUCTS[product_name]["variants"] if str(v["id"]) == variant_id), "Unknown")
            edit_message(chat_id, message_id, f"Choose payment method for {product_name} ({variant_name}):", keyboard)

        elif data.startswith("pay_"):
            _, product_name, variant_id, currency = data.split("_")
            if product_name not in PRODUCTS:
                edit_message(chat_id, message_id, "Product not found!")
                return
            variant_name = next((v["name"] for v in PRODUCTS[product_name]["variants"] if str(v["id"]) == variant_id), "Unknown")
            PENDING_PURCHASES[user_id] = {"product_name": product_name, "variant_id": variant_id, "currency": currency}
            send_message(chat_id,
                         f"Please reply with your email address as we send purchase confirmation on your email as well.\n"
                         f"Example: `your_email@gmail.com`",
                         {"force_reply": True})

def check_sellauth_payment(user_id, product_name, txid):
    while True:
        transaction = get_transaction(txid)
        if transaction and transaction["status"] == "completed":
            break
        if check_sellauth_transaction_status(txid):
            update_transaction_status(txid, "completed")
            send_message(user_id, f"Payment confirmed for {product_name}! Check your Sellauth account and email for the key.")
            break
        time.sleep(60)

def main():
    global PRODUCTS
    try:
        PRODUCTS = fetch_sellauth_products()
        print(f"Loaded products: {list(PRODUCTS.keys())}")
        for name, details in PRODUCTS.items():
            print(f"  {name}: Variants - {[{k: v for k, v in v.items() if k != 'custom_fields'} for v in details['variants']]}")
    except Exception as e:
        print(f"Failed to load products: {e}")
        PRODUCTS = {}

    offset = None
    while True:
        try:
            url = f"{BASE_URL}getUpdates"
            params = {"timeout": 30, "offset": offset}
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                updates = response.json().get("result", [])
                for update in updates:
                    offset = update["update_id"] + 1
                    handle_update(update)
            else:
                print(f"Error fetching updates: {response.text}")
        except Exception as e:
            print(f"Polling error: {e}")
        time.sleep(1)

if __name__ == "__main__":
    main()