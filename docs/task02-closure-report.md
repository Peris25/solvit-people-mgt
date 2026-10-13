# Task 02 security and quality verification — 13 October 2026

All requested local security/test/build checks pass, including the subsequent
mandatory password-change enforcement pass. This is not production sign-off.
Task 01 commit `83f0b4f` is preserved, and its manager/department regressions pass.
Prior uncommitted Task 02 work was retained. During implementation/verification,
no commit, push, deployment, production access, data migration or production
index installation occurred. The user subsequently authorized committing and
pushing this work on `task02-employee-account-security`; `main` remains at Task 01.
Deployment has not been authorized.
Task 03 was not started.

## Mandatory first-login password enforcement

The previous first-login limitation is resolved. Provisioning already records
`users.must_change_password = true`; existing account provisioning preserves the
saved hash, active status, role and change requirement. Login previously surfaced
the requirement without enforcing it, and refresh did not honor password-change
session invalidation. Both gaps are fixed without backfills, resets or schema
migrations.

Every protected request now validates the live account and effective password
requirement on the server. The shared `get_current_user` check and a global
FastAPI dependency prevent bypass through cookie/bearer tokens, direct requests,
alternate routes, privileged/custom roles or a handler missing its local check.
The global exemption uses actual registered handler identities; forged URLs,
headers, JWT requirement claims or body fields cannot create an exception.

Restricted sessions may use only these authenticated recovery endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| POST | `/api/auth/login` | Validate credentials and obtain a restricted session |
| GET | `/api/auth/me` | Minimal identity/change-required status |
| POST | `/api/auth/refresh` | Rotate tokens; the requirement still applies |
| POST | `/api/auth/password/change` | Verify current credential and existing password policy |
| POST | `/api/auth/logout` | Revoke the current pair and clear HTTPS-only cookies |

Existing anonymous health and public recruitment application handlers remain
public; they grant no private employee/account access. No other auth handler is
automatically exempt merely because it is under `/auth`.

The existing recorded-expiry policy uses the same gate. Legacy accounts without
the requirement or a recorded password-change timestamp are not retroactively
forced to change; their normal login/refresh behaviour and account links remain.
An account with a broken employee link can recover its own credential, but that
does not repair or bypass the link conflict on protected functionality.

Successful self-service change atomically updates the hash, existing password
history/timestamp and required flag, with an old-hash compare-and-set condition.
Incorrect current passwords, reuse/policy failures and concurrent changes do not
clear the requirement. Existing access and refresh tokens are invalidated; the
user signs in again. New JWTs include a snapshot of the existing password-change
timestamp, preventing a late token minted from pre-change login/refresh data from
becoming valid. Legacy JWTs retain timestamp-cutoff compatibility. Fractional
issue timestamps avoid rejecting a legitimate immediate new login in the same
second. The atomic password timestamp also protects old-token revocation if a
later invalidation-store write fails.

Logout revokes access IDs and their associated refresh-session ID using the
existing revocation collection. It accepts a bearer access token as well as
cookies. Replaying the current pair fails, while another current-format session
continues normally. A legacy access token without an individual ID uses the
existing per-user invalidation cutoff as the safe fallback; that legacy logout
can therefore sign the account out on other devices. Normal refresh does not
invalidate an otherwise unexpired access token solely because rotation occurred.

The frontend supplies a minimal required-password form and sign-out action;
private layouts, tours and page requests are not mounted while restricted.
Server requirement responses also gate a previously normal frontend session.
Password failures retain the restricted state; success clears the session hint
and returns the user to sign-in. This UI is not relied on for authorization.
Authentication/password flows emit no notifications and do not email credentials.

## Authorization fixes

Server-side employee ownership and saved direct-report checks now cover leave,
training, IDP, skills, performance, employee detail/profile, onboarding, projects,
disciplinary records, forms, tasks, private calendar entries and notifications.
Ordinary Employee/Solver roles, including roles inheriting Employee, cannot widen
personal access through a generic module override. Explicit revocation remains
effective. Existing HR delegation, Finance direct-report leave approvals and
authorized Board/system-admin access are preserved.

Creation canonicalizes employee references and derives managers from saved
relationships. Forged managers and reassignment through request/decision bodies
are rejected. Bulk training validates the entire batch before writing. Training
approval thresholds come from saved cost/duration/approval flags. An Employee
signature belongs exclusively to the form's actual subject, including when HR
initiates the workflow. Nested subjects/managers and explicit solver references
are checked. Form signing uses compare-and-set before firing outcomes, preventing
a competing/replayed step from overwriting the current step or triggering its
outcome. Orphaned task subjects fail closed. AI action overrides cannot replace
employee/manager/record identities or non-editable parameters.

