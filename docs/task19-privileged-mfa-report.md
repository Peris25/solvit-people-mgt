# Task 19 - Privileged MFA and session security

Local implementation, 17 October 2026. No production access, account changes, migrations, indexes, commit, push or deployment. Task 01 commit `83f0b4f` and all existing work are preserved; HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`.

## Audit and requirement alignment

Reviewed Task 17/18 reports, the existing authentication/access matrix and authoritative reference requirements. The Developer Brief requires privileged MFA for HR administration, Finance, IT and Executive access. HR Admin, HR Manager, Finance, IT Admin and Executive accounts are covered, including inherited custom roles and equivalent sensitive Full grants. Ordinary line managers, Board, employees and Solvers are not automatically reclassified; effective elevated grants still trigger privileged treatment. FRD encryption requirements are met by AES-256-GCM secret encryption. This does not approve unrelated outstanding HR policy decisions.

Previously password-only tokens could exercise privileged permissions; no usable MFA enrollment/recovery existed. Password lockout was process-local. Existing password-change enforcement and logout family revocation were retained. No implemented password-reset API was found; an email template does not establish a safe recovery workflow, so no password-only reset bypass was invented.

## Implemented functionality

- Authenticator-app TOTP using [RFC 6238](https://www.rfc-editor.org/rfc/rfc6238): six digits, 30-second steps, one-step clock allowance, persistent monotonic counter replay protection. Manual setup avoids sending secrets to external QR providers. No external MFA/SMS service or dependency was added.
- Enrollment requires current password; setup expires after five minutes. Existing authenticator remains active during replacement. Secrets are authenticated AES-256-GCM ciphertext bound to account and tenant; recovery codes have 128 random bits each and are stored only as account-bound hashes. Ten codes are shown once. Codes/secrets are absent from audit/status/previews and browser persistent storage.
- Enrolled accounts always require MFA, even in optional rollout mode. Correct passwords issue restricted sessions until verification. Backend dependency enforcement gates protected functionality, including alternate routes and old tokens. Password-first sessions retain Task 02's minimal identity and forced-change workflow; completing the password change does not grant an MFA exemption.
- Partial challenges expire after five minutes from original session start; refresh cannot extend or upgrade them. Successful verification replaces/revokes the restricted session. Recovery codes are single-use second factors, not password replacements. Sensitive factor/recovery changes require current password and MFA verified within five minutes.
- Five failed MFA proofs or known-account passwords cause persistent 15-minute cooldowns, serialized across workers. Existing per-IP login protection remains. MFA state and login limits use existing MongoDB `_id` uniqueness in `auth_mfa` and `auth_login_limits`; no index installation or historical rewrite.
- Verified IT may reset another same-tenant account only with recent MFA, current password and support reference. Self-reset is rejected. Reset invalidates sessions and forces re-enrollment even in optional mode. There is no disable-MFA or password-only recovery endpoint. Support references attest operator process; they do not verify an external ticket approval.
- Access tokens are capped at 15 minutes, including older long-lived tokens. Refresh defaults to 12 hours, capped at 24 hours. Original session age is preserved: privileged sessions have an eight-hour absolute maximum, ordinary staff 12 hours and Solvers 24 hours, also subject to refresh expiration.
- Password state, role, account activation, session cutoff and MFA generation are checked against live state. Role changes/deactivation persist a cutoff atomically. Signed cutoff snapshots prevent in-flight issuance races. Refresh rechecks inside the integrity lock. Logout, password changes and factor reset/replacement invalidate affected sessions.
- Branded enrollment/verification/recovery screens, account-security navigation and IT-assisted reset UI. Partial sessions do not load private layout or notification data. API MFA-required responses move the UI to the gate; backend remains authoritative.

## Task 19 files

New: `backend/utils/mfa.py`, `backend/routes/mfa_routes.py`, `backend/tests/test_privileged_mfa.py`, `frontend/src/pages/MfaSecurity.js`, `frontend/src/pages/MfaSecurity.test.js`, this report.

Updated: `backend/utils/auth.py`, `backend/routes/auth_routes.py`, `backend/server.py`, `backend/routes/access.py`, `backend/utils/lifecycle_workflows.py`, `backend/scripts/local_test_server.py`, `backend/tests/integrity_fakes.py`, `backend/tests/test_password_change_enforcement.py`; `frontend/src/App.js`, `frontend/src/components/Layout.js`, `frontend/src/components/Sidebar.js`, `frontend/src/context/AuthContext.js`, `frontend/src/context/AuthContext.test.js`, `frontend/src/context/NotificationContext.js`, `frontend/src/context/NotificationContext.test.js`, `frontend/src/services/api.js`, `frontend/src/services/api.test.js`.

Other uncommitted files belong to preserved earlier work. Dependency manifests were not changed; cryptography 47.0.0 is already declared and was used for final validation.

## Validation

Final validation on the completed source:

| Check | Result |
| --- | --- |
| Full backend (`backend/tests tests`, guarded localhost integration API and real MongoDB) | **1,347 passed**, no failures or skips; five existing deprecation warnings; 316.25 seconds |
| Full frontend | **198 passed**, 29 suites; no failures; 6.36 seconds |
| Strict CI build (`CI=true`) | Passed, compiled successfully |
| Normal production build (`CI=false`) | Passed, compiled successfully |
| Python `compileall backend` | Passed |
| `git diff --check` and new-file trailing-whitespace checks | Passed; existing LF/CRLF conversion notices only |

 Coverage includes RFC vectors, encryption/tamper/binding/key rotation, enrollment expiry, invalid/replayed codes, single-use recovery, concurrent real-Mongo consumption, persistent lockouts, refresh and legacy token bypasses, permission changes, password-first completion, normal staff/Solver login, IT reset boundaries, audit failures and notification isolation. The existing first-password legacy test remains; forged-role rejection has a separate 401 test.

## Configuration and controlled rollout

- `MFA_ENCRYPTION_KEYS`: one to five comma-separated URL-safe Base64 keys, each exactly 32 decoded random bytes. Primary first; retain older keys for decryption until an approved re-enrollment/rekey process is complete. Store separately from JWT signing keys and database backups. Do not print keys, put them in git or reuse the JWT secret. Loss cannot be repaired by deriving a key from JWT configuration.
- `MFA_ENFORCEMENT=optional` is the default for a controlled transition. Enrolled/reset accounts remain enforced. `privileged` requires enrollment for all privileged accounts immediately, including existing password-only tokens. Invalid configuration fails closed. All workers must use identical reviewed code/configuration.
- Validate staging first with synthetic accounts and isolated storage/delivery sinks. Verify HTTPS, cookies/origins/proxy configuration, clock synchronization, encryption-key backup/restoration, persistent lockouts, concurrent sessions and all roles. Agree session lifetimes and HR/IT support process.
- Pre-enroll at least two independently verified IT operators, securely save recovery codes, communicate authenticator setup and confirm privileged coverage before HR/IT approves enabling `privileged`. No existing live users were enrolled/reset here.
- Lost device: use a saved recovery code plus password, then replace authenticator with recent proof. Otherwise an independently identity-verified IT operator performs the audited reset after approved support review. If every IT operator loses all factors, use a controlled offline HR/IT-authorized recovery with all writers stopped, backups and explicit account/session-state review; there is intentionally no public bypass. Define and rehearse that operator runbook before enforcement.
- Rollback must retain the MFA-aware guard. Do not deploy a pre-MFA build that ignores stored factor state. A configuration rollback to optional does not remove enrolled-account protection.

## Remaining risks and staging prerequisites

Local code completion does not authorize production rollout. Encryption configuration, privileged enrollment coverage, HR/IT recovery approval and staging UAT are required. Unknown-account/edge abuse limits and intentional lockout denial-of-service still require ingress monitoring/rate policy. An attacker with direct database write privileges or an older API worker can bypass application guarantees. Clock synchronization is essential.

Security writes reuse the global persistent integrity lock: no unsafe automatic expiration/removal was added. Interrupted writes require quiescing all writers and the documented `docs/integrity-lock-recovery.md` procedure. Audits precede mutations and record intent, not proof of downstream completion. Cross-collection transactions/outbox recovery are not claimed. Retain private key/audit access controls and test outage recovery.

Other Task 17/18 policy, storage/scanning, normalized-index, employee/Solver reconciliation and external-integration prerequisites remain; this task does not certify full-platform launch readiness or constitute penetration testing.

## Disposable environment cleanup

All three explicitly named Task 19 localhost suite databases were dropped and absence verified. No `codex_integrity_*` databases remained, including per-test databases. Verified test API and MongoDB processes were stopped; ports 18089 and 27089 have no listeners. Checked workspace-only `.test-deps`, `.mongo-test` and `.node-test` directories were removed and absence verified. Existing application dependencies, source documents and employee/Solver records were preserved. HEAD and Task 01 ancestry were verified unchanged.
