#!/usr/bin/env python3
"""
send_emails.py

Send personalized emails with attachments from a CSV recipient list.

Features:
- Read recipients from CSV (`email`, `first_name`, `last_name`, optional `attachment`)
- Personalize body using Python `{}` format tokens (e.g. `{first_name}`)
- Retry logic with exponential backoff
- Logging to console and rotating log file
- Uses environment variables for SMTP credentials (secure for Gmail app passwords)

Usage: python send_emails.py --csv example_recipients.csv

"""

import argparse
import csv
import logging
from logging.handlers import RotatingFileHandler
import os
import socket
import smtplib
import ssl
import time
import mimetypes
from email.message import EmailMessage
from pathlib import Path

try:
    from typing import Optional
except Exception:
    pass


LOG_FILE = "send_emails.log"


def setup_logging(level=logging.INFO):
    logger = logging.getLogger("email_sender")
    logger.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    return logger


def load_env_from_dotenv():
    try:
        from dotenv import load_dotenv

        dotenv_path = Path(".env")
        if dotenv_path.exists():
            load_dotenv(dotenv_path)
    except Exception:
        # python-dotenv is optional; skip if unavailable
        return


def read_recipients(csv_path):
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row


def build_message(from_addr, to_addr, subject, body_text, sender_name=None):
    msg = EmailMessage()
    if sender_name:
        msg["From"] = f"{sender_name} <{from_addr}>"
    else:
        msg["From"] = from_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body_text)
    return msg


def attach_file(msg: EmailMessage, file_path: str, logger=None):
    p = Path(file_path)
    if not p.exists():
        if logger:
            logger.warning("Attachment not found: %s", file_path)
        return False

    ctype, encoding = mimetypes.guess_type(str(p))
    if ctype is None:
        ctype = "application/octet-stream"
    maintype, subtype = ctype.split('/', 1)

    with open(p, 'rb') as af:
        data = af.read()
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=p.name)
    return True


def connect_smtp(server, port, username, password, use_ssl, timeout=60, logger=None):
    if use_ssl:
        context = ssl.create_default_context()
        smtp = smtplib.SMTP_SSL(server, port, timeout=timeout, context=context)
    else:
        smtp = smtplib.SMTP(server, port, timeout=timeout)
        smtp.ehlo()
        try:
            smtp.starttls()
            smtp.ehlo()
        except Exception:
            # If starttls fails, continue — some servers don't need it
            pass

    if username and password:
        smtp.login(username, password)
    if logger:
        logger.debug("Connected to SMTP %s:%s (ssl=%s)", server, port, use_ssl)
    return smtp


def send_with_retries(smtp_conn, msg: EmailMessage, max_retries=3, backoff_factor=2, logger=None):
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            smtp_conn.send_message(msg)
            if logger:
                logger.info("Sent to %s", msg["To"])
            return True
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPException, socket.error, ssl.SSLError) as e:
            last_exc = e
            wait = backoff_factor ** (attempt - 1)
            if logger:
                logger.warning("Send attempt %s failed for %s: %s — retrying in %s sec", attempt, msg["To"], e, wait)
            time.sleep(wait)
    if logger:
        logger.error("All retries failed for %s: %s", msg["To"], last_exc)
    return False


def main():
    parser = argparse.ArgumentParser(description="Send personalized emails with attachments from a CSV list.")
    parser.add_argument("--csv", required=True, help="Path to CSV file with recipients")
    parser.add_argument("--subject", help="Email subject (overrides subject in env)")
    parser.add_argument("--template", help="Path to a text file template. If omitted, a built-in template is used.")
    parser.add_argument("--from-name", help="Display name for sender (overrides env)")
    parser.add_argument("--dry-run", action="store_true", help="Do everything except actually send emails")
    parser.add_argument("--max-retries", type=int, default=3, help="Max retry attempts for sending individual emails")
    args = parser.parse_args()

    load_env_from_dotenv()
    logger = setup_logging()

    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    default_subject = os.getenv("EMAIL_SUBJECT", "")
    default_from_name = os.getenv("FROM_NAME", None)

    subject = args.subject or default_subject or "Automated message"
    from_name = args.from_name or default_from_name

    # Template
    if args.template:
        with open(args.template, 'r', encoding='utf-8') as tf:
            template_text = tf.read()
    else:
        template_text = (
            "Hello {first_name},\n\n"
            "This is an automated message.\n\n"
            "Best regards,\n"
            "{sender_name}\n"
        )

    use_ssl = smtp_port == 465

    # Establish SMTP connection (will try to keep open)
    smtp_conn = None
    if not args.dry_run:
        try:
            smtp_conn = connect_smtp(smtp_server, smtp_port, smtp_user, smtp_pass, use_ssl, logger=logger)
        except Exception as e:
            logger.error("Failed to connect/login to SMTP server: %s", e)
            return 1

    total = 0
    sent = 0
    failed = 0

    for row in read_recipients(args.csv):
        total += 1
        email_addr = row.get('email') or row.get('Email')
        if not email_addr:
            logger.warning("Row %s missing 'email' field — skipping", row)
            failed += 1
            continue

        first_name = row.get('first_name') or row.get('FirstName') or row.get('first') or ''
        last_name = row.get('last_name') or row.get('LastName') or ''
        attachment = row.get('attachment') or row.get('Attachment') or ''

        body = template_text.format(first_name=first_name, last_name=last_name, email=email_addr, sender_name=from_name or smtp_user)

        msg = build_message(smtp_user, email_addr, subject, body, sender_name=from_name)

        if attachment:
            attached = attach_file(msg, attachment, logger=logger)
            if not attached:
                logger.warning("Continuing without attachment for %s", email_addr)

        if args.dry_run:
            logger.info("Dry-run: would send to %s", email_addr)
            sent += 1
            continue

        # Try sending with retries; reconnect on fatal disconnects
        success = False
        try:
            success = send_with_retries(smtp_conn, msg, max_retries=args.max_retries, logger=logger)
        except smtplib.SMTPServerDisconnected:
            logger.warning("Server disconnected; attempting reconnect and one more send")
            try:
                smtp_conn = connect_smtp(smtp_server, smtp_port, smtp_user, smtp_pass, use_ssl, logger=logger)
                success = send_with_retries(smtp_conn, msg, max_retries=args.max_retries, logger=logger)
            except Exception as e:
                logger.error("Reconnect/send failed for %s: %s", email_addr, e)
                success = False

        if success:
            sent += 1
        else:
            failed += 1

    if smtp_conn:
        try:
            smtp_conn.quit()
        except Exception:
            pass

    logger.info("Finished. Total: %s sent: %s failed: %s", total, sent, failed)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
