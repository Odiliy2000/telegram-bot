import requests
import base64
import json
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from config import *

def get_vehicle_data():
    url = "https://api.samsara.com/fleet/vehicles"
    headers = {
        "Authorization": f"Bearer {SAMSARA_API_TOKEN}",
        "X-Samsara-API-Version": "2024-04-01"
    }
    response = requests.get(url, headers=headers)
    return response.json().get("data", [])

def get_location_and_status(vehicle_id):
    url = f"https://api.samsara.com/fleet/vehicles/{vehicle_id}/locations"
    headers = {
        "Authorization": f"Bearer {SAMSARA_API_TOKEN}",
        "X-Samsara-API-Version": "2024-04-01"
    }
    response = requests.get(url, headers=headers)
    data = response.json()
    if data.get("data"):
        latest = data["data"][0]
        return latest["location"], latest.get("reverseGeo", "Unknown"), latest.get("speed", 0), latest.get("time")
    return None, None, None, None

def send_email(to, subject, html_body):
    creds = Credentials.from_authorized_user_file(GMAIL_TOKEN_PATH)
    service = build('gmail', 'v1', credentials=creds)
    message = MIMEText(html_body, 'html')
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    message = service.users().messages().send(userId="me", body={'raw': raw}).execute()
    return message