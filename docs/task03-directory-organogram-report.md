# Task 03 - Staff Directory and Organogram

Updated 14 October 2026. Task 04 has not started. The additional local closure
work described below is uncommitted; prior Task 03 commit 7afbe1f is preserved.

## Status and preserved baseline

Task 03 functionality is implemented locally under the conservative defaults
explicitly authorized by the user. Controlled staging UAT is the next step;
HR policy approval and actual roster reconciliation are still pending.
This report supersedes earlier missing-document and incomplete-directory findings.

The original clean baseline was `cbdba84c72a2601ff261b08da4c40c52ff576309`
(Task 02). Task 03 was subsequently committed/pushed as
`7afbe1f700fc17352cce58d644419b4efbff14ce`; HEAD remains at that commit.
Task 01 `83f0b4f4401f013ae694fe11e57b0e9b3c80bb88` remains an ancestor.
All prior Task 01/02/03 fixes are preserved, with additional local Solver
security and read-only reporting verification below. No production access, live employee updates,
migration, index installation, new commit, push or deployment occurred during this additional closure work.

## Reference documents and requirements traceability

`docs/reference/` was absent in this checkout. The five previously supplied
Downloads PDFs were copied unchanged into that requested directory, and their
SHA-256 equality to the supplied sources was verified. Relevant requirements
and the visual Team Directory role chart were reviewed. Source instructions to
import, delete demo records, change titles/departments or update exits are
requirements for a separately approved reconciliation, not authorization to
execute them now.

- `docs/reference/Solvit People System — Developer Brief v1.pdf`
- `docs/reference/Solvit Solver Directory - September 2026.pdf`
- `docs/reference/Solvit Team Directory - 2026.pdf`
- `docs/reference/Solvit_Employee_Handbook_v2 (1) (1).pdf`
- `docs/reference/Solvit_People_Platform_FRD.pdf`

The Brief section 3 extends the FRD and gives the Handbook precedence for
conflicting policy. Handbook section 4.1 separately recognizes individual
contract precedence for specific employment provisions. No precedence rule
substitutes for confirming a person's reporting assignment.

| Requirement | Source | Status | Evidence / limitation |
| --- | --- | --- | --- |
| Extend existing platform and preserve prior fixes | Brief sections 1-2; user Task 03 | Implemented | Existing React/FastAPI/MongoDB architecture, profile manager-name fallback and configurable department edits retained. |
| Searchable, responsive staff-facing directory | Brief section 5.6 pp10-11; user item 1 | Implemented | `/staff-directory` page, navigation, responsive cards, accessible search and department filter. Search covers name, title, department and contact responsibility. |
| Six documented departments | Brief Appendix A pp24-26; Team pp1-2 | Implemented for presentation | Six reference filters/notes are loaded from backend configuration. Unknown saved departments remain visible separately; no employee or master record remapping. |
| Department Contact for notes | Brief section 5.6; Team pp1-2 | Implemented | Exact published notes in `backend/config/staff_directory.json`, with read-only workforce-master contact_for overrides. Operations has no such note in the source and remains blank pending HR wording. |
| Name, title, department and business contacts | Brief section 5.6; Team pp1-2; user items 1-2 | Implemented conservatively | Valid single saved work_email; dedicated work_phone only with literal boolean work_phone_directory_approved=true. No fallback to personal phone_number/email. No roster hardcoded into runtime logic. |
| Photographs only with confirmed authorization | Brief section 6 p20; user item 2 | Implemented by withholding | All public projections and cards omit photographs. No consent or approval is assumed from an existing URL. Any future photo-display/consent workflow needs HR approval and separate implementation. |
| Consistent server-side staff access | Brief section 4 pp6-8; user item 2 | Implemented | All three public endpoints share a staff-role/eligibility guard. Ordinary employee requires a uniquely resolved eligible Full_Time/FTE account link. Solver/custom/unlinked/ineligible accounts cannot bypass via the legacy directory or organogram endpoint. Existing staff administrative layers retain access; private HR APIs remain separate. |
| Exited and Board-only ordinary-staff exclusion | User conservative-default instruction; Brief section 5.6 active-staff requirement | Implemented | Exited/unknown/conflicting/restricted states excluded; board_only excluded for ordinary roles even for their own record. Existing Board/IT public exception retained. Final eligibility/leadership policy needs HR sign-off. |
| Confidential HR information unavailable to peers | Brief section 4.1 p8; Handbook sections 9.2-9.3 p16 | Implemented | Explicit scalar whitelist; salary, bank, medical, disciplinary, personal contacts, photos, role bands and lifecycle/performance badges absent from public outputs. Nested malformed metadata cannot disclose private objects. |
| Canonical/legacy ID lookup, duplicates and cycles | FRD M01 p21; user items 3/5 | Implemented | Canonical/storage aliases, collision detection, hashed unique node keys, safe missing-manager fallbacks, iterative cycle handling and bounded depth. Ambiguous employee identities cannot be selected by picker. |
| Preserve role-level chart and actual manager links | Brief section 2 p2; Team p4; user item 3 | Implemented | Collapsible reference chart rendered directly from Team p4, distinct from live employee graph. Stored links unchanged; unavailable/ambiguous/cycle/root assignments flagged for HR confirmation. No title/department-based manager inference. |
| 21-person read-only roster reconciliation | Brief Appendix A; Team pp1-3; user item 4 | Implemented as offline tool | Reads reference PDFs and an already authorized local JSON snapshot; redacted issues for missing/extra/exited/demo candidates, duplicate IDs/emails/names, department/contact-email/title mismatch and unresolved managers. No database/network/write API; no automatic employee actions. |
| Actual named roster and reporting accuracy | Brief Appendix A; Team pp3-4 | Pending HR/data review | Tool verified source count 21 and six departments, not production membership. Board/IT Lead/acting assignments and Executive lateral relationship require explicit employee-ID confirmation. |
| Full tests/builds and HR staging acceptance | User item 5; Brief section 8 p24 | Partially implemented until UAT | Technical results below; desktop/mobile role UAT and HR policy sign-off remain required. |
| Separate Solver region/area directory | Brief section 5.6 p11; FRD M02 p22; Solver p1 | Outside this staff-directory completion | Five sources retained. Solver records are not imported or folded into the FTE reference roster. Separate restricted Solver directory remains a distinct work item, not Task 04 started here. |

