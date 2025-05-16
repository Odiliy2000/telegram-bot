import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from config import *
from utils import get_vehicle_data, get_location_and_status, send_email
from driver_data import driver_load_map

logging.basicConfig(level=logging.INFO)
last_locations = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send truck number to assign load or type /gtg to send updates.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.message.chat_id

    if text.lower() == 'gtg':
        report = []
        vehicles = get_vehicle_data()
        for truck, load in driver_load_map.items():
            match = next((v for v in vehicles if truck.lower() in v["name"].lower()), None)
            if not match:
                report.append(f"Truck {truck}: Not found in Samsara")
                continue
            vehicle_id = match["id"]
            location, address, speed, _ = get_location_and_status(vehicle_id)
            if not location:
                report.append(f"Truck {truck}: Location not found")
                continue
            subject = f"Load ID: {load}"
            body = f"Update on the load:<br>Current location: {address}<br>Status: Speed {speed} mph<br>We will keep you posted<br>Thank you"
            try:
                send_email(SENDER_EMAIL, subject, body)
                report.append(f"Truck {truck}: Email sent for Load {load}")
            except Exception as e:
                report.append(f"Truck {truck}: Email failed - {str(e)}")

        await update.message.reply_text("\n".join(report))
        driver_load_map.clear()
        return

    # Assume truck number first, then load number
    if 'awaiting_load' not in context.chat_data:
        context.chat_data['current_truck'] = text
        context.chat_data['awaiting_load'] = True
        await update.message.reply_text("Now enter load number:")
    else:
        driver_load_map[context.chat_data['current_truck']] = text
        await update.message.reply_text(f"Saved: {context.chat_data['current_truck']} -> Load {text}")
        context.chat_data.pop('awaiting_load')

async def check_stopped_drivers(bot):
    await asyncio.sleep(5)
    while True:
        logging.info("Checking for stopped drivers...")
        vehicles = get_vehicle_data()
        now = datetime.utcnow()
        for vehicle in vehicles:
            vehicle_id = vehicle['id']
            location, address, speed, timestamp = get_location_and_status(vehicle_id)
            if not timestamp:
                continue
            seen_time = datetime.utcfromtimestamp(timestamp / 1000)
            key = str(vehicle_id)

            if speed == 0:
                if key in last_locations and last_locations[key]['address'] == address:
                    stopped_duration = now - last_locations[key]['timestamp']
                    if stopped_duration >= timedelta(hours=STOP_THRESHOLD_HOURS):
                        await bot.send_message(chat_id=SENDER_EMAIL, text=f"Alert: {vehicle['name']} stopped 3+ hours at {address}")
                else:
                    last_locations[key] = {'address': address, 'timestamp': seen_time}
            else:
                last_locations.pop(key, None)

        await asyncio.sleep(CHECK_INTERVAL_MINUTES * 60)

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.create_task(check_stopped_drivers(app.bot))
    app.run_polling()

if __name__ == '__main__':
    main()