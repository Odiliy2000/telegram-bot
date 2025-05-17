import imaplib
import smtplib
import email
import requests
import re
from email.mime.text import MIMEText
from email.utils import make_msgid
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
EMAIL_USER = "adam@alistarincoh.com"
EMAIL_PASS = "kimc cosr nahz goya"
IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SAMSARA_API_TOKEN = "samsara_api_2NI0rRVo0DqNZH9krQNGwcPHVry4y4"
OPENCAGE_API_KEY = "43d8196cca694186a7df235c524e869d"
TELEGRAM_BOT_TOKEN = "7789216570:AAHLFmAPL5fbwgbc29zzKZ1MxkRayiv6Xh8"
ALLOWED_USER_IDS = [7776804235, 
                    6943427259,
                    6342251602, 
                    7833340802, 
                    7435374099,
                    5132391422, #thomas
                    ]

TRUCK_DRIVER_MAP = {
    '009': '281474978944642',
    '042': '281474995054937',
    '054': '281474995764559',
    '2500': '281474995780100',
    '555': '281474991080555',
    '573171': '281474979060907',
    '032': '281474991993401',
    '030': '281474991995190',
    '018': '281474980704662',
    '124': '281474979960296',
    '038': '281474995070373',
    '001': '281474994261580',
    '025': '281474979659450',
    '707965': '281474978863240',
    '115': '281474995646127',
    '036': '281474994765665',
    '102': '281474994946629',
    '022': '281474981735235',
    '888': '281474992444725',
    '99082': '281474979285065',
    '666': '281474981667239',
    '1848': '281474995500141',
    '006': '281474994583690',
    '033': '281474992196654',
    '028': '281474992027036',
    '222': '281474994947028',
    '233370': '281474995201038',
    '90079': '281474978858793',
    '029': '281474991994522',
    '016': '281474995201048',
    '589438': '281474981625483',
    '127': '281474995397266',
    '037': '281474994689863',
    '418': '281474992158458',
    '775973': '281474979305083',
    '031': '281474994907529',
    '0556': '281474995130898',
    '776276': '281474990169622',
    '027': '281474981563806',
    '777': '281474991063825',
    '521431': '281474992983936',
    '333': '281474992696991',
    '035': '281474994552453',
    '578269': '281474993730063',
    '444': '281474978901870',
    '020': '281474987549157',
    '040': '281474995049573',
    '125': '281474994058226',
    '1212': '281474995201041',
    '2246': '281474995260728',
    '776099': '281474988663979',
    '770334': '281474991623120',
    '023': '281474982022211',
    '01': '281474991824916',
    '786': '281474995532164',
    '148733': '281474992642466',
    '773413': '281474990034059',
    '708222': '281474995853035',
    '1044': '281474995470851',
    '126': '281474994060550',
    '244265': '281474995492019',
    '0015': '281474994727060',
    '041': '281474992599111',
    '776098': '281474978472665',
    '045': '281474994149593',
    '123': '281474992917798',
    '021': '281474986847993',
    '110': '281474986046973',
    '169': '281474985945439',
    '91032': '281474983526113',
    '008': '281474978731044',
    '005': '281474978472662',
    '1111': '281474992357664',
    '9595': '281474979103386',
    '215': '281474993126073',
    '111' : '281474982990229',
    # Add more as needed
}

sessions = {}

def get_vehicle_location_and_speed(driver_id):
    headers = {
        "Authorization": f"Bearer {SAMSARA_API_TOKEN}",
        "X-Samsara-API-Version": "2024-04-01"
    }
    url = f"https://api.samsara.com/fleet/vehicles/locations?vehicleIds={driver_id}"
    response = requests.get(url, headers=headers)
    if response.ok:
        data = response.json()
        vehicle = data.get("data", [None])[0]
        if not vehicle:
            return None
        loc = vehicle.get("location", {})
        return {
            "lat": loc.get("latitude"),
            "lon": loc.get("longitude"),
            "speed": loc.get("speed")
        }
    return None

def reverse_geocode(lat, lon):
    url = f"https://api.opencagedata.com/geocode/v1/json?q={lat}+{lon}&key={OPENCAGE_API_KEY}"
    resp = requests.get(url)
    if resp.ok:
        data = resp.json()
        if data["results"]:
            return data["results"][0]["formatted"]
    return f"{lat}, {lon}"