## Implementation and audit findings

- Previously, public directory and organogram visibility differed; the graph
  leaked Board-only metadata and overwrote nodes with duplicate employee IDs.
  Both now share tenant-aware projection and authorization. Tenant_id is kept
  in the database source projection for correct non-Solvit filtering but omitted
  from public output. Missing tenant compatibility is confined to Solvit.
- Interim visible states: Active, Onboarding, Probation, On Leave, Notice Period
  and Exiting (formatting equivalents recognized). Candidate, Suspended, PIP,
  Realignment, unknown/missing status and conflicting restrictive legacy flags
  are withheld. State itself is never returned. Ordinary employee access also
  requires recognized full-time employment; missing/unknown type fails closed.
  Administrative HR views and existing record editing remain unchanged.
- Directory-role guard permits employee, line_manager, hr_admin, hr_manager,
  finance, executive, it_admin and board. Ordinary employee eligibility is
  resolved server-side; forged client role/employee query values are ignored.
  Unsupported/custom roles require explicit policy approval before inclusion.
- Existing FTE/job-level/employment formatting compatibility is retained in
  eligibility and employee edits. Saving unchanged legacy employment, role,
  status, manager, department or email does not rewrite it.
- All identifiers are indexed before visibility filtering so a hidden/exited
  duplicate cannot be chosen as a manager. Cycles/depth splitting affect only
  presentation, with all eligible visible nodes retained. Hidden/missing manager
  cases share an unavailable response without disclosing hidden identities.
- Role/team reference boxes are an image, not fake employee records or inferred
  assignments. Neutral organogram card borders avoid confidential status badges.
- Public contact settings are read directly; no lazy settings seeding or writes.
  The record whitelist reads only view/visibility/relationship fields. Approved
  phone fields are optional read inputs, not new provisioning or schema writes.

## Offline reconciliation usage

Run from the repository root in a local document-review Python environment
with optional `pdfplumber` available:

```powershell
python backend/scripts/reconcile_staff_roster.py --snapshot integrity-reports/staging-employees.json --output integrity-reports/task03-roster-review.json
```

The operator must supply an already authorized snapshot. The tool does not
export or connect to any database and has no Mongo URL/credentials option.
Use only needed fields: _id/id, tenant_id, full_name, work_email, department,
role_title, lifecycle_state/status/employment_status, line_manager_id and
optional is_demo. JSON list or an employees-list wrapper is accepted; native
Mongo Extended JSON ObjectId aliases are recognized. No salary/private fields
are needed. Report E/R labels refer to tenant-filtered snapshot/reference order;
no names, emails, phones or internal IDs are emitted. The tool refuses existing
outputs and overwriting inputs/reference files. Reference parsing fails closed
if the expected PDF structure/count or Brief review flags cannot be recognized.

