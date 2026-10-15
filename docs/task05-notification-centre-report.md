# Task 05 — Notification Centre

Local implementation extends the existing application and retains all Task 01–04
changes. HEAD remains `7afbe1f700fc17352cce58d644419b4efbff14ce`.
No production access, live-data update, migration, commit, push or deployment.

## Requirements and inspected infrastructure

The Developer Brief v1 §5.4 (p.9) describes an inbox, badge, categories, related
records and approval actions. FRD §3.6/§3.10 (pp.10–12) describes notification
badges, read status and defined empty/loading states; §4 (p.16) requires API-level
role and recipient scope. Handbook v2 confidentiality/grievance provisions and
the personal-data acknowledgement (pp.15–17,22) support keeping confidential
content out of previews. This implementation follows the current Task 05 request;
it does not silently activate the Brief's additional delivery channels.

Inspected existing components:

- `backend/routes/automation_routes.py`: legacy notifications list and read API.
- `backend/utils/task_access.py`: existing recipient/employee checks.
- `backend/automation/engine.py`: existing event/cron notification inserts,
  role recipients and leave-email suppression rules.
- `backend/routes/leave.py`: leave submission event and employee decision notice.
- `backend/routes/lnd.py`: training records and existing assignment-email calls.
- `backend/reminders/engine.py`, `utils/email_triggers.py`, `utils/email_service.py`:
  reminder scheduling/deduplication and SMTP/Mailtrap configuration, throttling,
  retries and legal-template production overrides.
- Sidebar notification dropdown, HR/Solver dashboards and Task 04 Staff Home.

There is no independent announcement publisher/feed to connect. Training and
announcement categories work when a supported stored notification exists.
Training's current route primarily generates email; some Reminder Service rules
also remain email-only. This task does not replay/backfill those historical events
or claim every reminder already writes an inbox item.

## Completed functionality

- Central `/notifications` page, accessible through the existing bell/dropdown,
  Staff Home and Solver navigation. Existing dashboards remain available.
- `GET /api/automation/notifications/centre`: newest-first authorized items,
  full unread count, authorized total, category/type/read filters and bounded
  pages. Today/Earlier grouping and times use Nairobi/EAT. Missing or invalid
  timestamps have a clear fallback.
- Supported categories: Leave, Approvals, Onboarding, Training, Announcements,
  Performance, Recognition, Policies and System. Type filters distinguish
  Actions required, Updates and Approvals. No placeholder notifications are
  created to fill empty categories.
- Existing `GET /automation/notifications` remains a list response for existing
  callers, with safe projected previews. Its first 50 items no longer determine
  the bell's count; the shared context uses the server's full authorized count.
- Existing mark-read endpoint now writes a per-account `notification_receipts`
  record instead of changing the shared notification. Deterministic receipt `_id`
  and MongoDB's built-in uniqueness make repeated/concurrent acknowledgement
  idempotent. One reader of a role broadcast cannot mark it read for another.
- Legacy `is_read`/valid `read_at` remains a compatibility baseline. New read
  receipts do not modify original notifications, employee records or accounts.
- Canonical/legacy account, employee, native ObjectId and Solver anchors are
  supported. Conflicting recipients, cross-collection alias collisions, foreign
  tenants, contradictory subjects and ambiguous record references fail closed.
  Linked employee status and restricted Board classification are enforced;
  inactive/suspended Solvers are denied. Explicit administrative accounts without
  employee links retain their authorized role inbox.
- Private reasons, medical information, salary/banking details, raw routing data,
  attachments, credentials and free-text titles/messages are excluded from every
  preview. Controlled category text is used; sender labels are System/Solvit People
  rather than an invented person's identity. Full details stay in authorized modules.
- Links are generated from verified records and existing module permissions,
  never copied from a stored arbitrary URL. Missing/deleted/ambiguous/foreign
  targets produce no link. Leave/training pages select the related record from
  their already-authorized lists and give an unavailable state for forged targets.
- Authorized pending leave approvals reuse the existing decision API; self or
  unrelated employees receive no approval control. The server rechecks permissions
  at decision time. Exact repeated decisions do not create duplicate employee notices.
- Existing leave-submission automation binds notifications to the saved employee/
  manager relationship. Stable source-event IDs prevent concurrent/repeated
  AR-LV-01 dispatch creating multiple new notices. No second notification generator
  is invoked when reading the centre, refreshing, filtering or marking read.
- Shared badge polling, account-switch clearing, persisted read acknowledgements,
  failure states and refresh are implemented. Failed writes never optimistically
  decrement counts. The dropdown's bulk action explicitly marks **shown** items,
  with partial-failure feedback; it does not pretend to acknowledge unseen pages.

