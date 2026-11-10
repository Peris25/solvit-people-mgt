# Email recipient routing closure

## Implemented flow

| Event | Email recipients |
| --- | --- |
| Leave submitted or edited/resubmitted | Employee confirmation; saved line manager approval action; active HR Admin/HR Manager oversight action |
| Manager approves leave | Active HR Admin/HR Manager approval action |
| Leave approved or denied | Requesting employee outcome |
| Employee withdraws pending leave | Saved manager and active HR staff; no denial email |
| HR creates a performance review | Review employee, with secure portal link |
| Employee submits self-assessment | Saved eligible line manager (existing workflow retained) |
| Manager submits assessment | Active HR staff, to arrange the meeting |
| Manager proposes meeting date | Active HR staff to confirm; existing employee portal notification retained |
| HR sets meeting | Employee and saved manager, with date/time/location available through the protected review |
| Solver application, eligible or ineligible | HR Admin receives an internal review alert; applicant receives a separate receipt acknowledgement |

IT Admin does not receive routine recruitment emails. General Manager receives direct-report manager emails when assigned, but is not copied onto every HR operational email merely because of broad access rights. Existing role authorization and approval workflows remain unchanged.

## Privacy and reliability

- Legacy automation uses the saved employee/manager relationship, never all accounts sharing Employee or Line Manager roles. Missing employee context cannot become a role-wide staff notification.
- Role-based action emails select active tenant-scoped HR, Finance or IT accounts; duplicate mailbox addresses, inactive/exited linked employees and foreign-tenant accounts are excluded. Linked system HR accounts are supported.
- Routine check-only automation remains in the portal. Explicit action messages can email scoped recipients; the legacy performance-meeting duplicate is suppressed. Existing compliance action reminders remain supported.
- Reminder routing uses canonical/legacy identity lookup, saved manager assignments rather than supplied manager overrides, all active intended role recipients and mailbox deduplication. A skipped email is no longer reported as successful reminder delivery.
- New action messages contain a safe summary and an authenticated portal link, not medical details, reasons, assessment answers, scores or CV content. Links do not grant authorization.
- Existing template CC lists use active tenant-scoped accounts and mailbox deduplication. Template employee/manager lookup now supports legacy identifiers.
- New leave messages and new workflow actions have complete built-in content, retaining the central empty-content and outbound-email safeguards. No database template edits or backfill were performed.
- Source-event delivery claims use deterministic MongoDB `_id` keys in existing email_log storage. Multiple workers/replayed events cannot dispatch the same action twice. Claims are distinguished from actual provider-attempt logs so reports do not count a claim as a second delivery.
- Automatic retries now atomically claim a pending row; only the winning worker sends that attempt.
- Email failures remain best-effort and cannot roll back saved leave, review or applicant records. Existing in-portal notices remain available.

## Interrupted delivery handling

A source claim left `dispatching` or a retry left `processing` indicates a possible interrupted attempt. The application deliberately does not expire, remove or steal these claims: a provider may already have accepted the email. An authorized operator must compare the source event, provider/delivery logs and retry state before deciding whether a manual resend is safe. Ordinary provider failures retain the existing bounded retry schedule. Missing configuration/templates are logged/skipped; do not automatically replay events or clear claims after changing configuration.

## Validation

Frontend: 348 passed in 49 suites. Backend: 1,595 passed, 321 skipped, five existing deprecation warnings. Synthetic local test configuration and mocked transports only; no production database, real email or live employee changes.
Coverage includes HR/manager/employee routing, both Solver outcomes, legacy IDs, inactive and foreign-tenant exclusion, linked system HR, routine suppression, withdrawal vs denial, repeated/concurrent source delivery and concurrent retry ownership.
Python compilation and whitespace checks passed. No frontend application code changed; frontend regression suite was run, builds were not repeated.

## Deployment and remaining checks

No migration, new collection, dependency, production index installation or environment change is required. Existing MongoDB `_id` uniqueness supplies event/retry coordination. Backend auto-deployment follows push to main. Render completion and controlled real-inbox delivery still need confirmation. HR and manager work emails/account links must be correct, outbound email enabled, and a working SMTP/Sender.net configuration present. Existing templates used by other modules still require valid content; the previous empty-email guard blocks invalid templates rather than inventing messages. Old untemplated automation retries with the prior broadcast signature are held as blocked for recipient review. Their content is not rewritten and records are not deleted. Other legitimate retries retain existing delivery behavior.

## Modified files

- backend/utils/email_routing.py
- backend/utils/email_service.py
- backend/utils/email_triggers.py
- backend/utils/leave_workflow.py
- backend/utils/performance_workflows.py
- backend/automation/engine.py
- backend/reminders/engine.py
- backend/routes/solver_intake.py
- backend/routes/email_delivery.py
- backend/tests/test_email_routing.py
- backend/tests/test_runtime_controls.py
- docs/email-recipient-routing-report.md