The source parser confirmed 21 unique reference names across six departments,
eight Brief-listed demo candidates and one explicitly listed exit for review.
Only synthetic snapshot comparisons were run. No claims are made about actual
missing, extra or duplicate production employees. A contact-email mismatch is
not permission to replace a login email: shared inboxes and personal account
addresses must remain distinct.

## Validation

- Full backend suite: **637 passed**, six warnings; final fresh full run completed in 122.44 seconds.
  Earlier runs exposed the logout cutoff edge and three lookup mock assertions
  affected by explicit tenant scoping. Both were corrected and the entire suite
  rerun; failed/interrupted attempts are not counted as passing checks.
- Full frontend suite: **60 passed across 12 suites**.
- Strict CI build (`CI=true`): **passed**, no lint/hook-dependency warnings.
- Normal production build (`CI=false`): **passed**.
- Python compilation and tracked/new-file whitespace checks: **Passed**.

Coverage includes Task 01/02 regressions, legacy/native IDs, alias collisions,
missing/hidden managers, cycles/deep chains, tenant projection, conservative
status/Board visibility, approved phone versus personal-contact redaction,
role/alternate-route denials, search/filter/responsibility matching, all six
filters, error/empty states, reference chart separation and offline reconciliation
redaction/non-mutation/overwrite safeguards. Source-parser tests require the
optional document-review dependency; no service dependency manifest changed.

The first full backend attempt was interrupted by a very long elapsed run
(1h51m) and reported 11 failures in one HTTP module. The fresh full rerun outcome
is recorded above; the interrupted run is not counted as a passing check.
Cleanup status: All eight owned disposable databases were dropped and absence
verified; API/Mongo processes stopped; workspace runtimes/downloads removed;
neither localhost test port retained a listener. MongoDB file handles initially
delayed runtime removal; the verified workspace cleanup retry succeeded.

## Modified files (all local Task 03 changes relative to Task 02)

```text
backend/config/staff_directory.json
backend/routes/employees.py
backend/scripts/reconcile_staff_roster.py
backend/tests/integrity_fakes.py
backend/tests/test_staff_directory.py
backend/tests/test_staff_views.py
backend/utils/employee_integrity.py
backend/utils/roster_reconciliation.py
backend/utils/staff_directory.py
backend/utils/staff_views.py
docs/task03-directory-organogram-report.md
frontend/src/App.js
frontend/src/assets/solvit-role-organogram.png
frontend/src/components/EmployeePicker.js
frontend/src/components/EmployeePicker.test.js
frontend/src/components/OrgNode.js
frontend/src/components/Sidebar.js
frontend/src/pages/Employees.js
frontend/src/pages/EmployeesCompatibility.test.js
frontend/src/pages/Organogram.js
frontend/src/pages/Organogram.test.js
frontend/src/pages/StaffDirectory.js
frontend/src/pages/StaffDirectory.test.js
frontend/src/services/api.js
frontend/src/utils/staffDirectory.js
```

The five unchanged `docs/reference/` PDFs listed above remain local and are
ignored by Git because the repository is public. They are not published.
The source-dependent parser/CLI tests skip explicitly on checkouts without
these confidential references or the optional pdfplumber review dependency;
all application/privacy/reconciliation unit tests remain independent of them.
`.gitignore` also changed to protect these local reference files.

## Remaining decisions, source conflicts and staging prerequisites

1. HR must approve visible employment/lifecycle states, Board/IT exception and
   ordinary staff exclusions. Conservative withholding remains active meanwhile.
   HR must confirm dedicated business-phone ownership/approval. Photos stay off;
   future photo consent/display is a separate approved change. Operations contact
   wording is absent in the Team document and is deliberately not invented.
2. HR must confirm actual roster/title/department/email/exit and effective-dated
   manager assignments. Reference chart roles do not establish every named link;
   IT Lead, acting manager and Executive lateral relationship need resolution.
   No automatic demo deletion, merging, record correction or reassignment.
3. Run offline reconciliation only on an authorized staging snapshot, review
   redacted findings with the source privately, then approve any separate data
   correction plan. Functional changes require **no database migration**.
   Task 02 backfill/reconciliation/unique-index and lock-recovery prerequisites
   remain documented separately and were not executed.
4. Staging UAT: eligible FTE, unlinked/unknown-type employee, HR, manager, Finance,
   Executive, Board, IT and denied Solver/custom accounts; direct API and page
   access; desktop/mobile search and six filters; no sensitive contacts/status/
   photos; role-chart comparison and unresolved reporting notices; private HR
   records and unchanged employee-edit saves. HR sign-off closes Task 03.