Staff Home uses the same authorization/preview/read-receipt service, retaining
its self-only summary. The full centre can additionally contain explicitly
authorized manager/HR role actions. Returning to Home reloads its snapshot.

## Files modified by Task 05

Earlier edits in these files are retained; this list is Task 05's scope, not a
claim that unrelated pending changes were created by this task.

```text
backend/automation/engine.py
backend/routes/automation_routes.py
backend/routes/leave.py
backend/utils/notification_centre.py
backend/utils/staff_home.py
backend/tests/test_notification_centre.py
backend/tests/test_staff_home.py
backend/tests/test_password_change_enforcement.py
frontend/src/App.js
frontend/src/components/Layout.js
frontend/src/components/Sidebar.js
frontend/src/context/NotificationContext.js
frontend/src/context/NotificationContext.test.js
frontend/src/pages/EmployeeDashboard.js
frontend/src/pages/EmployeeDashboard.test.js
frontend/src/pages/Leave.js
frontend/src/pages/LnD.js
frontend/src/pages/Notifications.js
frontend/src/pages/Notifications.test.js
frontend/src/services/api.js
frontend/src/utils/relatedRecordFilter.js
frontend/src/utils/relatedRecordFilter.test.js
docs/task05-notification-centre-report.md
```

No application dependency was added. The new receipt collection is created only
when an authorized account actually acknowledges a notification; no migration
or historical record rewrite is needed.

## Validation

- Complete frontend suite: **85 tests passed, 16 suites**.
- Strict CI build: **passed**, with no lint/hook-dependency warnings.
- Normal production build: **passed**.
- Focused backend/regression run: **176 passed**, one real-Mongo case deferred
  until the full disposable-localhost run; six existing warnings.
- Full backend suite: **697 passed**, six existing dependency/lifecycle warnings,
  in 69.24 seconds. All disposable-Mongo concurrency tests ran; no skips.
- Python compilation and tracked/new-file whitespace checks: **passed**.
- Cleanup: all three owned disposable databases dropped and absence verified;
  test API/Mongo processes stopped, both listeners absent, temporary runtimes and
  downloads removed. MongoDB briefly held file handles; the checked cleanup retry
  completed successfully.

Tests cover recipient formats and isolation, another employee/account/tenant,
forged/ambiguous identifiers, status/Board restrictions, Solver module isolation,
per-account broadcast reads, idempotency and actual Mongo concurrency, counts,
filtering, timezone sorting, baseline legacy reads, private preview redaction,
safe/missing links, manager approval scope, exact event replay, retained first-login
enforcement, account changes, persisted badge updates, failures, page controls,
safe text rendering and Home navigation. Prior Task 01–04 suites remain included.

Initial checks found a type-filter variable shadowing issue and an isolated
password-screen provider compatibility issue; both were fixed and their tests
passed. The broader run identified Solver performance notifications must use
M02 permissions rather than FTE M05 permissions; that mapping was corrected.
Failed attempts are not counted as successful final validation.

## Outstanding staging requirements and boundaries

1. Confirm the staging database principal can read/write `notification_receipts`.
   Only built-in `_id` uniqueness is required for receipt/event idempotency; no
   production index or migration was installed. Review query indexes/retention
   as notification volumes grow; exact counts currently evaluate authorized
   candidate notices before filtering and pagination.
2. HR UAT: employee, assigned manager, unrelated manager, HR, Finance, administrative
   account and Solver; zero/unread/read inboxes; leave submission/approval;
   legacy notification/record IDs; denied status; account switching; desktop/phone.
3. Verify SMTP staging isolation before any end-to-end delivery test. Existing
   legal/formal email templates can override Mailtrap testing and select production
   SMTP. Role-based email recipient routing and retries remain existing behaviour;
   this task did not activate or claim to secure additional email/SMS delivery.
4. Historical role notices with a shared legacy read flag cannot reconstruct each
   individual's old read history. The baseline is preserved; new receipts are
   personal. Existing duplicate notifications are not deleted or merged, and
   historical events are not replayed.
5. Generic previews intentionally omit stored free text. If HR wants approved
   announcement text shown, an authenticated announcement publisher and an explicit
   safe-publication contract must be built first. Actual training/reminder producers
   that are email-only need a separately tested in-app delivery extension; no
   notification-centre query fabricates those missing events.
6. SMS/push, notification preferences, quiet hours, daily digests, announcement
   publishing and inline approvals for workflows other than existing leave are
   outside this bounded implementation. Other supported workflows link to their
   existing authorized modules instead of inventing approval endpoints.

No claim of production deployment or HR/staging acceptance is made.
