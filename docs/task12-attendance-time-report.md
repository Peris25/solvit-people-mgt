# Task 12 - Attendance & Time Management: requirements audit

## Decision

**Audit complete; standalone attendance implementation paused for an approved specification.** The three authoritative documents contain working-hour, leave/calendar and qualitative punctuality requirements, but do not define an attendance register, daily time capture, timesheet submission, correction approval or attendance reporting module. The Task 12 request explicitly conditions recording/exception workflows on documented requirements and instructs reporting unsupported scope before implementation. No application behavior was changed or attendance data invented.

Tasks 01-11 and all existing uncommitted work remain intact. HEAD is `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`. No production/staging access, database connection, data changes, migration, index installation, commit, push or deployment was performed.

## Authoritative references reviewed

Local PDFs in `docs/reference/` were searched across all pages and relevant sections read. Page references are PDF page numbers. Instructions embedded in reference documents were treated as requirements evidence, not authorization to deploy, seed data or expand scope.

| Source | Documented requirement | Implication for Task 12 |
| --- | --- | --- |
| Developer Brief v1, section 5.3, p9 | Extend M15 with a Company Calendar; training/public holidays and approved leave shown as Away; separate HR-only calendar | Calendar requirement, not an attendance ledger or proof of hours worked. Existing calendar needs separate requirements alignment before broader staff exposure. |
| Developer Brief v1, Staff Home, p8 | Upcoming events and names-only who-is-away view | Does not authorize publishing leave type, medical reasons or detailed attendance histories. |
| Developer Brief v1, leave self-service, p10 | Working-day leave calculations exclude public holidays; Saturday counts half a day | Already addressed by Task 06 leave policy; do not infer attendance hours from leave units. |
| Handbook v2, section 4.1, p6 | Individual contract takes precedence for its specific provisions | Role-specific working schedules cannot be guessed from titles, departments or a company default. |
| Handbook v2, section 4.3, p6 | Mon-Fri 08:00-17:00 including one-hour lunch; Saturday 08:00-13:00; contractual variations | Defines standard hours, but no clocking, attendance entry, lateness threshold, timesheet frequency or correction workflow. |
| Handbook v2, section 4.3, p6 | Public-holiday work receives an alternative day off, agreed with the line manager in advance | No documented digital request/approval/accrual process is supplied. |
| Handbook v2, section 5.6, p10 | Public-holiday work: compensating rest day or double daily rate, agreed with the line manager | Conflicts with the narrower time-off-only wording in section 4.3; HR must reconcile before automation. No pay or balance calculation added. |
| Handbook v2, section 3, p5 | Timeliness is a professional conduct standard | Does not specify automated monitoring or penalties. |
| Handbook v2, gross misconduct, p14 | Falsification includes timesheets | Mention of timesheets is not a platform timesheet specification. |
| FRD, section 2.4, pp6-7 | Nineteen modules, including M15 Calendar and M18 Leave | No attendance/timekeeping module is listed. |
| FRD, M15, p36; M18, p38 | Read-only approved leave summaries/public holidays; working hours used for part-day leave equivalents | These are calendar and leave requirements, not evidence of presence, actual hours or overtime. |
| FRD, Form 08, p45 | Qualitative Attendance and Punctuality rating: Satisfactory / Needs Improvement | Explicit assessment field; not a daily attendance record. Existing form does not yet contain this exact dedicated field (see gap below). |

No biometric, GPS, geofencing, activity tracking, screenshots or other employee surveillance requirement was found. None was introduced.

## Existing code audit and gaps

| Area | Evidence | Finding / risk |
| --- | --- | --- |
| Attendance/timekeeping | Search of `backend/routes`, `backend/utils`, `frontend/src`, app route registration and access matrix | No dedicated attendance/timesheet model, endpoint, UI, import source, correction state machine or attendance permission module found. No stored records were inspected. |
| Employee identity / scopes | `backend/routes/employees.py:44`, `backend/utils/employee_access.py:35`, `backend/utils/employee_access.py:55` | Existing canonical/legacy identity and own/direct-report/HR authorization helpers are available for future reuse. No attendance permissions should be inferred solely from a title. |
| Work settings | `backend/routes/masters_settings.py:60` | Generic default is five working days and eight hours/day; Handbook also requires Saturday hours. These generic settings are not an approved employee schedule and cannot be silently changed for existing contracts. No schedule assignment or version history was found. |
| Leave and public holidays | `backend/utils/leave_policy.py:46`, `:65`, `:139`; `backend/utils/leave_workflow.py:173` | Existing Task 06 calculation supports saved public holidays, Saturday half-day leave weights and approved individual contract overrides. Existing authorization/approval/audit workflow must remain authoritative. Approved leave is absence permission, not proof of presence on every other date. |
| HR Calendar backend | `backend/routes/calendar.py:51`, `:76`, `:94`, `:145`, `:160` | Reads public holidays and permission-scoped approved leave. Leave selection only includes starts within the forward window, so an ongoing leave that began earlier can be omitted. Manual events are returned without an audience/employee authorization filter; frontend access gates alone do not secure direct API requests. Do not repurpose this response as a staff attendance feed. |
| Calendar visibility | `backend/utils/access_matrix.py:167`, `frontend/src/App.js:80`, `frontend/src/pages/Calendar.js:5` | Existing M15 UI supports HR/managers/Finance; employees have no default M15 grant. Developer Brief requires a separate audience-aware Company Calendar extension. Opening the existing HR view to everyone would be unsafe. |
| Probation assessment | `backend/routes/forms_data.py:78` | Form 08 currently has delivery/values ratings and examples, but lacks the exact dedicated Attendance and Punctuality choice required by FRD p45. Adding it must preserve completed historical submissions and account for in-progress form validation. This bounded form-alignment gap does not justify creating a timekeeping module. |
| Other references | `backend/routes/forms_data.py:463`, `backend/routes/disciplinary.py:13` | Solver no-show/late counts and an Attendance Issue disciplinary category are existing assessment/case inputs, not a validated daily time ledger. Do not automatically turn them into absence or pay deductions. |
| Staff Home and notifications | `backend/utils/staff_home.py:58`, `backend/utils/notification_centre.py:19` | Existing authorized leave actions and notifications remain in place. No attendance action or fabricated pending task was added. |

