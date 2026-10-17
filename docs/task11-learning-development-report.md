# Task 11 - Learning & Development

## Scope and outcome

Extended the existing M08 L&D module, training request records, IDPs, skills matrix, private Document Centre, Staff Home and Notification Centre. No employee roster, reporting relationship, historical training or account was rewritten. Tasks 01-10 and all pre-existing uncommitted work are preserved. No production/staging access, migrations, index installation, commit, push or deployment was performed.

## Audit and requirements traceability

Reviewed the local authoritative PDFs in `docs/reference/`. Page references below are PDF page numbers.

| Source | Requirement / finding | Implementation |
| --- | --- | --- |
| Developer Brief v1, section 5.9, p13 | Personal IDPs, training requests, manager oversight; extend M08 | Existing module extended; employee/manager/HR scope enforced on server. |
| FRD, M08 section 6.8, p32 | Structured requests: course/provider/cost/duration/development goal | Existing request endpoint retained, optional IDP goal link retained, published courses snapshot their approved metadata. |
| FRD, M08 section 6.8 | Manager approval; additional HR approval when cost exceeds KES 5,000 or duration exceeds two days | Current saved manager must approve first; server calculates the threshold; no self-approval or supplied-manager bypass. HR may reject pending nominations, but cannot skip manager approval. |
| FRD, M08 section 6.8 | Training log, actual completion date, HR-added external certificates | Authorized requests/assignments become the learning log. Employee declares completion; conservative HR verification gates final completion. HR can record an authorized external certificate against approved training. |
| Handbook v2, section 6.5, p12 | IDP at first review and updated each cycle; goals, support and timeline | Existing employee-profile IDP workflow preserved; partial updates now retain historical goals and record audit evidence. No invented goals or automatic record creation. |
| Task 11 request | Programmes, courses, sessions, eligibility, schedules and completion requirements | HR catalogue with optional Programme > Course > Session hierarchy, publication/archive controls, department/worker-type eligibility and versioned assignment snapshots. |
| Task 11 request | Staff learning view, manager/HR tracking, notifications and Staff Home | Existing L&D page gains assigned learning/history and catalogue views; scoped requests provide participation tracking. Generic in-app events and canonical related-record links reused. |
| Tasks 07-08 / document privacy requirements | Private evidence and certificates | Existing M01 plus document-level authorization, owner, publication and restricted-category checks; no file paths or unrestricted URLs. Existing HR-only upload, scanning and sharing rules preserved. |

Audit found that HR approval could previously bypass manager approval and the AI assignment action inserted Approved training directly. Both now use the same nomination and approval rules as normal requests. Existing bulk assignment also uses the shared validation, scope, duplicate checks, audit and notification flow. Profile training/IDP aggregation now respects M08 access, so M01 access cannot bypass a revoked learning permission.

## Implemented behavior

- HR can create/edit/archive catalogue items, define explicit eligibility and completion requirements, and nominate employees. Published Course/Session assignments snapshot the catalogue version, dates, requirements and cost; later edits do not overwrite existing training. Empty eligibility lists explicitly mean all eligible employees. No hardcoded employee roster or new dependency was introduced.
- Employees see only authorized personal learning; eligible managers see themselves/direct reports and HR sees authorized participation across employees. Catalogue eligibility also checks ancestor restrictions. Canonical IDs, legacy string/native ObjectId references and current saved manager relationships are resolved through existing identity helpers.
- New nominations require an eligible employee and valid manager chain. Missing/conflicting links fail safely. Board-only records are excluded from this learning workflow. Historical records remain readable within permission scope; unknown legacy approval states require HR reconciliation instead of silently advancing.
- Catalogue assignment, manual request, bulk nomination and AI nomination share validation and cannot create an already existing matching assignment. Writes use the existing cross-worker persistent integrity lock. Programme batches validate the whole selection before starting inserts; no batch transaction is claimed.
- Approval status transitions are enforced on the backend. Cost/duration thresholds cannot be bypassed by client flags, another employee ID, a forged manager, replay or HR self-approval. Changed manager snapshots require reconciliation.
- Employees declare the actual completion date and evidence for approved learning. HR separately verifies or returns it with a reason. HR can record external certificate completion only with an authorized existing private document. Completed history is not editable through these actions; returned/resubmitted declarations retain history.
- Certificate selection excludes unauthorized documents. Downloads reuse authenticated Document Centre endpoints, which recheck permissions. HR-only certificates are not automatically published. Employees who need an unshared/required certificate must use the existing HR upload/sharing process; employee uploads were not enabled.
- In-app assignment, decision, completion and due/overdue events use deterministic recipient/event keys. Previews remain generic and exclude justification, medical details and certificate contents. Deadline checks reuse the daily automation cron, only for real saved deadlines; each due/overdue event is deduplicated. Staff Home adds own learning actions with canonical links.
- The existing `lnd.training_assigned` email trigger is reused once per new request, including bulk/AI paths. No new email/SMS provider, duplicate parallel reminder schedule or delivery guarantee was introduced. No existing training-deadline email rule was found, so deadline reminders added here are in-app only.
- Catalogue, approvals, IDPs, skills and completion mutations write audit evidence before data changes. Failed unexpected writes retain the persistent lock, following the existing controlled operator recovery procedure.
- Existing IDP and skills UI remain in place. Skills records are not automatically relabelled. Responsive catalogue, request/history and completion controls include loading, empty, retry and server-error states.

## Files changed for Task 11

