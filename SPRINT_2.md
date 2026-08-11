# StegoVault Sprint 2 — Hierarchical Access Control

Implemented:
- ADMIN / SUPER_USER / USER roles
- Admin approval workflow for Super User requests
- Super User group creation
- Group username + password (second-layer group access after personal login)
- Group membership management
- Strict backend group isolation
- Group-scoped encode/decode/activity
- Admin metadata-only audit access; secret messages are not returned to Admin APIs/UI
- Server-side encryption for stored secret-message activity
- CSRF protection for state-changing requests
- Admin account bootstrap through environment variables
- Admin dashboard
- Super User dashboard
- Group workspace for normal users

## Local admin setup
Before first run, set ADMIN_EMAIL and ADMIN_PASSWORD. On startup the configured account is created/promoted to ADMIN.

## Security note
`MESSAGE_ENCRYPTION_KEY` must be kept secret. In production use a managed secret and a persistent database/storage. The local `.message.key` file is only a development fallback.

## Group login model
Each person keeps an individual StegoVault account for accountability. A Group also has its own access username/password, which a member must provide to unlock that Group workspace. This preserves the requirement for Group credentials without losing per-user audit identity.
