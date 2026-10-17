# Task 10 — performance management

Local implementation extending the existing Performance page, `/performance` router, `performance_reviews` records, Staff Home and Notification Centre. Existing Tasks 01–09 changes are preserved. No production access, live-data changes, migrations, installed indexes, commits, pushes or deployment.

## Requirements and policy conflicts

Reviewed the locally supplied Solvit People System Developer Brief v1 (policy table, PDF p5; §5.9, p13), Employee Handbook v2 §§6.1–6.2 (p11), and FRD M05/review-cycle/scoring requirements (pp27–28 and the performance-form definitions). The documents are requirements, not authorization to change employee records or evidence that HR approved a disputed scoring policy.

| Requirement/source | Implementation / decision |
| --- | --- |
| Handbook §6.1: measurable role-specific OKRs agreed with the employee; first full cycle follows sign-off | Manager/HR assigns three to five explicit objectives, measurements, targets and due dates; employee acknowledgement is recorded server-side before self-assessment submission. Signed-off targets cannot be silently replaced. |
| Handbook §6.2 / FRD M05: two annual cycle types, each four weeks | HR configures Mid-Year/Year-End cycles, start date, self/manager deadlines and a calculated final HR deadline; duplicates and overlapping cycles are rejected. No active cycle is invented from today's month. |
| Handbook p11 / FRD p28: A 50%, B 30%, C 20%; C is Client Feedback | Available only as an explicitly selected, recorded HR-approved new-cycle policy. |
| Developer Brief p5: A 60%, B 25%, C 15%; C is Alignment | Conflicts with both weights and meaning of Section C above. Also available only with explicit recorded HR approval. Neither preset is installed as the production policy by this change. |
| FRD: Section A averages three to five KPI scores; weighted total is calculated, not manually supplied | Current reporting manager supplies each agreed KPI's 1–3 score and evidence. HR supplies verified normalized B/C inputs with an evidence reference. Overall is calculated from the immutable approved policy snapshot and rounded to one decimal. |
| Developer Brief §5.9: publish scores only after HR release | Employee-facing review APIs, history, profile timeline and Staff Home redact unreleased scores/manager assessments. Separate HR release is required after HR review. |
| FRD: peer/client inputs and consequences | Existing feedback forms and downstream modules are retained. This change does not fabricate feedback, infer conversions, launch disputed automatic consequences or change payroll. HR must approve conversion rules and evidence sources before operational use. |

Additional decisions: the exact peer-average conversion at boundary values, handling insufficient peer responses, Section C for non-client-facing roles, and whether any weighting redistribution is permitted remain subject to HR confirmation. A normalized input must have real, verified evidence; a missing input is not assigned a default or automatically reweighted.

The existing talent-density composite's 60/25/15 weights measure organizational health and are distinct from an individual's review weights. Its fabricated missing-survey baseline of 70 has been removed: incomplete evidence produces an insufficient-data state.

## Audit findings and implementation