The audit found and corrected an unreachable employee-detail authorization check
and a board-led review-panel return preceding ownership validation. Both have
regression tests. Settings responses now mask entire secrets and a masked settings
round trip preserves the saved secret.

Public staff metadata and intentional peer-recognition surfaces remain shared.
They are not private employee-profile authorization exceptions.

## Write integrity and recovery

Interactive employee creation/update, import, recruitment conversion and account
provisioning share normalized, legacy-aware identity validation and the persistent
MongoDB integrity lock. Creation also rejects a login email linked to a different
employee, including whitespace/case variants. An eligible unlinked legacy account
can be reused through explicit provisioning; existing credentials/roles are kept.
Password changes, role changes, tour flags, risk calculations and automation flags
do not create accounts or rewrite email/account-link identities. Development
fixture helpers require explicit development opt-in and are not production paths.

Lock metadata records a per-write owner, creation time, worker-instance UUID and
PID. A persistent 409 indicates contention; it does not establish interruption.
Cancellation, network timeouts and unexpected exceptions retain the lock because
an operation may still be running. Normal completion or known validation/duplicate
rejection removes only the matching owner. There is no TTL or automatic recovery.

[The controlled recovery procedure](integrity-lock-recovery.md) requires stopping
all writers/restarts/schedulers, proving database quiescence, backing up and
reconciling the uncertain outcome, then deleting only the captured lock with a
compare-and-set filter. Failure to match must not fall back to an ID-only delete.
This procedure was documented, not executed against any deployed database.

## Verification

| Check | Result |
| --- | --- |
| Full backend: `pytest backend/tests tests -q -p no:cacheprovider` | **465 passed**, zero failures/skips; 5 existing framework/dependency deprecation warnings |
| Password/session enforcement regression cases | **44 passed**, included above; real FastAPI routing with synthetic in-memory records |
| Actual disposable MongoDB tests | **3 passed**, included above; normalized indexes, serialization/concurrency and reporting-cycle checks |
| Frontend: CRACO Jest, `--watchAll=false --runInBand` | **28 passed**, 7 suites |
| Strict frontend build, `CI=true` | **Compiled successfully**, no React hook warnings |
| Normal production frontend build | **Compiled successfully** |
| `python -m compileall -q backend` | Passed |
| `git diff --check` and new-source trailing-whitespace check | Passed |
| Task 01 commit ancestry and HEAD at verification | `83f0b4f`, preserved |
| Disposable test MongoDB/API cleanup | Confirmed after shutdown/removal; see cleanup note below |

Backend tests ran with synthetic credentials against a separately guarded API at
`127.0.0.1:18089` and MongoDB at `127.0.0.1:27089`. Test database names were restricted
to disposable prefixes. External HTTP/socket connections were blocked. Legacy
fixtures were updated to use valid saved managers, actual employee signatures,
current validation contracts and sufficient synthetic funding. Test-only module
resets prevent fixture mutations from contaminating later modules; rate limits
remain active within individual tests. These reset routes are registered only by
the separate local test-server script, never by the production application.

The final backend run used repository-pinned authentication/framework dependencies:
PyJWT 2.12.1, Pydantic 2.13.3/core 2.46.3, FastAPI 0.110.1, Starlette 0.37.2,
HTTPX 0.28.1, AnyIO 4.13.0, Motor 3.3.1, PyMongo 4.5.0, bcrypt 4.1.3 and
pytest 9.0.3. Temporary test dependencies/runtimes did not alter project manifests.

React callbacks/effects now declare their actual dependencies. Email filters do
not reset unsaved configuration drafts; the AI greeting still initializes once;
calendar loading does not cause a refetch loop. No lint rule was suppressed.

## Remaining risks and prerequisites

- **Database enforcement is pending approval.** Until reviewed backfill and unique
  partial indexes are installed, protected API writers are serialized, but direct
  database writers and older deployments can bypass normalized-email/account-link
  checks. The proposed indexes cover normalized login email, tenant employee
  email, canonical employee ID, tenant account-to-employee link and employee code.
  Indexes cannot enforce acyclic reporting by themselves.
- **Existing records have not been inspected in production.** Duplicate accounts,
  legacy aliases, missing managers, cycles and special-account classifications
  require the separately authorized, pseudonymous read-only audit. No records were
  automatically deleted, merged, relinked or corrected. Dirty records may receive
  review-required conflicts or denied operations until individually resolved.
