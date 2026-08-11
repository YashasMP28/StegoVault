# Sprint 3 — Registration, Identity & Password Policy

## Implemented

### Registration fields
Every newly registered account now requires:
- First name
- Unique username
- Mobile number
- Email address
- Strong password
- Confirm password

### Super User registration request
The registration page has an account-type choice:
- Normal User
- Super User request

Selecting **Super User** additionally requires:
- Company / Group name
- Purpose / description for Admin

A Super User request remains `PENDING` until an Admin approves it. Approval changes the user's role to `SUPER_USER`; rejection leaves the account as a normal `USER`.

Normal users do not need a Group name during registration.

### Email validation
The backend validates email syntax and the browser uses `type=email` as an additional client-side check.

### Mobile validation
The backend accepts a `+` followed by 10–15 digits (or 10–15 digits without `+`).

### Password policy
The same password policy is enforced for every user account, including the Admin bootstrap account:
- Minimum 8 characters
- At least 1 uppercase letter
- At least 1 lowercase letter
- At least 1 number
- At least 1 special character
- No spaces

The same strong-password rule is also applied to Group access passwords.

### Admin review
The Admin dashboard now shows, for pending Super User requests:
- First name
- Username
- Mobile
- Email
- Company / Group name
- Business purpose / description
- Approve / Reject controls

This lets Admin understand the reason for the request before granting Super User privileges.

### Database upgrades
Existing Sprint 2 SQLite databases are upgraded automatically with:
- `users.first_name`
- `users.username`
- `users.mobile`
- `superuser_requests.group_name`
- `superuser_requests.description`
- `groups.description`

Existing accounts are retained. Legacy usernames are generated automatically for old records that did not have a username.

## Recommended production setup
Use a persistent PostgreSQL database for deployed user accounts. Keep `SECRET_KEY` and `MESSAGE_ENCRYPTION_KEY` in deployment secrets/environment variables.