1. **Unstaged writes:** the previous generic review PUT allowed managers/HR to set signatures and arbitrary statuses, recomputed totals using hardcoded weights, and triggered completion delivery without staged approvals. It now rejects those writes and directs callers to the authorized assessment workflow. Historical records are not recalculated.
2. **Workflow:** new reviews follow `Draft / Self_Draft → Self_Submitted → Manager_Submitted → HR_Reviewed → Completed`. Self-assessment belongs solely to the subject employee. Manager assessment requires the actual saved direct-report relationship and M05 write permission. HR review/release requires authorized HR, with explicit rejection of self-approval. Completed assessments cannot be silently overwritten.
3. **Cycles:** additive `performance_cycles` records contain deadlines, the chosen documented policy, HR actor, approval reference and timestamp. New reviews copy the policy snapshot. Later master-settings edits cannot change their calculations. Creating a review requires a configured cycle; duplicate canonical/native/legacy employee references cannot create another review for the same period through application paths.
4. **Goals:** use the existing review's `section_a_kpis` container rather than a separate goals module. Targets are entered by an authorized manager/HR, never invented. Employees report bounded progress with evidence; manager/HR verifies completion separately. Employee acknowledgement and subsequent target locking preserve agreed expectations.
5. **Privacy:** normal employees see their own reviews only. Current managers see their authorized direct reports; HR retains administration. Board-only employees remain outside the ordinary review workflow. Named nine-box access is limited to authorized HR; executives retain aggregate talent-density access rather than confidential individual records. Tenant-aware lookup protects legacy identities and rejects ambiguous references.
6. **Historical records:** scores remain stored unchanged. A legacy Completed/Imported record needs a separate HR publication approval to show its original scores to the employee. This adds publication metadata only. In-progress historical reviews require an approved reconciliation/resumption decision; they are not silently enrolled into a newly approved policy.
7. **Alternate form route:** legacy Form 06 start/submit/sign operations cannot bypass the staged assessment workflow. Existing forms are preserved for history; own employee reads hide their raw manager-score payload. Old Form 06 signature tasks no longer appear as executable tasks. Existing Form 07 self-review and Form 11 onboarding references remain available; there is no automatic copying or overwriting of their historical content.
8. **Audit/integrity:** cycle configuration, review creation, goals, acknowledgements, assessments, scoring, publication and nine-box changes are audited with actor/time and before/after evidence before mutation. The existing cross-worker integrity lock serializes writes. Unknown interruptions retain the lock for controlled operator recovery; no unsafe stale-lock expiry was added.
9. **Integration:** recipient-scoped, deduplicated notifications link to authorized reviews and use generic previews without scores/comments. Staff Home shows only the employee's pending self-assessment and safe review summary. Manager dashboard recognizes the new pending stages. The existing completion email integration is invoked only after HR publication; no new delivery channel is added.
10. **Frontend:** extend the existing Solvit-styled Performance screen with HR cycle configuration, full employee names, responsive scrolling, deadlines, goals, acknowledgement, employee/manager/HR actions, separate release and historical publication. HR retains the existing matrix and printable view. Errors, empty states and missing-data states remain explicit.

The existing rating-band labels and manual matrix taxonomy are retained; no automatic placement, compensation or disciplinary action is introduced. HR must confirm the final rubric and consequence process.

Cycle policy/deadline configuration and signed-off target definitions are intentionally immutable in this first safe workflow. Amendments, assessment returns/revisions and completed-score corrections need a separately approved, versioned process; no destructive edit endpoint is provided.

## Modified files for Task 10

- `backend/utils/performance_workflows.py` — scoped workflow, approved policy snapshots, goals, scoring, publication, audit and notifications.
- `backend/routes/performance.py` — extend existing router with cycles/goals/assessment operations; safe reads/history; guard legacy writes and matrix access; missing-data handling.
- `backend/routes/forms.py` — close legacy Form 06 write/read bypasses while retaining history.
- `backend/routes/employees.py` — safe performance summaries in profile/history/timeline.
- `backend/routes/dashboard.py` — include new pending workflow stages in manager counts.
- `backend/utils/staff_home.py` — own pending self-assessments and safe review projection.
- `backend/utils/notification_centre.py` — recipient/record-checked performance links.
- `backend/tests/test_performance_workflows.py` — new performance regressions, including real disposable MongoDB concurrency coverage.
- `backend/tests/test_password_change_enforcement.py` — first-login gate coverage for new endpoints.
- `backend/tests/test_iteration_18.py` — replace obsolete arbitrary-completion expectation with a bypass-rejection regression.
- `frontend/src/components/PerformanceWorkflow.js` — extend existing review detail with staged actions and HR cycle configuration.
- `frontend/src/pages/Performance.js`, `frontend/src/pages/Performance.test.js` — integration, privacy/status/error displays and frontend regressions.
- `frontend/src/services/api.js` — calls for the extended existing performance APIs.
- `docs/task10-performance-management-report.md` — this report.

Other existing working-tree changes belong to Tasks 07–09 and are preserved.

## Tests

Final verification of the finished implementation:

| Check | Result |
| --- | --- |
| Full backend `pytest backend/tests tests` | **915 passed**, 6 warnings, 145.09 seconds |
| Focused performance suite | **44 passed** |
| Full frontend suite | **126 passed**, 21 suites |
| Strict CI build (`CI=true`) | Passed; compiled successfully |
| Normal production build (`CI=false`) | Passed; compiled successfully |
| Python `compileall -q backend` | Passed |
| `git diff --check` | Passed; only Git's informational LF/CRLF notices |

The final complete run has no failures or skipped tests. Earlier cohort failures revealed board/own-unpublished matrix visibility assumptions and were resolved with explicit privacy regression coverage rather than weakening authorization.

Tests used synthetic in-memory fixtures and a guarded disposable MongoDB/API on localhost ports 27089/18089. Outbound application traffic was blocked. The existing synthetic document-scanner harness from Task 08 was retained for unrelated document integration tests; production scanning behavior is unchanged. No production or staging connection was made.

Cleanup verified: all five disposable localhost suite databases were removed; the synthetic API and MongoDB processes were stopped; `.mongo-test`, `.test-deps` and `.node-test` were removed; localhost ports 18089/27089 are no longer listening. HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`.

Coverage includes role/employee/tenant isolation; canonical and native legacy references; cycle policy/date validation; duplicate/overlapping cycles; cross-worker duplicate review prevention; signed-off goals; target injection; bounded progress; manager evidence/score validation; both approved policy calculations; HR-only review/release; self-approval rejection; immutable historical scores; legacy form bypasses; unreleased profile/timeline/dashboard redaction; recipient isolation and safe links; durable audit behavior and interrupted-write locking; mandatory first-login enforcement; and Tasks 01–09 regressions.

## Outstanding HR decisions and staging prerequisites

- HR must select and formally approve the applicable individual-scoring policy and Section C definition before creating real cycles. No production approval or historical policy reconciliation is claimed.
- Confirm peer-score and NPS/CSAT/alignment normalization, applicability exceptions, minimum valid feedback and the authoritative evidence sources. These are not inferred from absent data; HR records verified normalized scores and references.
- Confirm cycle dates, self/manager deadlines, late-submission handling and any review-return/amendment procedure. Deadlines are visible; this change does not invent automatic disciplinary penalties for late submission.
- Confirm the real employee links and saved line managers. A missing, changed or invalid manager cannot be bypassed with a supplied manager ID. Persisted M05 read-only/revoked overrides remain effective and must be reviewed by authorized IT/HR before enabling self-service. Special Finance/executive/custom-role manager assignments need the approved M05 permission configuration; a job title alone does not confer access.
- HR must decide which historical scores may be published, and how to resume pending legacy Form 06/review records. No historical score is automatically reweighted, adopted into a new cycle, merged or deleted.
- Automated 360 assignment/aggregation, normalization of raw feedback, review-meeting calendar booking, and automatic consequence/bonus/salary changes are not introduced by this focused workflow extension. Existing modules/forms are retained; these integrations need approved policy and staging validation.
- Use a consistent API version across workers during the eventual approved rollout; older workers must not keep accepting the retired unguarded review/form writes.
- Existing approved account, storage, notification/email and Task 02 database-index prerequisites remain. No index or migration was installed. Application writes are serialized, but direct database writers bypass application guards.
- Test release privacy end to end in staging, including profile, history, notifications, raw legacy forms, manager reassignment and overridden permissions. Verify completion-email delivery to synthetic accounts only before any approved rollout.
- Configure monitoring and controlled recovery for the persistent integrity lock per `docs/employee-integrity-rollout.md`. Audit and review writes are not a MongoDB transaction; quiesce writers and inspect recorded evidence before any operator recovery. Never remove an active writer's lock or blindly replay score changes.
- Reference PDFs remain local/ignored. The FRD references additional performance framework/rubric artefacts not supplied as separate files; this implementation does not claim to have reviewed those missing artefacts.

No database migration is required for these additive application fields. Readiness is for isolated staging validation after passing checks and HR configuration, not production deployment or approval of disputed policy.
