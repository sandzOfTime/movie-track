import hashlib
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
import httpx
from .db import normalized


def send(channel: str, recipient: str, body: str):
    if channel == "email" and os.getenv("EMAIL_PROVIDER", "resend") == "resend":
        with httpx.Client(timeout=30) as client:
            response = client.post("https://api.resend.com/emails",
                headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"]},
                json={"from": os.environ["EMAIL_FROM"], "to": [recipient],
                      "subject": "Movie showtime alert", "text": body})
            response.raise_for_status()
    elif channel == "email" and os.getenv("EMAIL_PROVIDER") == "smtp":
        message = EmailMessage()
        message["From"] = os.environ["SMTP_FROM"]
        message["To"] = recipient
        message["Subject"] = "Movie showtime alert"
        message.set_content(body)
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=30) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if os.getenv("SMTP_USERNAME"):
                smtp.login(os.environ["SMTP_USERNAME"], os.environ["SMTP_PASSWORD"])
            smtp.send_message(message)
    elif channel == "whatsapp":
        account = os.environ["TWILIO_ACCOUNT_SID"]
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account}/Messages.json",
                auth=(account, os.environ["TWILIO_AUTH_TOKEN"]),
                data={"From": os.environ["TWILIO_WHATSAPP_FROM"], "To": recipient, "Body": body})
            response.raise_for_status()
    else:
        raise ValueError("Unsupported alert channel or email provider")


def alert(db, request, sender=send) -> dict:
    matches = db.matches(request)
    sent, skipped = 0, 0
    for show in matches:
        identity = [request.channel, request.recipient, normalized(show["movie"]),
                    normalized(show["cinema"]), normalized(show["theater_type"]), show["starts_at"]]
        key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        # Serialize checks across processes, including cron and API workers.
        with db.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM deliveries WHERE delivery_key=?", (key,)).fetchone():
                skipped += 1
                continue
            if request.dry_run:
                continue
            body = (f'{show["movie"]} — {show["cinema"]} ({show["theater_type"]})\n'
                    f'Showtime: {show["starts_at"]} (UTC)\nSource: {show["source"]}')
            sender(request.channel, request.recipient, body)
            connection.execute("INSERT INTO deliveries VALUES(?,?)", (key, datetime.now(timezone.utc).isoformat()))
            sent += 1
    return {"matches": matches, "sent": sent, "already_sent": skipped, "dry_run": request.dry_run}
