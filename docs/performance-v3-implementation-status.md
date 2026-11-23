# Performance V3 implementation and release report

12 November 2026. Supersedes the earlier work-in-progress status.

## 19 November 2026 review updates

- Employee KPI measurement, target and weight are read-only. Actuals and five permitted self-score choices remain editable; evidence is optional for historical compatibility and removed from the current form. Five values self-scores and examples precede reflections.
- Managers enter independent KPI scores and comments beside the employee responses. Differences require a comment on submission. Drafts do not advance the workflow or notify HR. Section A uses the weighted manager scores, including configured group blends.
- Employees select at least five colleagues from the company directory, with no maximum. Only colleagues with an open eligible review can be added. Private drafts and two optional comment categories are supported. Submitted responses remain final.
- Peer averages require at least three responses and closed collection. Managers and employees receive them only after release; retention stays HR-only. Comments have no attribution and are shuffled. Week 1 shortfalls use the existing daily notification/email pipeline.
- Talent density uses 50% Stars/Core share, 30% converted Section B average and 20% company Alignment score. Complete released coverage for all eligible FTE is required; incomplete coverage displays awaiting data.
- Configuring a cycle sends nothing. Opening it through Create and send reviews queues notifications immediately. A future start date does not defer delivery. No live cycle was opened during this update.
- The approved Solvit Alignment Survey framework was received on 20 November 2026. All 12 FTE question texts now match it exactly, with four questions each for Environment, Values Alignment and Rewards & Recognition. Create Review and the employee form display the three pillars and the labelled 1-5 scale. New windows snapshot the approved wording; historical stored survey windows are not rewritten.
- Peris's duplicate was consolidated under podhiambo@solvit.co.ke using an explicit reviewed transaction, retaining IT Lead and reporting links. Reporting-line corrections were applied separately and verified. No automatic startup migration was introduced.
- Five screenshots in Downloads show the real components with labelled example data for sign-off; they do not expose staff assessment responses.

Release checks for this update: 425 frontend tests in 62 suites passed; strict production build passed. Backend full run: 1,814 passed, 321 skipped, one MFA session test interrupted by a seven-hour machine pause; the MFA rerun passed (51 passed, one skipped). Workflow visibility and selection regressions passed after updating the earlier expectations. Tests used synthetic repositories with mail and background jobs disabled.

## Jessica sign-off amendments on 20 November 2026

A 23 November start calculates self/peer deadlines of 29 November, manager scores by 6 December and meetings/release by 20 December. Acknowledgement now allows two recorded working days after actual release, respecting the employee schedule and recorded holidays. No cycle was opened.

The self-review displays the full five-step KPI guide. HR peer progress displays received, chosen and submitted counts with minimum shortfalls; the tracker no longer returns named reviewer/task pairings. Scores and anonymous comments remain in the separate authorized assessment workflow.

Martin Munene's title was updated live to Acting Technical Manager, Motor Inspection and Valuation. Martin Kiarie was already recorded as Managing Director reporting to the Board; the public directory now resolves that explicit reporting root. The outdated supplied-weights approval note was removed from references and saved-library display without changing approved targets or weights.

## Implemented flow

