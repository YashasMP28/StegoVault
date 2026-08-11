# StegoVault

StegoVault is a private, group-restricted image steganography web application.

## Architecture

- Python + Flask
- HTML5 + CSS3 + JavaScript
- PostgreSQL in production; SQLite remains available for local development
- Role-based access: ADMIN / SUPER_USER / USER
- Group-based authorization
- AES-256-GCM encrypted secret payloads
- 2-bit LSB image steganography
- Gunicorn for production serving
- Render deployment with managed PostgreSQL

## Security model

```text
ADMIN
  ├─ approves Super Users
  ├─ manages Groups/accounts
  └─ sees metadata, not secret messages

SUPER_USER
  ├─ owns a Group
  ├─ enters the Group using Group credentials
  └─ approves/rejects normal User access

USER
  ├─ registers
  ├─ requests Group access
  └─ enters Group credentials after approval
```

Secret message flow:

```text
Secret message
      ↓
AES-256-GCM
      ↓
Encrypted payload
      ↓
2-bit LSB
      ↓
Stego image
```

## Local development

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Without `DATABASE_URL`, the app uses `instance/stegovault.db` locally.

## Render demo deployment

Push to GitHub and create a Render Blueprint using `render.yaml`.

The Blueprint creates a Free Flask web service and Free PostgreSQL database. Supply `MESSAGE_ENCRYPTION_KEY` as a secret in Render.

The Free PostgreSQL database is intended for demonstration/testing and expires after 30 days. Upgrade before long-term production use.
