Email Sender Bot
================

Files added:
- `send_emails.py` — main script to send personalized emails with attachments.
- `.env.example` — sample environment file (copy to `.env` and fill in your credentials).
- `example_recipients.csv` — example CSV of recipients.

Quick usage
-----------

1. Create a `.env` file (or set environment variables). For Gmail, use an App Password (requires 2FA on the account):

   - Create an App Password: Google Account > Security > App passwords > generate for Mail.
   - Put the app password into `SMTP_PASSWORD` (do not commit this file).

   Example `.env` (copy `.env.example` to `.env` and edit):

   ```powershell
   $env:SMTP_USER = "your.email@gmail.com"
   $env:SMTP_PASSWORD = "your_app_password"
   ```

   Or create `.env` text file with the same key=value lines as `.env.example`.

2. Prepare a CSV with headers: `email,first_name,last_name,attachment`.

3. Run the script (Windows PowerShell examples):

   ```powershell
   # dry-run to verify without sending
   python .\send_emails.py --csv .\example_recipients.csv --dry-run

   # actually send
   python .\send_emails.py --csv .\example_recipients.csv
   ```

Options
-------

- `--template FILE`: a text file template using Python format tokens, e.g. `Hello {first_name}`.
- `--subject`: override default subject.
- `--from-name`: override `FROM_NAME` env var.
- `--max-retries`: number of retries (default 3).

Security notes
--------------

- Use an App Password for Gmail. Do NOT store your real password in repo files.
- Consider using `python-dotenv` to load `.env` for local development (`pip install python-dotenv`). The script will silently skip loading `.env` if `python-dotenv` isn't installed.

Logging
-------

Script writes a rotating log file `send_emails.log` alongside the script.

Next steps
----------

- Optionally add HTML body support, CSV templating columns, or parallel sending for large lists.
