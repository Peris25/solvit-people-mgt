# Task 04 — Staff Home Dashboard

Local implementation extends the existing React/FastAPI/MongoDB application.
Baseline HEAD remains `7afbe1f700fc17352cce58d644419b4efbff14ce`; all existing
uncommitted Task 03 changes were preserved. No production connection, record
migration, commit, push or deployment was performed.

## Requirements and audit

| Source | Requirement | Implementation |
| --- | --- | --- |
| Developer Brief v1, §5.1, p.8; current Task 04 request | Personalized first screen, leave, pending requests, tasks and unread updates | Extended EmployeeDashboard; linked employee accounts land on Staff Home. Name, job title, department and Nairobi/EAT date come from authenticated employee data. |
| FRD §3.8–3.10, pp.11–12; M04, p.25 | Preserve employee navigation, existing onboarding actions, responsive layout and empty states | Existing personal review/development/recognition/leave tabs remain, subject to access. Wrapped navigation and adaptive card grid; no-data and failure states are distinct. |
| Developer Brief §5.1, p.8 | Retain role widgets and HR dashboard | Linked managers/HR/Finance retain their existing role dashboard through a second view. Unlinked administrative accounts and Solvers retain existing dashboards. |
| Developer Brief goals, p.1 and §2.2, p.3; Task 04 request | Self-service navigation and supported recent updates | Server-qualified My Profile, Leave, Documents & policies, My Tasks and Learning links. Existing notifications provide recent updates; no fabricated announcements. |
| Handbook v2 §5.1, p.8 | Annual entitlement/accrual | Reuses existing authorized leave-balance endpoint; does not invent a separate calculation. Missing, invalid or future employment start dates produce an unavailable balance. |
| FRD access rules; Task 04 privacy requirement | Server-enforced employee-level scope | Identity resolved from saved account, tenant and canonical/legacy employee aliases. The endpoint has no client employee/manager selector; all summary records are self-scoped, even for HR and managers. |

The previous employee dashboard fetched recognition through an endpoint that did
not apply its supplied nominee filter. It also used a user-ID fallback for leave,
treated failed loads like empty successful data, lacked employee role/department,
and used a fixed two-column layout. Staff Home now uses a dedicated, minimal,
read-only projection. Existing global recognition functionality is not widened
or used by this dashboard.

## Implementation

- `GET /api/dashboard/staff-home` uses existing authentication and Task 02
  first-login password enforcement. Missing/ambiguous/conflicting employee links
  fail closed. Supplying other employee, manager or role parameters cannot change
  the subject. Solver accounts use their existing separate dashboard.
- Tenant-scoped queries support canonical employee IDs, Mongo string aliases and
  native legacy references. Pending leave shows type, dates, working days and
  status, excluding reasons, certificates and approval/private payloads.
- Form actions reuse existing signature authorization. Pending general tasks
  require matching account/employee assignment and subject. Another employee's
  or account's actions never become personal tasks through HR privileges.
- Notifications support saved account/employee recipients, role broadcasts and
  legacy `user_id` records. Conflicting recipients, foreign tenants and another
  employee/Solver subject are excluded. The latest five are shown with a count of
  unread authorized notifications. Raw routing data, attachment/link payloads and
  confidential fields are not returned. Viewing Home does not mark items read.
- Personal review/recognition summaries preserve existing tabs without reading
  team/global datasets. Notes, pay, banking, medical, disciplinary, credential,
  signature and document contents are excluded from the dashboard DTO.
- Quick links follow effective server permissions, including runtime revocations.
  **Documents & policies opens the existing Policy Library**; it does not pretend
  an employee-private contract/payslip centre already exists.
- Frontend distinguishes errors from empty data, clears stale state on account
  changes, renders notification text safely, preserves zero balances, and uses
  existing Solvit colours and components. Form actions open the existing My Tasks
  workflow; general pending actions are informational, without invented completion
  routes or writes.

## Files modified for Task 04

```text
backend/routes/dashboard.py
backend/utils/staff_home.py
backend/tests/test_staff_home.py
backend/tests/test_password_change_enforcement.py
frontend/src/pages/EmployeeDashboard.js
frontend/src/pages/EmployeeDashboard.test.js
frontend/src/pages/RoleDashboard.js
frontend/src/services/api.js
docs/task04-staff-home-report.md
```

The password-enforcement test file retains its earlier changes and adds the new
Home route to its direct/bypass request matrix. No dependencies or database
schemas/indexes were added to the application.

## Validation

- Focused backend Home/password tests: **69 passed**, six existing warnings.
- Complete frontend suite: **68 passed across 13 suites**.
- Strict CI build (`CI=true`): **passed**, no lint/hook warnings.
- Normal production build (`CI=false`): **passed**.
- Python compilation and whitespace checks: **passed**.
- Full backend suite: **661 passed**, six existing dependency/lifecycle warnings
  in 120.96 seconds, using guarded disposable localhost services.
- Cleanup: the disposable test database was dropped and absence verified; owned
  API/Mongo processes stopped, both test listeners absent and temporary runtimes
  and downloads removed.

Tests cover personalized data, real zero balances, absent/invalid start dates,
legacy/native references, foreign tenants, invalid/duplicate account links,
own/other employee requests and actions, restricted-field projection, runtime
revocation, forged query parameters, first-login enforcement, notification read
flags, safe text rendering, error states, account switches and retained role views.
All prior Task 01–03 regression suites remain included.

## Remaining scope and staging acceptance

No migration or production data change is needed for this dashboard. Staging HR
acceptance should check a linked employee, linked manager, HR/Finance role view,
unlinked account, zero/missing leave and a denied/revoked module on desktop and
phone. Actual employee links and leave history must exist for actual figures.

The broader Brief's announcements publishing/read-receipt system, company events,
birthdays, SMS/push and employee-private document centre are separate features;
this task uses existing notifications and policy documents as requested.
Photographs are not exposed by the dashboard. The existing leave calculator and
its policy/backfill limitations remain unchanged; in particular the FRD's older
carry-forward figure conflicts with the later Brief/Handbook. Task 04 does not
silently select a new policy or rewrite leave records.

The legacy global recognition API still does not filter its nominee parameter;
Staff Home does not call it. Reviewing that module's wider visibility is separate
from the self-only dashboard implemented here. No claim of overall production
or policy acceptance is made without staging UAT.
