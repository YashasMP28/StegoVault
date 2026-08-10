# StegoVault — Private Group-Based Image Steganography

StegoVault is a Flask web application for private image steganography with authenticated users, Admin/Super User/User roles, isolated Groups, and encrypted secret-message storage.

## Current sprint structure

### Sprint 1 — Private Web Application
- Flask backend
- HTML/CSS/JavaScript frontend
- Registration and login
- 2-bit LSB image steganography
- AES-256-GCM encrypted hidden payloads (STEGv3)
- UTF-8 messages
- PNG output
- Image utilities

### Sprint 2 — Hierarchical Access Control
- Admin → Super User → Group → User hierarchy
- Admin approval for Super User requests
- Group credentials
- Group membership
- Backend-enforced Group isolation
- Group activity/audit
- Admin metadata-only access to steganography activity
- Admin cannot retrieve secret messages
- Super Users can access content/activity for their own Group


### Sprint 5 — AES-256-GCM Secure Steganography
- Secret message is encrypted **before** it is embedded in the image.
- New payload format: `STEGv3`.
- AES-256-GCM provides confidentiality and tamper detection.
- Every encode uses a fresh random 96-bit nonce.
- Every Group has a unique 256-bit encryption key.
- The Group ID is authenticated as associated data, preventing cross-Group decryption.
- Existing `STEGv2` images remain readable for compatibility; all new images use `STEGv3`.
- Admin can still view audit/image metadata, but cannot use secret-message endpoints.

### Sprint 3 — Registration, Identity & Password Policy
- First name
- Unique username
- Mobile number
- Email validation
- Strong password policy for all account roles
- Normal User / Super User request selection during registration
- Company / Group name for Super User requests
- Required business purpose/description for Admin review
- Admin request screen with applicant identity and purpose
- Strong Group access passwords
- Automatic SQLite schema upgrade for existing Sprint 2 databases

## Password policy

Every account password must contain:

- At least 8 characters
- 1 uppercase letter
- 1 lowercase letter
- 1 number
- 1 special character
- No spaces

The Group access password follows the same policy.

## Registration flow

### Normal User

`Register → Account created → Login → Wait for Group assignment`

Required:
- First name
- Username
- Mobile
- Email
- Password

No Group name is required.

### Super User request

`Register → Select Super User → Company/Group name + business purpose → Account created → Admin review → Approve/Reject`

Approval changes the account role to `SUPER_USER`.

## Run locally

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Open:

`http://127.0.0.1:5000`

## Admin bootstrap

Set these environment variables before first startup:

```text
ADMIN_NAME=StegoVault Admin
ADMIN_USERNAME=admin
ADMIN_MOBILE=+919876543210
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=AdminPass1!
```

`ADMIN_PASSWORD` must satisfy the same strong-password policy.

## Security model

### Admin
Can manage application accounts, approve Super Users, inspect Groups and audit metadata. Admin cannot read/decrypt secret messages.

### Super User
Can manage only Groups they own and the registered users assigned to those Groups. Super Users can view secret content inside their own Group.

### User
Can access only Groups in which they are an active member.

The backend checks Group membership/ownership for every protected Group operation; changing a URL or API parameter does not bypass isolation.

## Secret messages

Secret messages are not stored as plaintext in the activity table. They are encrypted with Fernet using `MESSAGE_ENCRYPTION_KEY`.

Admin-facing audit queries deliberately exclude the encrypted message field and there is no Admin secret-message endpoint.

## Secure payload details

A new encoded image contains a random nonce and authenticated AES-GCM ciphertext inside the LSB payload. Extracting the LSB data without the correct Group key produces ciphertext, not the original message. Any modification to the encrypted payload causes GCM authentication to fail.

The cover image is intentionally **not** encrypted as a whole because StegoVault must remain a normal viewable image after encoding. The secret content is encrypted before hiding.

Keep `instance/.message.key` private. In production, provide `MESSAGE_ENCRYPTION_KEY` through the deployment secret manager/environment instead of committing local key files.

## Production

Run with Gunicorn:

```bash
gunicorn app:app
```

For production, use:
- Persistent PostgreSQL for accounts/groups/activity
- Strong `SECRET_KEY`
- Strong `MESSAGE_ENCRYPTION_KEY`
- HTTPS
- Secure deployment environment variables

`render.yaml` is included as a deployment starting point.


## First-run Admin setup

The application no longer requires ADMIN_EMAIL/ADMIN_PASSWORD environment variables. On a fresh database, opening the app redirects to `/admin/setup`. Create the first Admin using the same password policy as every other account. Once an active Admin exists, `/admin/setup` is permanently closed and normal registration becomes available.

## Sprint 4 update

Normal Users are approved into Groups by the owning Super User. Admin only approves Super User requests and manages/removes Groups and accounts. Admin never receives secret message content.
