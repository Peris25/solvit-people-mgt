# Task 14 - Audit Logs & Reporting

## Implemented outcome

Extended the existing application with an authorized Reports & Audit screen, read-time federation of the six existing audit stores, role-scoped operational/management reports and authenticated CSV/Excel exports. Existing source events are not copied, merged, backfilled or rewritten. Ordinary employees and Solvers have no administrative reporting access. Tasks 01-11 and 13 and the deferred Task 12 audit are preserved, including all earlier uncommitted changes.

No production/staging connection, live data change, migration, production index installation, commit, push or deployment occurred. HEAD remains `cee6c92ca92ed5ab35bd63bd6445c4ec8e6c784e`.

## Reference requirements reviewed

The local Developer Brief, FRD and Employee Handbook v2 PDFs in `docs/reference/` were reviewed. Page references below are PDF page numbers. Embedded document instructions were treated as reference requirements, not permission to seed data or deploy.

| Source | Requirement | Implementation / status |
| --- | --- | --- |
| Developer Brief v1, goals p1; access matrix pp6-8 | HR reporting, team reports, Finance reports, IT audit and executive summaries; private salary/bank/medical/disciplinary fields excluded from peers/managers | Explicit server-side role and module guards; manager/direct-report scope; Finance participation/financial scope; executive aggregates; IT metadata audit only. No general personnel export for IT. |
| Brief section 5.14, p17 | Headcount/movements, leave/balances, probation, contracts, training and other HR reports; date/department filters; Excel/PDF | Implemented employee snapshots/hire cohorts, recorded probation/contract dates, leave requests and saved balance snapshots, onboarding, performance progress, training and benefits participation; CSV/Excel. Historical attrition and additional module analytics/PDF remain gaps below. |
| Brief section 5.14, p17 | Thursday management meeting reporting | Management summary counts authorized module records by department/status, with each source's date basis. No new scheduler, fabricated historical headcount or PDF delivery. |
| Brief access/privacy p8; document security p12 | Sensitive views/downloads audited; role-appropriate privacy | New report views, exports and audit reads record access evidence; delivery fails closed if that evidence cannot be written. Raw audit payloads and secrets are omitted from the new view and hardened legacy readers. |
| Brief benefits section 5.15, p17 | HR/Finance participation tracking; private households; Finance-only premiums | Benefits report is participation status only; no dependants, beneficiaries, HR notes or premiums. Finance's existing protected premium workflow remains separate. |
| FRD full audit trail, p5 / p74 | Timestamp and user ID for actions, approvals, submissions and signatures | Existing source records remain intact; canonical projection covers historical actor/date aliases and exposes source-qualified record identity. Unknown actors/dates are labelled, not invented. No claim of retroactive audit completeness. |
| FRD roles/matrix, pp16-17 | API-level role enforcement; managers own team; Finance no individual performance/disciplinary records; executives summary views | Applied to JSON and downloads alike, including module revocations. Finance cannot use performance/employee report endpoints; executive detail never leaves aggregation. Leave summaries follow the actual configured direct-report scope where applicable. |
| Handbook v2, confidentiality section 9.2, p16 and confidential reporting p17 | Confidential handling of business/personnel information | Report whitelists exclude confidential notes, private contacts, medical/disciplinary material, banking/statutory identifiers, attachments and storage paths. No new statutory/payroll calculation or attendance module introduced. |

## Audit findings and fixes

1. Audit history is split across `audit_log`, `audit_logs`, `settings_audit`, `document_audit`, `email_delivery_audit` and `ai_actions_audit`. The new view reads these collections directly. Rows use source plus MongoDB storage identity, so duplicate legacy public IDs do not overwrite events. Separate stored events are not silently deduplicated. New access-audit events represent new reads/downloads, not copies of the underlying events.
2. Historical timestamps and actors use different keys/types. Projection handles ISO strings/BSON datetimes and `actor_id`, `performed_by`, `by_user_id`, `changed_by` and `user_id`. Actor choices come only from authorized visible events; labels use uniquely resolved tenant accounts and safe fallback names, not raw actor emails. Filtering uses opaque actor tokens, not user-supplied employee identity.
3. Legacy settings/AI audit readers returned raw before/after values or AI parameters/results. These could contain credentials, bank data or other sensitive payloads. The new view and compatible legacy readers expose safe metadata, with values redacted. HR cannot read Security/unknown-module events through the consolidated feed; IT can inspect metadata across all sources. HR module revocation/narrow scopes remain effective.
4. The old employee CSV included salary and national/statutory identifiers and was available to executive/IT roles. It now shares the safe employee report projection: HR authorized records, eligible managers' actual direct reports, executive aggregate rows; IT is denied. Salary, bank and statutory identifiers are absent even from the default HR employee export. Dedicated approved workflows remain available for authorized HR/Finance.
5. Existing financial CSVs ignored tenant/module overrides and included free-text notes. They now use current-tenant queries, appropriate M10/M12 permissions, narrow fields and export access evidence. IT/executive roles cannot use these detail exports. Financial amounts remain only in the existing authorized financial exports, never general employee reports.
6. Email-delivery views/CSV exposed recipients, subjects and raw SMTP errors. These are now redacted into delivery metadata; template/status/time remain usable and resend still targets the original stored recipient. CSV is explicitly limited to 1-500 metadata rows rather than claiming an unrestricted historical dump. No email was sent by this task.
7. Existing applicant CSVs are tenant-scoped, formula-safe and access-audited. Detail export now requires appropriate Solver access and recruitment permission, excluding IT/executive aggregate roles. Existing recruitment CRUD is not rebuilt. Oversized applicant exports fail clearly rather than silently truncating.
8. CSV/Excel generation protects formula-leading strings and control characters. Existing import-error workbooks receive the same cell protection. New report downloads use authenticated API/blob requests; legacy employee/pay-band/budget buttons now also preserve authentication instead of relying on a bare navigation URL. Downloads use no-store/nosniff headers and never expose filesystem paths or public storage URLs.

