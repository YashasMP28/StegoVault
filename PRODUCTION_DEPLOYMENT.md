# StegoVault — Free Demo Deployment on Render

This version uses **Render Free Web Service + Render Free PostgreSQL**. It does not use a persistent disk.

## Why PostgreSQL

Render Free web services have an ephemeral filesystem. A local SQLite database would be lost when the service restarts, redeploys, or spins down. Render provides Free PostgreSQL for persistent relational data, although the Free database expires after 30 days.

## Render Blueprint

`render.yaml` creates:

- `stegovault` — Free Python web service
- `stegovault-db` — Free PostgreSQL database
- `DATABASE_URL` — automatically connected to the web service
- generated `SECRET_KEY`
- `MESSAGE_ENCRYPTION_KEY` supplied privately in the Render Dashboard

## Deploy

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint**.
3. Select the GitHub repository.
4. Render reads `render.yaml`.
5. Choose the Free instance types when prompted.
6. Enter a new `MESSAGE_ENCRYPTION_KEY` in the Render Dashboard.
7. Deploy.

Generate the encryption key locally with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Never commit that value to GitHub.

## First production login

The database starts empty. Open the live URL and use the first-run Admin setup page to create the production Admin.

Do not upload your local SQLite database to GitHub or Render.

## Health check

`GET /healthz` verifies both the Flask process and PostgreSQL connection.

## Important Free-tier limitations

- Free web service sleeps after 15 minutes without inbound traffic.
- The first request after sleep can take about a minute to wake the service.
- Free PostgreSQL is 1 GB.
- Free PostgreSQL expires 30 days after creation, with a 14-day upgrade grace period.
- Free web services cannot use persistent disks.

This configuration is intended for a **client demo / evaluation deployment**, not permanent production hosting. Upgrade the database and web service before using it for long-term real users.
