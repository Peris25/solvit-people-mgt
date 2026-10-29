# Forgot password — 29 October 2026

## Functionality

- Login links to an anonymous Forgot password page. Eligible active accounts receive a one-use link to choose a new password; responses never confirm whether an email/account exists.
- Reset tokens contain 256 random bits, expire after 15 minutes and are stored only as SHA-256 hashes. A new request invalidates the previous link. Password, email, role or session-invalidation changes invalidate outstanding links.
- The reset link uses an HTTPS `FRONTEND_URL` and a URL fragment, not a request Host header or query credential. The frontend removes the fragment on entry and does not store the token in browser storage.
- Completion enforces existing password length/common-password/history checks and the bcrypt byte limit, updates the password with an optimistic concurrency check, consumes the link, and invalidates old access/refresh sessions. There is no automatic login or role/MFA change. A successful reset fulfills a pending first-login password change because a new policy-compliant password has actually been set.
- Mongo-backed request/completion limits and the existing persistent integrity lock protect independent workers. Unknown, duplicate and disabled accounts receive the same request response. Only the actual recovery handlers are exempted from the global session gate; existing protected routes stay protected.

## Email security and configuration

- Reuses the existing SMTP/Sender.net email service and the password-reset template category. Recovery email content uses a fixed trusted security message.
- Delivery runs as an in-process event after the generic response. Reset email uses the production delivery bucket, never the testing/Mailtrap bucket. `OUTBOUND_EMAIL_ENABLED=false` is honored; scheduled-job flags do not suppress an explicitly requested recovery event.
- Raw links are never placed in the retry queue, email logs or audit logs. Provider failure text is redacted for sensitive email. Delivery failure/interruption leaves the link unusable; the user requests a fresh link.
- Production requires `FRONTEND_URL=https://people.solvit.co.ke`, enabled outbound mail and a working verified production email sender in the existing delivery configuration. No existing secrets were read, printed or changed. No live recovery emails were sent during development.
- An actual mailbox delivery/reset must be verified by its owner after deployment. Password entry and submission are an operator handoff; do not reset a real employee account for QA without approval.

## Data and rollout

The application creates `password_resets` (one row per account) and `password_reset_limits` (hashed limiter keys) on first use. Mongo's existing `_id` uniqueness is sufficient for correctness; no migration or production index installation was run. Expiry is checked in code, independently of cleanup. Expired limiter/security-record retention should follow the approved operational retention policy; no historical employee records are touched.

The reset routes belong to existing authentication, not a new login/account-provisioning system. Existing accounts, first-login restrictions, MFA configuration and notification modules are preserved. Account provisioning remains a separate workflow.

## Validation

- Backend: 1,244 passed; 321 existing integration/environment skips and five existing warnings.
- Frontend: 240 passed across 32 suites.
- Tests cover unknown/disabled/ambiguous accounts, delivery-disabled configuration, generic responses, trusted origins, hashed storage, expiry, replay, concurrent consumption, changed identity/credentials, password history and limits, old-session invalidation, unchanged MFA state, anonymous HTTP routing, transport retry/log privacy, and frontend success/error/mismatch states.
- Strict production build, Python compilation and whitespace checks passed. Full regression suites used synthetic repositories and mocked mail transport only; no production database or account was changed.