## Reports and access

| Report/view | Authorized scope | Important limits |
| --- | --- | --- |
| Administrative audit | IT metadata; HR permitted operational metadata with full M01 scope and relevant module access | No raw payload/details endpoint or export; no audit update/delete route. Unclassified/security events are IT metadata only. |
| Employees / hire cohorts | HR authorized records; manager direct reports; executive aggregate | Basic work/employment fields only. Current state, not reconstructed historical headcount. Restricted board records excluded. |
| Recorded probation/contract end dates | HR; authorized manager direct reports | Uses actual saved date; missing dates are counted and omitted from these date-specific reports. No renewal/confirmation is invented. |
| Leave requests | HR; manager direct reports; Finance approved direct-report rows; executive aggregate within configured scope | Actual saved intervals/units only. No reasons, evidence, medical file or private medical type for non-HR. Date filtering includes overlapping leave that started earlier. |
| Recorded leave balances | HR with M18 access | Saved snapshots only, no derived accrual, balance rewrite or invented balance when absent. |
| Onboarding progress | HR; managers' direct reports | Checklist keys/status/responsibility/dates only; no clearance, document or financial payload. |
| Performance review progress | HR; direct-report managers; executive aggregate | Explicit score/rating fields only for authorized detailed views; Task 10 unreleased own-score restrictions preserved. No assessment narratives or recalculation/weighting. |
| Training participation | HR; managers' direct reports | Saved request/course status, schedules and completion; no cost, justification or private certificates. |
| Benefits participation | HR and Finance with required grants | Status/cover level only; no household details, premiums, medical data or HR decision reasons. |
| Management meeting summary | Counts from only the caller's authorized report modules/scopes | Department/status counts and date basis; never joins private employee details into an executive output. |

- Date, department and status filtering is applied server-side; audit adds event, module and authorized actor filters. Date comparisons use EAT boundaries and preserve mixed historical date formats safely.
- Missing historical values are null/Not recorded. Ambiguous employee aliases are excluded with HR reconciliation counts; orphaned references are not attached to a guessed employee. No stored reporting relationships change.
- Duplicate canonical IDs and malformed nested identifier payloads cannot overwrite rows or leak through ID fields. Native ObjectId/string/UUID references resolve through the tenant-specific employee index and existing authorization helpers.
- List responses paginate at up to 500 rows, with offsets bounded at 10,000. New report exports include the authorized filtered set up to 10,000 rows; larger sets fail with an instruction to narrow filters. Actor/source projections are bounded in memory while scanning audit history.
- Reports never assume a missing record means zero leave, completed onboarding, approved coverage or a historical employment change. Counts represent recorded rows; different modules can have multiple records per employee.

## Files modified for Task 14

- `backend/utils/administrative_reporting.py` (new): report/audit scope, safe projections, identity/date compatibility, filtering/pagination, management summaries, access evidence and export helpers.
- `backend/routes/reporting.py` (new), `backend/server.py`: read-only reporting routes and registration.
- `backend/routes/exports.py`: secure existing employee/pay-band/budget CSV routes.
- `backend/routes/settings.py`, `backend/routes/masters_settings.py`, `backend/routes/ai_agent.py`, `backend/routes/email_delivery.py`: redact and tenant-scope legacy audit/delivery readers and protect email metadata CSV.
- `backend/routes/solver_intake.py`: secure existing applicant CSV exports without changing recruitment workflows.
- `backend/routes/data_import.py`: protect existing error-workbook cells and audit download.
- `backend/tests/test_administrative_reporting.py` (new): role/module/scope, data isolation, source federation, filtering, export privacy, formula safety, legacy identifier and real MongoDB regressions.
- `backend/tests/test_password_change_enforcement.py`: five new route/format cases under the mandatory password-change gate.
- `frontend/src/pages/Reporting.js`, `frontend/src/pages/Reporting.test.js` (new): responsive authorized report/audit screen, filters, safe columns, exports, pagination and account-switch isolation.
- `frontend/src/App.js`, `frontend/src/components/Sidebar.js`, `frontend/src/services/api.js`: route/navigation, authenticated report calls and legacy CSV downloads.
- `docs/task14-audit-reporting-report.md`: this report.
- `docs/task13-benefits-payroll-report.md`: finalize the interrupted Task 13 validation/cleanup record; no Task 13 functionality changed.

