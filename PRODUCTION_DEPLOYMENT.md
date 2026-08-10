# StegoVault Production Deployment (Render)

## Recommended production architecture

Browser -> HTTPS -> Render -> Gunicorn -> Flask -> SQLite on Render Persistent Disk

This deployment keeps the current application architecture unchanged. The persistent disk stores the database and server-side encryption/session keys. For higher traffic or multi-instance scaling, migrate the database to PostgreSQL in a later hardening sprint.

## 1. Create a GitHub repository

Create a new private GitHub repository, then from this project directory:

```powershell
git init
git add .
git commit -m "StegoVault production release"
git branch -M main
git remote add origin <YOUR_GITHUB_REPOSITORY_URL>
git push -u origin main
```

Do NOT commit `.env`, credentials, or a production database containing real users.

## 2. Create the Render service

1. Sign in to Render.
2. New -> Blueprint.
3. Select the GitHub repository.
4. Render will read `render.yaml`.
5. The service uses Gunicorn and a 1 GB persistent disk.

A persistent disk is required because SQLite, the generated server keys, and the current application data must survive deploys/restarts. If your Render plan does not support persistent disks, do not deploy this SQLite configuration; use PostgreSQL instead.

## 3. Set the production encryption key

The `MESSAGE_ENCRYPTION_KEY` variable is used to wrap each Group's AES-256 key. It must be a valid Fernet key.

Generate one locally:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Copy the output into Render as the value of `MESSAGE_ENCRYPTION_KEY`.

Keep this value permanently. If it is lost, existing Group encryption keys cannot be unwrapped and existing encrypted secret messages cannot be recovered.

`SECRET_KEY` is generated automatically by Render in the Blueprint. Keep it stable after deployment.

## 4. First production startup

Open the Render HTTPS URL. If the persistent database is new, the application redirects to `/admin/setup`.

Create the first Admin account.

Then:

- Register Super User
- Approve Super User from Admin
- Super User creates Group
- Normal User registers
- Normal User requests Group access
- Super User approves User
- User/Super User unlock the Group with Group credentials
- Encode/Decode

## 5. Health check

Render checks:

`/healthz`

A healthy response is HTTP 200 with:

```json
{"status":"ok"}
```

## 6. Important production rules

- Do not commit `instance/`, `.env`, database files, or encryption keys to GitHub.
- Back up the Render persistent disk/database regularly.
- Back up `MESSAGE_ENCRYPTION_KEY` in a secure password manager.
- Never rotate `MESSAGE_ENCRYPTION_KEY` casually. Existing wrapped Group keys depend on it.
- Use HTTPS only for production.
- Keep the Admin account protected with a strong unique password.

## 7. Current production limitation

The current production configuration uses SQLite on a persistent Render disk so the working application can be deployed without changing the proven Sprint 5 data-access layer.

For substantial concurrent traffic, the next hardening step should be PostgreSQL + a proper migration layer. That is recommended before scaling beyond a small/private deployment.
