# Sprint 4 — Group Governance & Approval

## Final authority model

- **Admin** is the application-level authority.
- Admin approves/rejects **Super User registration requests**.
- Admin can inspect Group → Super User → Users relationships.
- Admin can disable/remove Users, Super Users, and Groups.
- Admin cannot approve normal Users, add Users to Groups, or read secret messages.
- **Super User** controls their own Group and approves/rejects normal User Group-access requests.
- **User** registers normally, then requests access to a Group using the Group username supplied by the Super User.
- A User receives Group membership only after the owning Super User approves the request.
- Group isolation is enforced server-side for all steganography operations.

## User flow

```text
Normal User registration
        ↓
Request Group access
        ↓
Super User approval
        ↓
Group membership
        ↓
Unlock Group
        ↓
Encode / Decode / Activity
```

## Super User flow

```text
Super User registration
        ↓
Admin review
        ↓
Approve
        ↓
Create Group
        ↓
Approve Group members
```

## Admin visibility

Admin can see:

- account identity and role
- Group name
- Group owner
- Group members
- encode/decode metadata
- image metadata and image preview
- timestamps

Admin cannot see secret message content.
