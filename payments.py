from dotenv import load_dotenv
import os
import requests
import json

load_dotenv()

SELLAUTH_SHOP_ID = os.getenv("SELLAUTH_SHOP_ID")
SELLAUTH_API_KEY = os.getenv("SELLAUTH_API_KEY")

def fetch_sellauth_products():
    url = f"https://api.sellauth.com/v1/shops/{SELLAUTH_SHOP_ID}/products"
    headers = {"Authorization": f"Bearer {SELLAUTH_API_KEY}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        products_data = response.json().get("data", [])
        products = {}
        for product in products_data:
            product_name = product["name"]
            products[product_name] = {
                "id": product["id"],
                "variants": product.get("variants", [])
            }
        return products
    else:
        raise Exception(f"Failed to fetch products: {response.text}")

def generate_sellauth_checkout(product_id, variant_id, quantity, gateway, email=None, custom_fields=None):
    url = f"https://api.sellauth.com/v1/shops/{SELLAUTH_SHOP_ID}/checkout"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {SELLAUTH_API_KEY}"
    }
    payload = {
        "cart": [{
            "productId": int(product_id),
            "variantId": int(variant_id),
            "quantity": quantity
        }],
        "gateway": gateway
    }
    if email:
        payload["email"] = email
    if custom_fields:
        payload["cart"][0]["custom_fields"] = custom_fields
    print(f"Sending checkout request: {json.dumps(payload)}")
    response = requests.post(url, headers=headers, json=payload)
    print(f"Checkout response for {gateway} (product {product_id}, variant {variant_id}): {response.text}")
    if response.status_code == 200:
        data = response.json()
        return {
            "invoice_url": data.get("invoice_url") or data.get("url"),
            "txid": data.get("txid") or data.get("transaction_id") or data.get("id"),
            "address": data.get("address") or data.get("payment_address"),
            "amount": data.get("amount") or data.get("total")
        }
    else:
        raise Exception(f"Sellauth checkout error: {response.text}")

def check_sellauth_transaction_status(txid):
    url = f"https://api.sellauth.com/v1/shops/{SELLAUTH_SHOP_ID}/payouts/transactions"
    headers = {
        "Authorization": f"Bearer {SELLAUTH_API_KEY}"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        transactions = response.json().get("data", [])
        for tx in transactions:
            if tx.get("txid") == txid and tx.get("confirmations", 0) >= 1:
                return True
        return False
    else:
        raise Exception(f"Transaction status check failed: {response.text}")