5. All-tenant identifier reads deliberately preserve global collision detection;
   measure 250-person performance in staging. Depth above 32 is split/flagged.
   Inherited reportlab/qrcode manifest omissions and Task 02 operational
   prerequisites still require staging environment verification.
6. Document conflicts recorded for later approved work: FRD Express/PostgreSQL
   stack versus the existing user-authorized FastAPI/MongoDB stack (no rebuild);
   older FRD departments/counts superseded by Brief/Team; Handbook performance
   weights 50/30/20 versus Brief/current 60/25/15; Handbook manager+HR leave
   approval versus Brief short-window manager-only approval. Stated Handbook
   precedence applies to planning, with corrected HR acceptance criteria needed.
   Solver regional summary/detail counts and missing contact data need review
   before any separate Solver import. No broader policy-module work started.

All requested technical checks passed. Ready for controlled staging validation under the interim defaults.
This is not HR policy sign-off, production readiness, or authorization to deploy.


## Additional closure: confirmed structure and Solver security

The user authorized proceeding with the supplied reference documents and confirmed
IT/Valuation reporting structure. This authorizes local implementation and
verification work, not production access, record mutation, migration or deployment.

### Reference data and confirmations

- HR confirmed IT Lead and Valuation Team manager. Their actual names are in
  ignored `docs/reference/hr-reporting-confirmations.json`, not application
  runtime constants. The original PDFs remain byte-for-byte unchanged.
- The private reference-only plan is
  `integrity-reports/task03-confirmed-reference-plan-2026-10-14.json`. It validates
  21 FTE reporting targets and 109 named Solver rows against the supplied files.
  The Solver PDF says 118, so its nine-row difference remains a source-data
  decision, not permission to invent or create people. One listed phone is absent.
- Named manager targets combine confirmed role holders and chart edges; team
  branches remain reference proposals subject to individual exceptions. The
  Executive's lateral link is not converted to a manager edge; no unnamed Board
  employee is created. Acting-assignment metadata and original reference titles
  remain intact unless a specific HR title override is supplied.
- New `backend/scripts/verify_workforce_reporting.py` reads local PDFs, HR
  confirmations and an already approved JSON snapshot containing employees and
  solvers arrays. It has no database/network/migration connection and no write
  API. Output must be a new file within ignored integrity-reports; existing
  reports and source/input files cannot be overwritten. Names and current
  manager name/department/role are intentionally confined to that private report.
- The pure checker supports canonical/storage/Extended JSON identity aliases,
  ambiguous IDs/matches, missing/invalid managers, cycles, exited members,
  classification/department/title/contact-email mismatches and extra records.
  It identifies a proposed manager record label only when uniquely resolved.
  Current records have not been supplied, so no actual current assignments,
  missing/extra members or correction completion are claimed.

Example future authorized offline check:

```powershell
python backend/scripts/verify_workforce_reporting.py --snapshot integrity-reports/approved-staging-workforce.json --output integrity-reports/reporting-verification.json
```

### Security findings fixed locally

Previously Solver detail lookup allowed any authenticated user to retrieve a
whole document by ID without ownership/tenant checks. List/update/rating and
onboarding paths also had inconsistent or missing scope checks; formatted phone
duplicates bypassed create/import/update safeguards.

- `backend/utils/solver_access.py` now centralizes M02 role/scope enforcement,
  qualified Solvers Manager checks through the saved canonical employee link,
  tenant-aware canonical/legacy Solver lookup and unambiguous self-account
  resolution. A storage alias cannot bypass a duplicated canonical ID. Ordinary
  Solver scopes cannot be widened to company-wide read/write by a matrix override.
- Self accounts resolve from a trusted explicit solver_id or unique saved email.
  Blank/recycled phone, name, department or supplied request IDs are not account
  identity. Ambiguous/missing links fail closed. Explicit account links are checked
  for competing owners, including native Mongo storage-ID aliases.
- HR retains private record functionality. Operational manager and self views
  whitelist necessary fields, excluding banking, statutory identifiers, medical,
  disciplinary/free-text HR notes and credential material. Executives get counts
  only, not individual records. Existing rating-audit/void IT exception stays
  tenant-scoped. Sensitive HR record reads require a metadata-only audit event;
  private field values are never copied into the audit log.
- Create/update/activation, rating submission/void and imports now authorize
  server-side. Ratings cannot forge another target/tenant or use NaN/infinite
  scores; legacy/canonical rating links remain compatible. Stored UUIDs remain
  unchanged, while legacy UI storage-ID URLs still work through explicit aliases.