- `backend/utils/learning_workflows.py` - new shared catalogue, eligibility, nomination, approval, completion, evidence, audit, notification and deadline helpers.
- `backend/routes/lnd.py` - extend existing routes; add catalogue CRUD/archive-by-update, assignment and completion endpoints; protect IDP/skills updates and scoped projections.
- `backend/routes/ai_actions.py` - route AI nominations through the normal guarded workflow.
- `backend/routes/employees.py` - permission-aware safe learning/history projection in the aggregated profile.
- `backend/utils/staff_home.py` - personal learning actions and canonical links.
- `backend/utils/notification_centre.py` - canonical training links matching the L&D list.
- `backend/automation/engine.py` - invoke deduplicated training deadline checks from the existing daily cron.
- `backend/tests/test_learning_workflows.py` - synthetic workflow, security, document, audit, notification and real MongoDB concurrency regressions.
- `backend/tests/test_employee_authorization.py` - stage-aware training approval fixtures preserving existing isolation tests.
- `backend/tests/test_password_change_enforcement.py` - new routes covered by the existing mandatory password-change gate.
- `backend/tests/test_employee_profile_display.py` - adapt the profile fixture for the added M08 authorization, retaining Task 01 assertions.
- `backend/tests/test_staff_home.py` - learning fixture and own-record/canonical-link regression.
- `frontend/src/components/LearningWorkflows.js` - catalogue and authorized completion/certificate controls.
- `frontend/src/pages/LnD.js`, `frontend/src/pages/LnD.test.js` - integrate learning/history/catalogue, scoped nominations and approvals; frontend regressions.
- `frontend/src/services/api.js` - calls to extended existing L&D APIs.
- `docs/task11-learning-development-report.md` - this report.

Other existing working-tree changes belong to earlier tasks and are retained.

## Verification

| Check | Final result |
| --- | --- |
| Full backend `pytest backend/tests tests` | **971 passed**, 6 warnings, 132.00 seconds; no failures or skips |
| Focused Task 11 learning suite | **50 passed**, including real localhost MongoDB concurrency and profile permission tests |
| Full frontend suite | **137 passed**, 22 suites; no failures |
| Strict CI build (`CI=true`) | Passed; compiled successfully |
| Normal production build (`CI=false`) | Passed; compiled successfully |
| Python `compileall -q backend` | Passed |
| `git diff --check` and new-file whitespace validation | Passed; Git LF/CRLF notices are informational |

Coverage includes HR catalogue permissions and validation, hierarchy/eligibility, legacy identity formats, direct-report visibility, forged IDs, duplicate assignment prevention, missing managers/exited records, approval thresholds/stages/self-approval, completion declarations and verification, private document ownership/sharing, immutable completion history, recipient isolation/deduplication, AI/bulk paths, mandatory password-change protection, durable audits and retained interrupted-write locks, Staff Home integration, canonical notification links and Tasks 01-10 regressions.

The first complete run found two outdated profile mock failures, resolved by mocking the newly required learning permission check while retaining manager/department assertions. A subsequent rerun was aborted because restarting the synthetic seed harness against its old test database caused a duplicate-seed startup error; a fresh disposable database resolved this harness issue. The final complete run above passes against the finished application.

Tests use synthetic fixtures and guarded disposable MongoDB/API services on localhost ports 27089/18089. External application traffic is blocked by the local harness. Existing document integration tests use the Task 08 synthetic scanner verdict; production scanning remains fail-closed. No live employee records or credentials were used.

## HR decisions, limitations and staging prerequisites

- FRD describes HR as read-only for IDPs while the existing approved application grants HR Full M08 access. Existing privileged HR functionality is preserved as requested; HR must approve any narrower IDP ownership matrix before changing permissions.
- FRD skill levels are Developing/Proficient/Expert; the existing application has Beginner/Intermediate/Advanced/Expert. No historical relabelling or assumed equivalence was applied. HR must approve a mapping if standardization is required.
- Handbook references a separate L&D framework; FRD career pathway maps and role competency material are not supplied as standalone authoritative artifacts. Career maps, automatic skill progression, budgets, attendance integrations and invented targets are not generated.
- Confirm whether HR verification of employee completion, mandatory document categories, certificate sharing and any exception approval for top-level employees match HR's final operating procedure. New requests with missing managers cannot bypass the workflow. A job title alone does not confer manager access; review actual M08 grants for special-role managers in staging.
- Reconcile ambiguous/duplicate historical training or IDP records and legacy approval states read-only before any separately approved repair. Historical Approved/Completed records are preserved, not retrospectively reapproved or rewritten.
- Verify synthetic employee/manager/HR journeys in isolated staging, including eligibility, manager changes, revoked M08/M01 overrides, first-login restrictions, document scanner/storage settings, archive behavior, cron execution and email suppression/delivery. Email infrastructure is best-effort; this task does not claim exactly-once email delivery.
- No migration is required for these additive application fields and catalogue records. No indexes were installed. Existing Task 02 index prerequisites remain; application guards do not constrain direct database writers or older API workers. Roll out one consistent API version across workers after approval.
- Mutations, audit and notifications are not a MongoDB transaction. A process interruption can leave partial evidence/data/notifications and the persistent lock intentionally remains. Operators must quiesce writers, inspect recorded state and follow `docs/employee-integrity-rollout.md`; never remove an active writer's lock or blindly replay a batch.
- This is readiness for isolated staging validation after passing checks and HR configuration, not production policy approval or deployment.

Cleanup verified: both disposable suite databases were removed (per-test databases also clean themselves up); the synthetic API and MongoDB processes were stopped; `.mongo-test`, `.test-deps` and `.node-test` were removed; localhost ports 18089/27089 are no longer listening. HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`.