def find_latest_message_with_load_id(imap_conn, load_id):
    imap_conn.select("INBOX")
    result, data = imap_conn.search(None, f'(SUBJECT "{load_id}")')
    if result != "OK" or not data or not data[0]:
        return None
    msg_ids = data[0].split()
    last_two = msg_ids[-2:] if len(msg_ids) >= 2 else msg_ids
    delivered_count = 0
    for msg_id in last_two:
        result, msg_data = imap_conn.fetch(msg_id, "(RFC822)")
        if result != "OK":
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                body = part.get_payload(decode=True).decode(errors='ignore')
                if "load has been delivered successfully" in body.lower():
                    delivered_count += 1
    if delivered_count == len(last_two):
        return "DELIVERED"
    result, msg_data = imap_conn.fetch(msg_ids[-1], "(RFC822)")
    if result != "OK":
        return None
    return email.message_from_bytes(msg_data[0][1])

def reply_all_smtp(original_msg, subject, body_text):
    from_email = email.utils.parseaddr(original_msg.get("From", ""))[1]
    to_emails = email.utils.getaddresses(original_msg.get_all("To", []))
    cc_emails = email.utils.getaddresses(original_msg.get_all("Cc", []))
    reply_to_emails = email.utils.getaddresses(original_msg.get_all("Reply-To", []))

    all_recipients = set()
    for name, addr in to_emails + cc_emails + [(None, from_email)] + reply_to_emails:
        if addr and addr.lower() != EMAIL_USER.lower():
            all_recipients.add(addr)

    msg = MIMEText(body_text, "html")
    msg['Subject'] = f"Re: {subject}"
    msg['From'] = EMAIL_USER
    msg['To'] = ", ".join(all_recipients)
    msg['Message-ID'] = make_msgid()
    msg['In-Reply-To'] = original_msg.get("Message-ID")
    msg['References'] = original_msg.get("Message-ID")

    with smtplib.SMTP_SSL(SMTP_SERVER, 465) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.sendmail(EMAIL_USER, list(all_recipients), msg.as_string())

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("You are not authorized to use this bot.")
        return
    sessions[user_id] = []
    await update.message.reply_text("Welcome! Type the beginning of a truck number to search for a driver.\nType /cancel to reset.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in ALLOWED_USER_IDS:
        return

    text = update.message.text.strip().upper()
    session = sessions.setdefault(user_id, [])

    if text == "/CANCEL":
        sessions[user_id] = []
        await update.message.reply_text("Session canceled. Start again.")
        return

    if text == "GTG":
        if not session:
            await update.message.reply_text("No driver/load pairs entered.")
            return

        imap_conn = imaplib.IMAP4_SSL(IMAP_SERVER)
        imap_conn.login(EMAIL_USER, EMAIL_PASS)
        results = []

        for truck_number, load_id in session:
            if truck_number not in TRUCK_DRIVER_MAP:
                results.append(f"❌ {truck_number}: Driver not found.")
                continue
            driver_id = TRUCK_DRIVER_MAP[truck_number]
            vehicle_data = get_vehicle_location_and_speed(driver_id)
            if not vehicle_data:
                results.append(f"❌ {truck_number}: No driver data on Samsara.")
                continue
            if vehicle_data['speed'] == 0:
                results.append(f"❌ {truck_number}: Vehicle stopped.")
                continue
            msg_obj = find_latest_message_with_load_id(imap_conn, load_id)
            if msg_obj == "DELIVERED":
                results.append(f"✅ {truck_number}: Already delivered.")
                continue
            if not msg_obj:
                results.append(f"❌ {truck_number}: No mail chain found for Load ID {load_id}.")
                continue

            subject = msg_obj["Subject"]
            address = reverse_geocode(vehicle_data['lat'], vehicle_data['lon'])
            status = "rolling" if vehicle_data['speed'] >= 50 else "rolling slowly due to the traffic"
            body = (
                f"Update on the load:{load_id} <br>"
                f"Current location: {address}<br>"
                f"Status: {status}<br>"
                "We will keep you posted<br>"
                "Thank you"
            )
            reply_all_smtp(msg_obj, subject, body)
            results.append(f"✅ {truck_number}: Email sent for Load ID {load_id}")

        await update.message.reply_text("\n".join(results))
        sessions[user_id] = []
        return

    if not session or isinstance(session[-1], tuple):
        if text in TRUCK_DRIVER_MAP:
            session.append(text)
            await update.message.reply_text(f"Enter load number for driver {text}:")
        else:
            matches = [d for d in TRUCK_DRIVER_MAP if d.startswith(text)]
            if matches:
                await update.message.reply_text(
                    "Matching drivers:\n" + "\n".join(f"- {m}" for m in matches) + "\nType full truck number to select."
                )
            else:
                await update.message.reply_text("No matching drivers found. Try again.")
        return

    if session and session[-1] in TRUCK_DRIVER_MAP:
        truck_number = session.pop()
        session.append((truck_number, text))
        await update.message.reply_text("Driver/load pair added. Enter another truck number or type 'gtg' to send updates.")

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()

if __name__ == "__main__":
    main()