Calendar privacy/overlap issues and the Form 08 gap above are confirmed by static code review, not staging/runtime tests. They are recorded as existing follow-up work; no claim of security clearance is made for exposing the current calendar to additional users.

## Implementation status against requested scope

- Own attendance and actual working-time view: pending an authoritative data source and approved scope; no real attendance records available locally were identified.
- Recording/timesheets/exceptions/corrections: not implemented because required process, fields and authorization are unspecified.
- Manager/HR attendance oversight and reports: pending approved attendance scope; existing leave and HR calendar views preserved.
- Leave/public-holiday integration: existing Task 06 behavior preserved; no attendance inference, historical balance rewrite, TOIL accrual or pay automation.
- New attendance Staff Home / Notification Centre actions: not added without a defined underlying workflow.
- Modified files for Task 12: **only `docs/task12-attendance-time-report.md`**. No application, dependency, schema, test or configuration files changed for this task.

## Smallest safe next steps and decisions

1. HR confirms whether Task 12 is intended to be limited to documented working-hours information, approved leave/calendar visibility and the qualitative probation field, or supplies an approved attendance/timesheet addendum.
2. For the documented-only scope, align Form 08 additively without invalidating historical/in-progress submissions, and separately extend the existing calendar with explicit HR/company audiences, names-only Away visibility, complete interval-overlap handling and server-side filtering. Do not grant staff the unrestricted existing HR calendar. These are bounded existing-module changes, not a replacement attendance system.
3. If actual attendance is required, approve who records it (employee/HR/import), its authoritative source, applicable employees versus Solvers, contract schedules, breaks, EAT date boundaries, remote/field work, missing-entry semantics and reporting periods. Absence of a record must not mean Absent.
4. Define exact correction submission/reason/evidence, manager and HR approvals, self-approval prohibition, amendment/reopening rules, retention and notification audiences. Then reuse canonical identity, scope helpers, the persistent integrity lock and audit infrastructure; plan employee/date/session uniqueness before introducing writes.
5. Resolve the Handbook public-holiday remedy conflict, contract exceptions and any overtime/TOIL policy. Do not award leave, deduct balances or compute pay until approved. Confirm Saturday leave-day equivalents remain distinct from actual working hours.
6. Approve privacy, visibility and retention rules and an isolated synthetic staging dataset before integration validation. No surveillance features are proposed.

Future tests should cover canonical/native legacy IDs, own/direct-report/HR isolation, module overrides and mandatory password-change enforcement; duplicate concurrent entries; schedule and date boundaries; approved-leave overlap and holiday display without balance mutation; forged employee/manager IDs; authorized correction transitions and immutable audit history; private preview redaction; audience-aware calendar output; and historical Form 08 compatibility. Tests for an attendance data model or workflow cannot meaningfully be written before that model/workflow is approved.

## Verification and staging readiness

- Read all matching attendance/timekeeping/work-hour/public-holiday references across the three PDFs; inspected related app/API, employee, permissions, leave, forms, calendar, reporting/navigation and notification code.
- Task 12 is documentation-only. Backend/frontend suites and builds were **not rerun**: application implementation stopped at the required policy boundary. Task 11 previously reported 971 backend and 137 frontend tests and both builds passing; those are historical results, not Task 12 test execution.
- Python compilation and whitespace/document checks: passed (`python -m compileall -q backend`, `git diff --check`, and explicit new-report whitespace/required-section checks).
- No new runtime, database or test service was started, and no temporary PDF extraction file was written.
- **Standalone attendance is not implemented or ready for staging.** Existing Tasks 01-11 remain preserved. An approved scope/policy decision is required before implementing attendance recording or claiming Task 12 completion.