1. HR edits and publishes role KPIs with an MD/line-manager approval reference. Drafts and historical versions remain in the existing library/audit records. Publishing assigns approved exact-role defaults to currently unassigned employees; it never overwrites an existing assignment.
2. HR maps employees to an approved role and may make approved individual amendments with a reason. Targets lock when a cycle opens. Role-change amendments cannot rewrite submitted or partially completed assessments.
3. Create Review opens one popup: choose employees, an existing cycle or a new Mid-year/Year-end cycle, year, start date and approval reference. Deadlines are calculated for four weeks; weights are fixed at 50/30/20. HR confirms the displayed existing Alignment Survey questions. No separate configuration page is required.
4. Employees see My role KPIs throughout the year and a review/deadline on Staff Home and Performance. They can save partial self-assessments, resume them and submit actuals, evidence, self-ratings, accomplishments and values examples.
5. Department colleagues receive separate peer tasks; MD reviews direct reports, and Executive Director accounts are excluded as staff peer reviewers. HR can nominate additional eligible cross-department reviewers. Peer submissions use separate assignment/completion and anonymous response records.
6. Managers confirm actuals in Week 2; changes require explanations. HR receives an actionable notification and email through the existing delivery infrastructure. HR can correct verified actuals with a reason and preserved history, requiring reassessment before release.
7. HR records verified company NPS/CSAT from Week 2. HR compilation requires manager completion, a closed peer window and at least three responses. Section A, B, C, final rating and placement are derived, not manually entered.
8. The manager proposes a date using the portal calendar and recorded availability suggestions. HR arranges the meeting manually, confirms it and records completion. Employee and manager receive portal notifications; no Outlook integration is introduced.
9. HR releases the review after the meeting. Late releases require a reason after 48 hours. Employees acknowledge within two recorded working days or submit a written dispute. HR can record a written resolution. Disputes remain employee/HR-only.
10. Released outcomes appear in HR's tracker: development, mentoring/recognition, values/realignment discussions and applicable 30/60-day PIP checkpoints. These are tracked actions, not automatic employment-status changes or termination.
11. Compensation provides an authorized Finance handoff with released final scores. Multiplier interpolation follows the V3 bands, requires an entered company scorecard of at least 80%, and respects values holds. It does not calculate or execute payments or overwrite salary/bonus records.

## Privacy and integration

- HR can see anonymous peer averages after collection closes and three or more responses exist. The assigned manager and employee see results only after HR release. Retention answers remain HR-only. Respondent identities/response IDs are never returned alongside answers.
- HR can extend insufficient peer collection by up to three days after the original deadline. Compiled results cannot be reopened for additional responses. Response submission claims and deterministic MongoDB IDs prevent duplicate concurrent submissions.
- Existing Survey collections are reused for Alignment. V3 responses omit employee/account identity fields and timestamps; manager tags support team aggregates only after at least three responses. The alternate existing survey submission endpoint delegates V3 windows to the same checks.
- Alignment is separate from individual scores. V3 talent density is 50% Stars/Core share, 30% normalized Section B and 20% Alignment. It waits for released reviews covering all eligible staff; a partial selected-employee cycle is never presented as a company score.
- Staff Home, My Tasks, Performance and Notification Centre link to authorized review, peer and Alignment items. Notification previews and email bodies contain no assessment answers, medical or payroll details.
- Event emails use existing recipient resolution and durable delivery claims. HR owners are excluded from their own approval emails; General Manager email escalation is used for HR-owned reviews. Email and background-job deployment switches remain enforced.
- Daily reminders cover three/one-day deadlines, peer shortfalls, overdue actions, meeting dates, release SLA and follow-ups. Existing legacy reminder rules do not select V3 Open cycles as legacy Active cycles.
- Earlier reviews and qualitative monthly probation reviews remain on their existing workflows. Probation does not receive Section C. Existing records, scores, employee status, passwords, leave balances and account permissions are preserved.

## HR inputs and rollout prerequisites

HR must publish approved role scopes, targets, weights/group blends, data sources, owners and approval references. Several supplied role profiles are probation/reference profiles: they are not silently converted into Annual KPIs. HR must explicitly approve an Annual configuration before using it for an annual review. Missing or ambiguous role matches require HR mapping.

Employees choose their colleagues for peer reviews. HR supplies verified company NPS/CSAT, meeting arrangements and review follow-up decisions. The application does not invent these inputs. MD reviews remain Board-administered outside this annual employee workflow. No automatic production backfill, migration or index installation was performed.

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

## Finance KPI amendment on 23 November 2026

Finance and Operations now use a single KPI list totalling 100%. The approved nine-row reference weights are 15, 10, 15, 15, 10, 5, 10, 10 and 10 percent. Saved Finance role drafts are presented and validated without the old internal Finance/Operations groups, preserving HR's amended goals and individual weights. Other roles retain their existing group support. Publishing stores the flat configuration; existing review snapshots and scores are not rewritten by this display/validation change.

Checks: 36 backend regressions and seven editor checks passed. The reference matches the supplied KPI/weight image; it does not import example actual results or baselines as staff assessments.

## Review distribution confirmation on 23 November 2026

