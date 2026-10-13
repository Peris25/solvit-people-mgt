# Employee accounts and integrity rollout

This change is compatible with existing documents and does not install new
indexes, backfill account links, rewrite reporting relationships, or provision
accounts on startup. Production data review, migration, and deployment are
separate operations requiring approval. Do not enable demo seeding in production.

## Runtime behavior

- `users.employee_id` refers to the employee's stable `employees.id`. Reads can
  resolve legacy MongoDB employee IDs. Missing links and the historical user-ID
  seeder bug can use a unique normalized email match, without writing a backfill.
  Ambiguous matches and conflicting accounts return a review-required conflict.
- Roles do not confer account exceptions. Explicit `account_type` values
  `system`, `solver`, and `board` designate non-employee accounts. Classify these
  only after review; an HR Admin who is an employee follows the employee rules.
- Employee emails are trimmed and lowercased. Plus tags and dots are retained.
  Existing login emails are independent once explicitly linked; changing an
  employee's work email does not reset credentials, change roles or revoke sessions.
- Normal creation, recruitment conversion and import share duplicate and manager
  validation. Import requires one uniquely resolved existing manager name.
  Recruitment conversion requires `line_manager_id` and is idempotent.
- A reporting apex uses the existing `is_board_chair` flag. Only HR Admin can
  create it, and only one apex can be created through the API. Other new records
  require an eligible manager. Legacy unresolved assignments are preserved on
  unrelated edits and reported for review. Manager departures require active
  direct reports to be reassigned first.
- IT Admin can use **Roles & Permissions > Users > Employee login account** to
  provision or explicitly link an account. New accounts use the Employee role,
  the existing password policy and the existing password-change flag. The server
  enforces the flag on every protected request, including refresh-issued and
  previously issued tokens. The frontend shows password recovery and sign out
  until completion; successful changes require a new sign-in. Existing
  account passwords, active status and roles are retained. Passwords are never
  included in response/audit payloads. Deliver initial credentials through an
  approved secure channel; this operation does not email passwords.
- API identity and reporting writes use a MongoDB lock document to serialize
  checks across workers, including concurrent cycle changes, without requiring
  replica-set transactions. Conflicting requests return 409 and should be retried.
  The lock has no automatic expiry: a process crash leaves writes blocked rather
  than allowing an overlapping writer. An operator must confirm all previous
  writers have stopped before removing an abandoned lock document. Never delete
  account or employee documents to clear a lock.
- Destructive demo helpers require BOTH `APP_ENV=development` and
  `ALLOW_DESTRUCTIVE_DEMO_DATA=true`. Bootstrap no longer purges existing data or
  resets passwords. Startup seeding additionally requires `SEED_DEMO=true`.

## Read-only audit

Prefer an access-controlled snapshot containing `employees` and `users` arrays.
Use the minimal fields listed in `backend/scripts/audit_employee_integrity.py`;
exclude names, statutory IDs, salary, passwords, password hashes and tokens.

```powershell
python backend/scripts/audit_employee_integrity.py --snapshot <restricted-snapshot.json>
```

The script has no write mode. It emits aggregate counts and report-local labels,
not names, emails or database IDs. It detects normalized duplicates, conflicting
account links, orphaned/unclassified accounts, employees without accounts,
invalid/ambiguous/ineligible managers and reporting cycles. Proposed reviews are
not executable migrations. Keep snapshot files and reports outside Git.

`--database` is available only for a separately authorized read-only audit. It
reads `MONGO_URL` and `DB_NAME` from the environment and uses minimal projections.
It does not load application startup, create indexes, seed records or perform
writes. Never run it with production access without explicit authorization.

## Proposed additive migration (not run by this change)

1. Take and verify a backup. Obtain a fresh read-only audit and inspect actual
   indexes. Inventory every external writer, deployment branch and database topology.
2. Resolve each duplicate or conflicting identity through an approved mapping.
   Do not merge, delete, auto-select or exclude conflicting records just to make
   index creation succeed. Unresolved groups block full uniqueness enforcement.
3. Review system/solver/Board exceptions, rehires, inactive accounts and roots.
   Explicitly approve every account-link or manager-reference correction. Keep
   historical references intact and document any compatibility aliases.
4. Add `email_normalized` to users and `work_email_normalized` to employees.
   Preserve raw email fields and credentials. Add missing legacy canonical IDs
   as the existing ObjectId string, never a new random ID. Review missing tenant
   values. Leave non-employee account links absent, not empty strings.
5. Apply only approved account links. Provision missing accounts through the
   idempotent endpoint, with individual authorization and secure credential delivery.
6. Re-audit during a maintenance window with ALL external writers paused. The
   approved migration should use compare-and-set conditions, capture before-values,
   be resumable and have a tested rollback. This repository provides a review
   plan, not a production mutation script.
7. Install the explicit unique/partial index specifications in
   `backend/utils/integrity_audit.py`: global normalized login email, per-tenant
   normalized employee email, canonical employee ID, per-tenant account employee
   link and employee code. Retain the current raw-email index until its replacement
   is separately reviewed. Verify partial string fields have no empty values.
8. Run staging tests with the reviewed data and indexes; approve deployment
   separately. Verify login, self/team scope, approvals and manager display.

Until the approved backfill/index installation, the API lock and legacy-aware
checks prevent concurrent duplicates through the protected code paths. Direct
database writes or old application versions are not protected by the planned
normalized indexes. No migration can be declared complete while existing
duplicates, exceptions or manager issues remain unresolved.

## Tests

Run the isolated backend integrity/profile suites and frontend component suites.
`test_employee_integrity_mongo.py` additionally requires an explicitly selected
localhost disposable MongoDB instance; it creates a uniquely named test database
and never uses `MONGO_URL` or `DB_NAME`. Do not run the existing broad legacy
integration suites against production: some create or delete fixture records.

## Security closure

Employee-linked leave, training, IDP, skills, performance, onboarding, project and form operations enforce object ownership on the server. Scoped managers can access saved direct reports; ordinary Employee roles and roles inheriting Employee remain self-scoped even with a generic matrix override. Manager routing and training HR-approval requirements come from saved records, not client flags. Public staff metadata and peer-recognition workflows remain intentional shared surfaces.

See [controlled lock recovery](integrity-lock-recovery.md). Uncertain write outcomes now retain the lock; no automatic unlock has been added. Development-only seed/reset helpers cannot run outside explicitly enabled development.

The legacy HTTP suites use a separately opted-in disposable localhost API, synthetic fixture accounts, outbound network guards and per-test authentication-limit isolation. The test-only reset route is registered by `backend/scripts/local_test_server.py`, not by the production application. `SOLVIT_LOCAL_INTEGRATION=1` additionally requires the exact localhost Mongo URI and a `codex_integrity_suite_` database name. Without explicit local setup the legacy destructive suites are skipped, never redirected to their old preview defaults.
