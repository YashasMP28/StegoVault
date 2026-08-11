# Sprint 5 — Secure Steganography

## Security upgrade

New encoded images use **AES-256-GCM** before the encrypted payload is embedded with 2-bit LSB steganography.

- Every encode operation gets a fresh random 96-bit nonce.
- AES-GCM provides confidentiality and tamper detection.
- The ciphertext is authenticated with Group-specific associated data.
- Every Group has its own random 256-bit encryption key.
- Group keys are wrapped with the server-only encryption key at rest.
- A secure image created for Group A cannot be decrypted in Group B.
- Existing `STEGv2` images remain readable for backward compatibility; new images are always `STEGv3`.
- Admin can still view image/audit metadata, but the hidden plaintext is not exposed through Admin endpoints.

## Important

Keep `instance/.message.key` secure. It protects stored secret-message records and Group encryption keys. For production, set a strong `MESSAGE_ENCRYPTION_KEY` environment variable and do not commit local key files.

## Payload

`STEGv3 | Group ID | random nonce | ciphertext length | AES-GCM ciphertext + tag`

The image itself remains visually usable; the secret content is encrypted before being hidden.