No dependency manifest changed. Other working-tree changes belong to earlier tasks and remain preserved.

## Validation

| Check | Result |
| --- | --- |
| Full backend `pytest backend/tests tests` | **1,118 passed**, 6 warnings, 141.02 seconds; no failures or skips |
| Focused Task 14 backend tests | **77 passed**, including real disposable MongoDB |
| Full frontend suite | **157 passed**, 24 suites, 10.23 seconds |
| Strict CI build (`CI=true`) | Passed; compiled successfully |
| Normal production build (`CI=false`) | Passed; compiled successfully |
| Python `compileall -q backend` | Passed |
| `git diff --check` and new-file whitespace validation | Passed; Git LF/CRLF notices are informational |

Tests cover role and module revocation; direct-report/tenant isolation; executive aggregation; date/department/status/event/module/actor filters; pagination; unknown actors/dates; duplicate/native/malformed IDs; board/exited records; balance preservation; unreleased performance privacy; household/salary/bank/secret redaction; safe legacy audit readers; CSV/Excel formula protection; authenticated downloads; audit-write failure; read-only route methods; first-login enforcement; management/date reports; and Tasks 01-13 regressions.

The prior Task 13 localhost processes were no longer running when the first real-Mongo check was attempted; fresh local services were started. The synthetic fixture was also adjusted to avoid nesting `asyncio.run` inside a running loop. The final focused and complete runs above pass. All integration tests used disposable localhost MongoDB/API services with outbound application traffic blocked, repository synthetic fixture labels and generated credentials. No live employee data or provider account was accessed. The existing synthetic document scanner harness is unchanged.

## Outstanding requirements and staging prerequisites

- Validate the new role projections and redacted legacy readers with HR, Finance and IT in isolated staging. The source documents do not approve broad unredacted audit payload export; it is intentionally unavailable. Any future raw-detail access needs a separate approved permission and field policy. No policy approval or production readiness is claimed here.
- Historical point-in-time headcount, movement reconstruction and attrition rates require a verified opening population and effective-date history. Current employee states and audit events do not prove a complete historical denominator. No rate or reconstruction is fabricated.
- One-click PDF/Thursday pack generation/scheduling and PDF/Excel analytics for policy acknowledgements, updates reach, requests SLA, recognition and other administration registers are not implemented in this bounded six-module reporting extension. The implemented meeting summary and CSV/Excel exports are available now; additional reports need their relevant workflow data and approved definitions. Existing modules remain untouched.
- Finance-wide payroll export of unpaid/half-pay days remains subject to the approved payroll workflow. New leave reports use actual existing direct-report permissions; they do not widen Finance/Executive access merely because a user requests a summary. Task 13 Wingubox, payslip release, insurer-format and benefit-removal prerequisites remain.
- Review missing/ambiguous historical identities, timestamps and balance formats through the controlled HR reconciliation process. Source records are preserved. Board-only data is excluded from operational reports rather than inferred into management totals.
- Audit-source date normalization is performed at read time to accommodate mixed BSON/string history; high-volume audit/report performance must be profiled in staging. New audit pagination is bounded in memory, but source scans and employee authorization lookups still require suitable existing indexes and capacity. No index or normalization migration was installed.
- Access evidence is an append to the existing audit store, not a cryptographically immutable ledger. Database permissions, protected backups, retention, monitoring and tamper protection remain operational prerequisites. Ordinary application users have no reporting audit mutation endpoint. This change does not prove every pre-existing application action was historically logged.
- No new automatic audit deletion/retention or housekeeping job was introduced. Apply any legal retention/storage changes only after approved policy and an explicit operational plan.
- Stage real permissions, overridden modules, manager reassignment, authorized downloads, formula fixtures and fail-closed audit outages. Use a consistent API version across workers so older exports cannot bypass new privacy guards.
- No database migration is required for these read-time projections and existing-format access events. Task 02 integrity/index and controlled interrupted-write recovery prerequisites remain; no production operation was attempted.

Cleanup verified: all four disposable suite databases were removed; per-test databases also clean themselves up. The verified synthetic API and MongoDB processes were stopped. `.mongo-test`, `.test-deps` and `.node-test` were removed, and localhost ports 18089/27089 are no longer listening. This also completes cleanup of the interrupted Task 13 test resources. No application source or historical record was removed.
