# Performance V3 implementation and release report

12 November 2026. Supersedes the earlier work-in-progress status.

## Implemented flow

1. HR edits and publishes role KPIs with an MD/line-manager approval reference. Drafts and historical versions remain in the existing library/audit records. Publishing assigns approved exact-role defaults to currently unassigned employees; it never overwrites an existing assignment.
2. HR maps employees to an approved role and may make approved individual amendments with a reason. Targets lock when a cycle opens. Role-change amendments cannot rewrite submitted or partially completed assessments.
3. Create Review opens one popup: choose employees, an existing cycle or a new Mid-year/Year-end cycle, year, start date and approval reference. Deadlines are calculated for four weeks; weights are fixed at 50/30/20. HR confirms the displayed existing Alignment Survey questions. No separate configuration page is required.
4. Employees see My role KPIs throughout the year and a review/deadline on Staff Home and Performance. They can save partial self-assessments, resume them and submit actuals, evidence, self-ratings, accomplishments and values examples.
5. Department colleagues receive separate peer tasks; MD reviews direct reports, and Executive Director accounts are excluded as staff peer reviewers. HR can nominate additional eligible cross-department reviewers. Peer submissions use separate assignment/completion and anonymous response records.
6. Managers confirm actuals in Week 2; changes require explanations. HR receives an actionable notification and email through the existing delivery infrastructure. HR can correct verified actuals with a reason and preserved history, requiring reassessment before release.
7. HR records verified company NPS/CSAT from Week 2. HR compilation requires manager completion, a closed peer window and at least three responses. Section A, B, C, final rating and placement are derived, not manually entered.
8. The manager proposes a date using the portal calendar and recorded availability suggestions. HR arranges the meeting manually, confirms it and records completion. Employee and manager receive portal notifications; no Outlook integration is introduced.
9. HR releases the review after the meeting. Late releases require a reason after 48 hours. Employees acknowledge within five recorded working days or submit a written dispute. HR can record a written resolution. Disputes remain employee/HR-only.
10. Released outcomes appear in HR's tracker: development, mentoring/recognition, values/realignment discussions and applicable 30/60-day PIP checkpoints. These are tracked actions, not automatic employment-status changes or termination.
11. Compensation provides an authorized Finance handoff with released final scores. Multiplier interpolation follows the V3 bands, requires an entered company scorecard of at least 80%, and respects values holds. It does not calculate or execute payments or overwrite salary/bonus records.

## Privacy and integration

- HR and the assigned current manager can see anonymous peer averages after collection closes and three or more responses exist. Employees see results only after HR release. Retention answers remain HR-only. Respondent identities/response IDs are never returned alongside answers.
- HR can extend insufficient peer collection by up to three days after the original deadline. Compiled results cannot be reopened for additional responses. Response submission claims and deterministic MongoDB IDs prevent duplicate concurrent submissions.
- Existing Survey collections are reused for Alignment. V3 responses omit employee/account identity fields and timestamps; manager tags support team aggregates only after at least three responses. The alternate existing survey submission endpoint delegates V3 windows to the same checks.
- Alignment is separate from individual scores. V3 talent density is 50% Stars/Core share, 30% normalized Section B and 20% Alignment. It waits for released reviews covering all eligible staff; a partial selected-employee cycle is never presented as a company score.
- Staff Home, My Tasks, Performance and Notification Centre link to authorized review, peer and Alignment items. Notification previews and email bodies contain no assessment answers, medical or payroll details.
- Event emails use existing recipient resolution and durable delivery claims. HR owners are excluded from their own approval emails; General Manager email escalation is used for HR-owned reviews. Email and background-job deployment switches remain enforced.
- Daily reminders cover three/one-day deadlines, peer shortfalls, overdue actions, meeting dates, release SLA and follow-ups. Existing legacy reminder rules do not select V3 Open cycles as legacy Active cycles.
- Earlier reviews and qualitative monthly probation reviews remain on their existing workflows. Probation does not receive Section C. Existing records, scores, employee status, passwords, leave balances and account permissions are preserved.

## HR inputs and rollout prerequisites

HR must publish approved role scopes, targets, weights/group blends, data sources, owners and approval references. Several supplied role profiles are probation/reference profiles: they are not silently converted into Annual KPIs. HR must explicitly approve an Annual configuration before using it for an annual review. Missing or ambiguous role matches require HR mapping.

HR supplies reviewer nominations for small departments, verified company NPS/CSAT, meeting arrangements and review follow-up decisions. The application does not invent these inputs. MD reviews remain Board-administered outside this annual employee workflow. No automatic production backfill, migration or index installation was performed.

The documented Year-end 2026 example is 30 November to 27 December: self/peer deadline 6 December, manager deadline 13 December, meetings in Weeks 3–4. No live cycle was created automatically.

## Interrupted peer submission recovery

A task in Submitting is deliberately fail-closed; no automatic timeout deletes its claim. An authorized operator must stop all writers/schedulers, take a backup and follow the existing Task 02 integrity-lock recovery procedure before investigating. Locate the exact tenant/task and deterministic response ID produced by key('v3-response', tenant, task.id). If the response exists, reconcile completion to Submitted without changing answers. If no response exists and all writers are confirmed stopped, reset only that exact Submitting task to Assigned using a compare-and-set predicate and record the operator/reason in the audit trail. If uncertain, leave it blocked. Never bulk-remove claims or the persistent integrity lock while a writer may still be running.

## Validation

- Full backend: 1,707 passed, 321 skipped, five existing deprecation warnings.
- Full frontend: 365 passed in 52 suites.
- Strict CI and normal production builds both passed. Calculated V3 9-box placements are read-only in the UI and API; historical review tools remain compatible.
- Python compilation and whitespace checks passed.
- Tests use synthetic in-memory repositories with background jobs and outbound mail disabled. No production account, employee, assessment or database was used for test writes; no disposable database was created.
- No authenticated live HR/employee walkthrough is claimed. Automated workflow/authorization tests exercise the complete sequence and failure cases.
- Final V3-focused regression run after the last company-coverage safeguard: 90 passed, including circular reporting-chain, board-only and partial-company-report guards.

## Changed files

Backend: routes/performance_v3.py, routes/performance.py, routes/surveys.py, routes/compensation.py; utils/performance_v3.py, performance_v3_reviews.py, performance_v3_admin.py, performance_v3_alignment.py, performance_v3_reminders.py, performance_v3_scoring.py, performance_workflows.py, role_kpi_library.py, notification_centre.py, staff_home.py; automation/engine.py. New regression files: tests/test_performance_v3_end_to_end.py and tests/test_performance_v3_security.py.

Frontend: components/PerformanceV3Panel.js, PerformanceV3Review.js, PerformanceV3.css, PerformanceV3.test.js, PerformanceHandoffs.js, PerformanceTaskLinks.js, PerformanceWorkflow.js, CreateReviewDialog.js; pages/Performance.js, Performance.test.js, Compensation.js, MyTasks.js; services/api.js.