- **Credential delivery/staging:** mandatory changes are now enforced and locally
  verified. Initial credential delivery still needs an approved secure channel.
  Verify the new UI/cookie flow over staging HTTPS and review the existing
  flagged/expired account population without resetting or updating records.
  Replace every backend worker serving protected functionality together; older
  deployments do not enforce this gate. Keep new provisioning disabled until
  all serving instances have the fix. No JWT-secret rotation is required.
- **Existing runtime dependency manifest:** existing PDF/QR routes import
  `reportlab` and `qrcode`, which are absent from `backend/requirements.txt`.
  The disposable test environment supplied them. Verify those existing runtime
  prerequisites in a clean staging build; this authentication change adds no
  project dependencies and does not modify the manifest.
- **Availability/reconciliation:** an uncertain write intentionally blocks later
  integrity writes until controlled operator recovery. Multi-document workflows
  and best-effort automation/email delivery are not transactional. Review a
  partially completed workflow before retrying; form outcomes are not a durable
  queue and are not guaranteed exactly-once after a process crash.
- **Staging is required:** restore an approved restricted snapshot to staging,
  inventory external writers and actual indexes, review exceptions and mappings,
  verify backup/restore and lock recovery, then test self/team/HR/Board workflows
  and concurrent writes with the approved index plan. Disable production demo
  seeding. Obtain separate approval for data changes, indexes and deployment.

No local password-enforcement finding or test failure remains unresolved. Task 02
is **not production-ready or signed off for deployment** while the separately
approved production/staging data review and database prerequisites remain pending.

## Full Task 02 source-file inventory

This includes earlier Task 02 changes as well as this closure pass. Temporary
downloaded runtimes/dependencies/test databases and generated build artifacts are
excluded. Task 01's committed files were retained and regression-tested.

```text
.gitignore
README.md
backend/automation/engine.py
backend/automation/seed_data.py
backend/routes/access.py
backend/routes/ai_agent.py
backend/routes/auth_routes.py
backend/routes/automation_routes.py
backend/routes/calendar.py
backend/routes/dashboard.py
backend/routes/data_import.py
backend/routes/disciplinary.py
backend/routes/documents.py
backend/routes/employees.py
backend/routes/forms.py
backend/routes/leave.py
backend/routes/lnd.py
backend/routes/onboarding.py
backend/routes/performance.py
backend/routes/projects.py
backend/routes/recognition.py
backend/routes/recruitment.py
backend/routes/settings.py
backend/server.py
backend/scripts/audit_employee_integrity.py
backend/scripts/local_test_server.py
backend/tests/conftest.py
backend/tests/integrity_fakes.py
backend/tests/test_employee_authorization.py
backend/tests/test_employee_integrity.py
backend/tests/test_employee_integrity_mongo.py
backend/tests/test_employee_profile_display.py
backend/tests/test_iteration_12.py
backend/tests/test_iteration_13.py
backend/tests/test_iteration_2.py
backend/tests/test_iteration_3.py
backend/tests/test_iteration_4.py
backend/tests/test_iteration_6.py
backend/tests/test_iteration_7.py
backend/tests/test_iteration_8.py
backend/tests/test_password_change_enforcement.py
backend/tests/test_solvit_platform.py
backend/utils/auth.py
backend/utils/employee_access.py
backend/utils/employee_accounts.py
backend/utils/employee_integrity.py
backend/utils/form_access.py
backend/utils/integrity_audit.py
backend/utils/task_access.py
docs/employee-integrity-rollout.md
docs/integrity-lock-recovery.md
docs/task02-closure-report.md
frontend/src/components/AIAgent.js
frontend/src/components/EmailDelivery.js
frontend/src/components/EmployeeAccountForm.js
frontend/src/components/EmployeeAccountForm.test.js
frontend/src/components/HookDependencies.test.js
frontend/src/components/Layout.js
frontend/src/components/RequiredPasswordChange.js
frontend/src/components/RequiredPasswordChange.test.js
frontend/src/context/AuthContext.js
frontend/src/context/AuthContext.test.js
frontend/src/pages/Calendar.js
frontend/src/pages/EmployeeProfile.js
frontend/src/pages/Employees.js
frontend/src/pages/Employees.test.js
frontend/src/pages/Performance.js
frontend/src/pages/Projects.js
frontend/src/pages/Retention.js
frontend/src/pages/RolesPermissions.js
frontend/src/pages/Solvers.js
frontend/src/services/api.js
frontend/src/services/api.test.js
```

Cleanup note: the owned localhost API and MongoDB processes were stopped, all
disposable integrity-suite databases were removed, their database files/runtime
directory were removed, and neither designated test port retained a listener.
The temporary Node/Python dependency downloads were also removed.
