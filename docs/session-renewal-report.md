# Silent session renewal — 4 November 2026

Root cause: access tokens expire after at most 15 minutes, but the frontend
redirected immediately on HTTP 401 without using the existing refresh endpoint.
AuthContext also cleared sign-in state on temporary network/server errors.

The shared session helper now renews expired access using the existing HttpOnly
refresh cookie, then retries the original protected request once. Concurrent
requests share one renewal; Web Locks serialize cookie rotation across tabs on
supporting HTTPS browsers. Browsers without Web Locks retain per-tab single-flight
renewal; cross-tab simultaneous expiry can still require reauthentication there.
No tokens are stored in localStorage: the existing sign-in hint is retained.

API requests and authenticated account/security requests use renewal. Login,
logout, password recovery and public endpoints do not trigger automatic retries.
Permission/MFA/password-change denials do not bypass their existing gates.
Failed refresh due to expiry/revocation ends the UI session. Network/503 failures
retain the sign-in and expose an error/retry state. Logout clears local state
immediately and blocks replay after an in-flight refresh completes.

Backend token expiry, absolute session age, MFA requirements, deactivation,
password changes and revocation remain unchanged. This does not provide an
unlimited session: configured absolute expiry still requires sign-in.

Validation: all 297 frontend tests in 41 suites passed; strict CI build, normal
production build and whitespace checks passed. No backend code was changed.

Regression coverage includes concurrent refresh, one retry, revocation, transient
outages, MFA denial, browser locking, logout during refresh, invalid login and
AuthContext session restoration. No production credentials or accounts changed.