- Phone/email identity writes and import inserts use the existing persistent
  integrity-write lock. Legacy/international-format comparisons detect duplicate
  phone variants, numeric Excel values and Unicode decimal digits. New intentional
  phone writes normalize; unchanged saves preserve old values. No backfill/index
  was run. Legacy email-linked accounts cannot be orphaned by a contact-email
  change without an explicitly confirmed account link.
- Solver onboarding GET checks subject/tenant before reading or lazily initializing
  induction. Read-only self requests do not create missing tasks. Qualified HR/
  manager initialization is serialized and canonical. Own assigned self induction
  steps can be completed; manager/other-subject steps cannot. Generic task,
  notification and form paths use the same Solver ownership checks.
- Employee onboarding reuses its already-authorized employee rather than an
  unscoped second lookup; task retrieval/creation/update/summary respects tenant
  and legacy identities. Existing FTE tests continue passing.
- Solvers UI management controls use server-returned can_manage; denials clear
  stale lists/controls and show a safe error. Role names in the browser do not
  confer write permission.

### Additional modified files (relative to 7afbe1f)

```text
backend/routes/data_import.py
backend/routes/employees.py
backend/routes/onboarding.py
backend/routes/solvers.py
backend/scripts/verify_workforce_reporting.py
backend/tests/test_reporting_verification.py
backend/tests/test_solver_security.py
backend/tests/test_employee_profile_display.py
backend/tests/test_password_change_enforcement.py
backend/utils/employee_integrity.py
backend/utils/form_access.py
backend/utils/reporting_verification.py
backend/utils/solver_access.py
backend/utils/security.py
backend/utils/task_access.py
docs/task03-directory-organogram-report.md
frontend/src/pages/Solvers.js
frontend/src/pages/Solvers.test.js
```

The private HR confirmation/reference-plan/report files remain ignored and local.
No real employee/Solver records or production accounts were changed. No new
service dependency was added; optional PDF parsing uses the existing local
review environment. Task 04/new Solver OTP or wider HR workflow features were
not started.

Employee detail, profile, list and update responses also now distinguish HR/self
private views from manager team metadata. Team views exclude pay, banking,
statutory identifiers, medical information and unapproved personal contacts.
Managers cannot change a report's job title to grant Solver-management authority,
pay or statutory identifiers. Cross-tenant employee updates and ambiguous storage
aliases fail closed. Existing privileged functionality is preserved.

A regression run exposed an existing same-second legacy logout cutoff edge.
Tokens issued exactly at the invalidation cutoff are now rejected; a fixed-clock
test covers both access and refresh tokens. First-login enforcement and normal
login regression tests remain included. No passwords or accounts were reset.

### Remaining staging/data gates

1. Supply an approved local/staging workforce snapshot and hosting ownership.
   Repository configuration has no actual database address or local .env/snapshot;
   GitHub deployment/workflow metadata is empty. The checker therefore cannot
   truthfully claim current stored links are verified or corrected.
2. HR resolves the Solver summary/list discrepancy, missing phone and individual
   reporting exceptions, Board/Executive representation and Sales Team membership.
   The confirmed reference manager roles are no longer pending; actual record IDs
   still are. Ordinary directory/photo/contact visibility policy remains interim.
3. Validate actual legacy Solver account anchors. Accounts relying only on phone
   or missing/conflicting email/solver_id now fail closed until approved linkage
   is confirmed. The separate Solver OTP/provisioning workflow is not introduced.
4. Shared integrity-lock recovery now must account for Solver identity/import/
   rating/initialization writes as well as employee/account writes. Existing
   fail-closed operator procedure still applies: no TTL or automatic stale-lock
   removal. Unique database phone/email/identity constraints remain future
   prerequisites for direct/external writers; application checks do not claim
   those indexes exist. No migration is needed for this code, but any actual
   reconciliation/backfill/index installation requires separate approval.
5. Audit metadata persistence is required for HR-sensitive reads and new Solver
   mutations. If audit storage fails after a record write was acknowledged, the
   endpoint returns 503 and directs operator inspection before retrying; it does
   not roll back or delete records. No transactional outbox was introduced.
6. Complete staging UAT for HR, qualified/unqualified managers, own/other Solvers,
   aggregate executives, IT rating audit and denied ordinary staff; verify private
   redaction, account compatibility, phone conflicts, forms/tasks/onboarding and
   new directory/reporting behavior. Obtain HR sign-off before Task 03 closure.

All final local tests/builds pass. The identified Solver authorization findings
are fixed in local code. Actual stored-record alignment and staging acceptance
remain pending; this is not a claim that production has been updated or that
all HR modules are release-ready. No new commit/push/deployment was performed.
