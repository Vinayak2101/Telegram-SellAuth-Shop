from flask import Flask, request
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, Filters
import requests
import os

# === CONFIGURATION ===
BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'
SELLAUTH_API_KEY = 'YOUR_SELLAUTH_API_KEY_HERE'
SHOP_ID = 'YOUR_SHOP_ID_HERE'

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)
dispatcher = Dispatcher(bot=bot, update_queue=None, workers=0, use_context=True)

# === STATES ===
SELECT_PRODUCT, SELECT_PAYMENT, WAIT_PAYMENT = range(3)

# === COMMAND: /start ===
def start(update, context):
    user = update.message.from_user
    response = requests.get(f"https://api.sellauth.com/v1/shops/{SHOP_ID}/products", headers={"Authorization": f"Bearer {SELLAUTH_API_KEY}"})
    products = response.json().get('data', [])

    if not products:
        update.message.reply_text("No products found.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(product['name'], callback_data=f"product_{product['id']}")] for product in products]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Select a product to buy:", reply_markup=reply_markup)
    return SELECT_PRODUCT

# === HANDLE PRODUCT SELECTION ===
def handle_product_selection(update, context):
    query = update.callback_query
    query.answer()
    product_id = query.data.split('_')[1]
    context.user_data['product_id'] = product_id

    keyboard = [
        [InlineKeyboardButton("Bitcoin", callback_data="pay_btc")],
        [InlineKeyboardButton("Litecoin", callback_data="pay_ltc")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text("Choose your payment method:", reply_markup=reply_markup)
    return SELECT_PAYMENT

# === HANDLE PAYMENT METHOD SELECTION ===
def handle_payment_selection(update, context):
    query = update.callback_query
    query.answer()
    payment_method = query.data.split('_')[1]
    product_id = context.user_data['product_id']

    # Create invoice using SellAuth API
    invoice_response = requests.post(
        f"https://api.sellauth.com/v1/shops/{SHOP_ID}/invoices",
        headers={"Authorization": f"Bearer {SELLAUTH_API_KEY}"},
        json={"product_id": product_id, "payment_method": payment_method}
    )
    invoice_data = invoice_response.json().get('data', {})

    if not invoice_data:
        query.edit_message_text("❌ Failed to create invoice. Try again later.")
        return ConversationHandler.END

    address = invoice_data.get('wallet_address')
    amount = invoice_data.get('amount')
    invoice_id = invoice_data.get('id')

    context.user_data['invoice_id'] = invoice_id
    context.user_data['payment_method'] = payment_method

    query.edit_message_text(
        f"Send *{amount}* {payment_method.upper()} to the following address:\n\n`{address}`\n\nAfter payment, reply with your *transaction ID*.",
        parse_mode="Markdown"
    )
    return WAIT_PAYMENT

# === HANDLE TRANSACTION ID ===
def handle_transaction_id(update, context):
    txid = update.message.text
    invoice_id = context.user_data.get('invoice_id')

    # Confirm invoice with SellAuth
    confirm_response = requests.post(
        f"https://api.sellauth.com/v1/shops/{SHOP_ID}/invoices/{invoice_id}/confirm",
        headers={"Authorization": f"Bearer {SELLAUTH_API_KEY}"},
        json={"txid": txid}
    )
    confirm_data = confirm_response.json().get('data')

    if confirm_data and 'serials' in confirm_data and confirm_data['serials']:
        serial_key = confirm_data['serials'][0]
        update.message.reply_text(
            f"✅ Payment confirmed! Here's your serial key:\n\n`{serial_key}`",
            parse_mode="Markdown"
        )
    else:
        update.message.reply_text("❌ Payment not verified or failed. Please try again or contact support.")

    return ConversationHandler.END

# === SETUP CONVERSATION HANDLER ===
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        SELECT_PRODUCT: [CallbackQueryHandler(handle_product_selection, pattern='^product_')],
        SELECT_PAYMENT: [CallbackQueryHandler(handle_payment_selection, pattern='^pay_')],
        WAIT_PAYMENT: [MessageHandler(Filters.text & ~Filters.command, handle_transaction_id)],
    },
    fallbacks=[]
)

# === FLASK WEBHOOK ENDPOINT ===
@app.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return 'ok'

# === REGISTER HANDLER ===
dispatcher.add_handler(conv_handler)

# === RUN LOCALLY ===
if __name__ == '__main__':
    app.run(port=5001)