The Create Review popup now provides Select all listed employees, Clear selection and an explicit selected count. A successful send must return the expected cycle ID with Open status before the interface reports confirmation. The popup keeps a visible receipt until HR chooses Done to view the tracker. This confirms the portal review requests; email delivery follows the configured notification service. An unconfirmed response retains the prepared cycle and selection and instructs HR to check the tracker before retrying. Existing cycles can be selected when adding remaining employees. No live review was sent while building or testing this change.

## Grace employee assignment repair prepared on 23 November 2026

The role-library correction does not overwrite an employee's existing assignment. Grace's reported screen still contains the older group-relative weights. An explicit operator repair is available in scripts/repair_grace_kpis.py. It verifies Grace's identity and nine objectives, preserves KPI IDs, wording and targets, previews a fingerprint, and requires that fingerprint for transactional apply with recovery copies and an audit event. It refuses started or submitted assessments and has no startup hook or notification calls. Seven synthetic checks passed, including rollback, stale plans and idempotency.

The local code session has no production MONGO_URL/DB_NAME. The repair has NOT been applied or verified against Grace's live record. It must be previewed and applied in an authorized backend environment with the existing database connection; publishing this script alone does not correct the live assignment.

## Explicit deployment correction approved on 23 November 2026

Following the instruction to correct Grace's individual account through code immediately, the same tested repair is now invoked once during backend startup, using the existing backend database connection. It is restricted to the verified Grace identity and nine approved Finance objectives. It creates recovery copies and a durable audit marker, updates the stored assignment and untouched Year-end 2026 review drafts transactionally, and refuses started or submitted assessments. Once marked complete it never overwrites later HR amendments. It creates no reviews, tasks, notifications or emails. The public health response exposes only the release hash and a generic applied/needs_review/unconfirmed state, with no employee identity or KPI data, so the deployment result can be checked without browser access.

## HR deletion of unused cycles on 23 November 2026

Create Review now shows Delete unused cycle after HR selects an existing cycle. The confirmation identifies its period and dates and requires a reason. The action archives records atomically instead of physically deleting history. It refuses assessment drafts/answers, submitted work, peer tasks already started, peer responses, Alignment responses and company feedback. An unused cycle can be removed so HR can create the correct cycle for that period. Unused review/peer/survey requests are closed, pending cycle email alerts are cancelled, and obsolete portal alerts are hidden. Emails already processed cannot be recalled. No live cycle was deleted during implementation or testing.

## Earlier-cycle selector correction on 23 November 2026

The duplicate-period check included earlier cycles while the HR selector listed only V3 cycles. The selector now includes earlier setups, labelled manage-only, so a blocking setup is visible. An earlier setup can be archived only with no linked review records; cycle identity aliases are checked so storage-ID links cannot evade the protection. Earlier setups cannot be sent through the V3 popup. No live cycle was archived while implementing this fix.
# HR review send readiness — 23 November 2026

Preparation and sending now share one readiness check. The HR setup response includes `review_ready` and exact `review_issues` for Annual KPI scope, complete targets/weights and valid reporting chains. The assignment picker no longer equates an existing assignment with readiness. The send popup lists corrections by employee, disables blocked options and offers selection of all ready employees. Sending revalidates stored records before any review or notification is written and reports specific reasons if data changed. This change does not rewrite staff assignments, change reporting lines or send reviews automatically.

## HR-authorized status-based KPI assignments

Employee lifecycle Onboarding/Probation or onboarding recorded In_Progress requires Probation KPI scope. Other eligible FTE staff use Annual scope. New explicit HR assignments and exact-role account setup assignments use that status, retaining the published role goals and approved individual targets/weights. Annual opening independently rejects staff still in onboarding/probation.

The authorized deployment correction changes only existing valid assignment scopes, preserving role, goals, targets and weights. Each change uses a transaction, original-record recovery copy, version check and durable per-employee audit marker. Started reviews, missing assignments and invalid KPI data are skipped; no existing review or employee status is changed, and no notifications are created. Health reports aggregate correction outcomes only. HR preparation displays the employee status, onboarding status and expected scope. This does not infer a different job role or invent missing KPI targets.
