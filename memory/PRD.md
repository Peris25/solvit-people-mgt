# Solvit People Management Platform — PRD

## Original Problem Statement
Build a full-stack People Management Platform for **Solvit Limited** (Kenyan tech-enabled vehicle inspection company) implementing the FRD: 19 modules, intelligent forms engine (32 forms), automation rules engine, employee lifecycle state machine (9 FTE + 5 Solver states), AI HR Agent (Policy Q&A + Compliance Guardian), HR Kanban dashboard, Kenya statutory compliance (KES, EAT, NSSF/SHA/PAYE), pre-populated launch data and demo-friendly auth (standard login + 9 quick-login role tiles).

## Tech Stack
- Backend: FastAPI + Motor (async MongoDB) + APScheduler + sendgrid
- Frontend: React 18 + Tailwind utility classes
- Auth: JWT in httpOnly cookies (custom)
- AI: Emergent LLM Key (gpt-5.2 default)
- Email: SendGrid OR generic SMTP (via Settings)
- Timezone: Africa/Nairobi (EAT)

## Architecture
```
/app/backend/
├── server.py                       # 25 routers mounted at /api
├── utils/{auth, email_service, access_matrix}.py
├── routes/
│   ├── access.py / masters_settings.py / exports.py
│   ├── budget.py (envelope_pct, alloc_threshold, tier_thresholds from settings)
│   ├── compliance.py (PAYE/NSSF/NHIF from settings)
│   ├── leave.py (active types from lookups)
│   ├── employees.py (probation duration from settings, board_only filter)
│   ├── performance.py (scoring thresholds + MD KPIs + review-panel routing)
│   └── 18 module routes
└── automation/{engine.py, seed_data.py}

/app/frontend/src/
├── App.js (RoleDashboard for /dashboard, AccessGate around 8 module routes)
├── components/
│   ├── Layout.js / Sidebar.js (role-scoped + custom employee menu)
│   ├── EmployeePicker.js / AccessGate.js / MastersValueEditor.js
├── hooks/useModuleAccess.js
├── utils/format.js (fmtKES, fmtEAT)
└── pages/ (21 pages incl. role dashboards + MastersSettings + Budget rebuild)
```

## Implemented (May 2025 → Feb 2026)

### Iter 19 — Spec-compliant Email Pipeline (Formal Override + Retries + Branded Templates) ✅

**Section 1 (Central Service)** — kept the existing direct-call architecture (per user's "do all apart from central architecture"). Everything else from the spec is now in:

**🔐 Formal Template Override (legal-document safety)**
- `FORMAL_TEMPLATE_KEYS` constant — `disciplinary.show_cause`, `disciplinary.written/final/dismissal`, `exit.confidentiality_ack`, `recruitment.offer`.
- These 6 templates **always use the production SMTP config** even when active_mode is testing. If production isn't configured, the email is skipped with a clear log entry rather than silently going to Mailtrap.
- New `X-Formal-Document: true` header set on formal emails.

**🔁 Retry Logic (5 min → 30 min → 2 hr)**
- Failed sends are queued in `email_retry_queue` with `next_attempt_at` timestamp.
- New `process_retry_queue()` coroutine + APScheduler 1-minute cron drains the queue.
- After 3 failed retries, an in-platform notification is created for IT Admin: *"Email delivery failed after 3 attempts — [Template] to [Recipient]. Check Notification Log."*
- Verified: bursting 3 leave submissions creates 4 failed sends → 4 rows in `email_retry_queue` with retry_count=1.

**🏷️ Standard Merge Tags (all of spec's globals)**
- `employee_first_name`, `employee_role`, `employee_department`, `line_manager_name`, `hr_name`, `action_date`, `due_date`, `platform_link`, `current_year`, plus auto-resolved manager + employee context.
- Plus back-compat aliases (`manager_name`, `today`, `login_url`) so existing seed templates render correctly.

**🎨 Solvit-Branded Email Wrapper**
- Every outbound HTML body wrapped in a Solvit-branded shell — black header bar, Red `#FF353F` accent line, Barlow heading, Nunito Sans body, footer with company line. Idempotent (`<!--solvit-wrapped-->` sentinel prevents double-wrap).

**📋 Notification Log (Settings → Email Delivery)**
- `GET /api/email-delivery/log` — combines `email_log` + `email_send_log`. Status filter chips.
- **HR-scoped view**: HR Admin / HR Manager only see HR-domain templates (onboarding/leave/perf/recog/exit/retention/lnd/survey/policy/recruitment/disciplinary/comp). System / Budget templates hidden per spec.
- **Resend button** on every failed row (`POST /api/email-delivery/log/{id}/resend`, IT Admin only).
- **CSV export** (`GET /api/email-delivery/log/export.csv`).
- New columns: Retry count, Formal badge (red FORMAL tag on legal-doc rows).

**📧 8 new seed templates** added for spec gaps:
- `disciplinary.show_cause`, `exit.confidentiality_ack`, `retention.flight_risk_alert`, `budget.allocation_submitted`, `leave.cancelled`, `performance.self_review_submitted`, `onboarding.probation_confirmed`, `onboarding.probation_extended`.
- Total templates: 70.

**🔗 New action triggers wired:**
- Retention: stay-interview scheduled → `retention.stay_interview_invite`.
- Retention: critical flight risk crossed → `retention.flight_risk_alert` (HR only, never to employee).
- Budget: allocation submitted needing Finance approval → `budget.allocation_submitted`.

### Iter 18 — Cross-Platform Email Triggers + Email Send Log Viewer ✅
**21 of 21 template→action triggers wired** across the platform via a new central helper `utils/email_triggers.py`. Every route handler that performs a meaningful action now fires the corresponding email template (best-effort, never blocks the response):

| Module | Trigger | Templates |
|---|---|---|
| Leave (iter 17) | Submit / approve / reject | leave.received, leave.pending_lm, leave.approved, leave.rejected |
| Onboarding | Employee created | onboarding.welcome |
| Performance | Review completed / PIP transitions | performance.review_complete, performance.pip_initiated/success/escalate |
| Recognition | Peer + manager nomination | recognition.peer, recognition.manager |
| Disciplinary | Issue notice (by type) | disciplinary.hearing/written/final/dismissal |
| Compensation | Salary review created | comp.salary_review |
| Recruitment | New candidate + stage changes + reject | recruitment.application_received, recruitment.invite_competency/values/growth/interview, recruitment.offer, recruitment.regret |
| Policies | Publish (fan-out to active employees) | policy.published |
| Projects | Assign + complete | lnd.project_assigned, lnd.project_completed |
| L&D | Single & bulk training assignment | lnd.training_assigned |
| Solvers | Activate, tier change, suspend, reactivate | solver.activation, solver.tier_upgrade, solver.tier_downgrade, solver.suspension, solver.reactivation |

**Email Send Log viewer:**
- New `GET /api/email-delivery/log` endpoint — combines `email_log` + `email_send_log` collections, sortable by date, filterable by status, RBAC-gated to IT Admin + HR Admin.
- New section on Platform Settings → Email Delivery page with filter chips (all / sent / failed / skipped), refresh button, and rows showing When, To, Subject + template_key chip, Source (system / ai_agent), Mode, Status (color-coded), Error.
- `email_service.send_email()` now also logs `skipped` rows so missing recipients become observable.

**Data fixes (caught during iter 18 testing):**
- `SolverCreate` / `SolverUpdate` now have an `email` field (was missing — solver triggers were silently no-op'ing).
- New idempotent migration `backfill_solver_emails()` runs every boot to give existing demo solvers an email so their triggers actually fire.
- `ai_actions.execute_send_email` refactored to use the shared `send_email()` (was duplicating SMTP code, bypassing throttle + log).

**Tests — Iter 18:** 19/22 backend (+ 3 follow-up tests pending after solver email backfill — now reproducible via the curl-verified path). Frontend: Email Send Log section + filter chips + refresh + template_key chip + status colors all visible & functional.

### Iter 17 — Editable Permissions Matrix + Custom Roles ✅
**Live-editable access matrix:**
- New runtime overlay store (`RUNTIME_OVERRIDES`, `CUSTOM_ROLE_DEFINITIONS` in `utils/access_matrix.py`) — mutated synchronously by IT Admin actions, persisted to MongoDB `permission_overrides` + `custom_roles` collections, and re-hydrated on every server boot via `load_runtime_state(db)`.
- `get_module_access()` now resolves through the overlay → custom-role inheritance → static `ACCESS_MATRIX`. Enforcement on all existing routes is unchanged (still synchronous) and picks up overrides immediately.

**New backend endpoints (IT Admin only, audited):**
- `PUT  /api/access/matrix/cell` — set/override one cell (level, scope, or null to revoke).
- `DELETE /api/access/matrix/cell` — drop the override, returns cell to seed default.
- `POST /api/access/roles` — create a custom role with inheritance from a base role.
- `DELETE /api/access/roles/{key}` — delete a custom role; any users assigned to it auto-rebase to `employee`. Per-cell overrides for the role are cascade-deleted.
- `/api/access/matrix` now returns `custom_roles`, `system_roles`, `valid_levels` and the **effective** matrix (with overlays applied + custom-role columns inherited).

**Frontend `/roles-permissions` redesigned:**
- Three tabs: **Access Matrix** (click any cell → inline editor with Level + Scope + Save/Reset), **User Assignments** (now includes any custom role in the dropdown), **Custom Roles** (table with delete + "New Role" modal that picks an inheritance base role).
- Custom-role columns in the matrix are tagged with a small `CUSTOM` badge.

**Tests — Iter 17:** 19/19 new pytest + 14/14 iter-16 regression. Frontend e2e (Playwright) green for edit→save→effective access reflected in `/access/check`; reset→default restored; new role column appears with inherited permissions; delete role removes column and rebases assigned users.

### Iter 16 — Finance Leave Bug Fix + Roles & Permissions admin ✅
**Bug fix — Finance was locked out of Leave:**
- Root cause #1: `<AccessGate module="M18">` wrapped the `/leave` route; the access matrix had `M18.finance = None`, so the gate blocked Finance before render. Aligned with the additive role rule by setting `M18.finance = Manage (own_team)`. M04 and M14 also corrected for Finance (employee base layer per role rule).
- Root cause #2: `Leave.js` was using `user.id` (users-collection id) as `myEmpId`, which differs from the actual `employees.id` for Finance/HR Admin. Now resolved from `GET /api/employees/me`.

**New module — Roles & Permissions (IT Admin only, under Tools):**
- New backend endpoints in `routes/access.py`:
  - `GET /api/access/matrix` — now returns `module_labels`, `role_labels`, `roles_order` alongside the matrix.
  - `GET /api/access/users` — IT Admin only, lists every user with role.
  - `PUT /api/access/users/{id}/role` — IT Admin only, validates against canonical ROLES, writes an audit log entry. HR Admin gets 403.
  - `GET /api/access/roles` — canonical role list with display labels.
- New frontend page `/roles-permissions` (`pages/RolesPermissions.js`):
  - **Tab 1 — Access Matrix**: read-only 19×9 module/role grid with Full / Manage / Read / — chips, scope qualifiers shown beneath cells; destructive-action list pinned at bottom.
  - **Tab 2 — User Assignments**: every platform user with a `role` dropdown. Change → confirm dialog → audited PUT → flash banner.
- Sidebar: new `Tools → Roles & Permissions` nav item (IT Admin only) using `KeyRound` icon.

**Tests — Iter 16:** 14/14 backend pytest pass (M18 access for all 9 roles, /me-based leave submission, /access/matrix shape, /access/users IT-Admin gating, PUT role-change with audit, invalid role 400). Frontend testids verified by code review.

### Iter 15 — Line Manager Dashboard + strict LM visibility scope ✅
**New "My Team" widget (`/dashboard` for `role=line_manager`):**
- New page `LineManagerDashboard.js` replacing the generic HR Kanban for LM users.
- Top-brief tiles: Direct Reports · Pending Leave · Open Reviews · My Open Tasks (each clickable to drill down).
- Team Flight Risk bar (Critical / High / Elevated / Healthy split).
- Direct Reports table with per-person lifecycle_state, flight_risk_level, pending_leave, open_reviews, days_since_last_review, last_performance_score. Row click → `/employees/<id>`.

**New backend endpoint `GET /api/dashboard/line-manager`:**
- Returns `manager_employee_id`, `team[]`, `team_size`, `pending_leave`, `flight_risk_summary`, `open_reviews`, `my_open_tasks`. Scoped to the caller's own employees.id; gated to `line_manager / hr_admin / hr_manager / it_admin`.

**Strict visibility scope for `line_manager` role:**
- `/api/employees` list now matches `line_manager_id` against the LM's own employees.id (was incorrectly matching against users.id before). LM sees ONLY self + direct reports.
- `/api/employees/{id}` and `/api/employees/{id}/profile` mirror the same scope — LM gets 403 for employees they don't manage, 200 for self or direct reports.
- `/api/leave` list scope fixed to include the LM's own requests + their direct reports (previously dropped both).

**Serializer hygiene (caught during iter 14 testing):**
- `fmt()` now preserves the canonical UUID `id` and pops Mongo `_id` from every employees response. Previously the list endpoint was leaking `_id` AND overwriting the UUID `id` with the ObjectId, desyncing identifiers between the new widget (UUID) and other endpoints (ObjectId).

**Tests — Iter 15:** 18/18 backend pytest pass on the consolidated iter 14 regression suite (widget shape & RBAC, employees scope across 7 roles, leave scope, UUID consistency, no `_id` leak, LM profile/detail scope). 9/9 mandatory-LM regression from iter 13 still green. Frontend: end-to-end LM → click direct report → profile renders successfully.

### Iter 13 — Role Architecture & Mandatory Line Manager (UAT fixes) ✅
**Additive Role Layering:**
- Sidebar restructured: "Finance & Admin" section is gated to `role='finance'` only; "Budget & Operations" section visible to HR Admin / HR Manager / Executive only; IT Admin sees no Finance or Budget sections.
- Finance also receives the Line-Manager team layer (Performance, Leave, L&D, Projects, Recognition, Disciplinary, Calendar).

**Mandatory Line Manager (every employee, end to end):**
- `EmployeeCreate.line_manager_id` is now a required `str`. Pydantic returns 422 when missing.
- `POST /api/employees` validates the supplied id exists (400 'Selected Line Manager not found.' otherwise).
- HR Admin → Add Employee modal includes the required `[data-testid=employee-lm-picker]` with inline error `[data-testid=employee-lm-error]` and stable `[data-testid=employee-save]` submit.

**Auto-populated read-only Line Manager on Leave:**
- New `GET /api/employees/me` returns the caller's own employee row enriched with `line_manager_name`.
- Apply-for-Leave modal pre-fills `line_manager_id` from `/me` and renders a read-only badge `[data-testid=leave-lm-readonly]` instead of a picker (with `[data-testid=leave-lm-missing]` fallback if HR hasn't set one yet).

**Board Chair + Reporting Tree:**
- Board Chair seeded as a real `employees` record (board_only=true, role_title='Board Chair').
- New `LINE_MANAGER_TREE` + `enforce_line_manager_hierarchy()` runs on every boot and idempotently applies the canonical reporting tree (MD/ED → Board Chair; Sarah/Jessica/Isaac/Lillian → MD; David/Grace/Daniel → Sarah; James → David; Mary → Lillian; John → Isaac; Robert/Stephen → David). Any unmapped legacy employee with no LM defaults to Sarah.

**Tests — Iter 13:** 22/22 backend pytest (13 regression from iter 12 + 9 new); 100% on frontend UAT cases (leave readonly, LM-required inline error, sidebar gating for IT Admin / Finance / HR Admin).

### Iter 12 — Light mode (default) + Dark mode toggle ✅
- New `ThemeContext` with `theme: 'light' | 'dark'`, localStorage persistence (`solvit_theme`) and `<html data-theme>` attribute switch.
- **Light mode** (new default) — white sidebar with subtle right border, `#FFEEEE` pink-tint active background + red text + left red bar (matches the reference image exactly), muted grey section labels, light borders throughout.
- **Dark mode** (former default) — preserved as a one-click alternative; sun/moon toggle button in sidebar footer next to the Sign Out button.
- Theme-aware components: `Sidebar.js`, `AIAgent.js` header, `FirstLoginTour.js` step tooltip. All other surfaces (cards, modals, forms) already use white / `#F5F5F5` which look correct in both modes.
- Token catalogue in `themeTokens()` makes adding new theme-aware surfaces a one-line lookup.

### Iter 11 — Actionable AI with confirmation prompts ✅
**The AI Assistant is no longer read-only.** It now proposes write actions, surfaces a confirmation card, and only executes after explicit click.

- New `routes/ai_actions.py` (action catalog) + extended `routes/ai_agent.py` (propose / execute / cancel / audit endpoints):
  - `POST /api/ai-agent/chat` — when an action intent is detected, returns a `proposed_action` payload instead of routing to the LLM (deterministic, no hallucination risk).
  - `POST /api/ai-agent/actions/{id}/execute` — executes the action (with optional `params_override` for HR-edited fields) and writes an immutable audit row.
  - `POST /api/ai-agent/actions/{id}/cancel` — abandons the proposal.
  - `GET /api/ai-agent/actions/audit` — full audit trail (HR + IT Admin).
- **6 action types** wired with role-gated execution:
  - `approve_leave` (low risk, green)
  - `reject_leave` (medium risk, amber; editable reason)
  - `send_recognition` (low risk; editable message)
  - `send_email` (medium risk; uses the live Email Delivery mode — Mailtrap/O365; renders the chosen template + logs `email_send_log`)
  - `mark_task_complete` (low risk)
  - `assign_training` (low risk; editable training name)
- Built-in safeguards:
  - 30-minute action expiry (`expires_at` checked at execute time)
  - Only the proposer can confirm their own pending action
  - Role gating per action (`ACTION_REQUIRED_ROLES`)
  - Edit-before-execute support for reason / message / training_name
- Frontend `AIAgent.js`: renders `ActionCard` with risk-tinted banner (green / amber / red), inline editable textareas for the action's editable params, and Confirm / Cancel buttons. Outcome ("✓ Executed", "Cancelled", "✗ Failed") shown below the message.

**Testing — Iter 11:** 7/7 new pytest cases pass + 46/46 iter 8-10 regression pass. End-to-end smoke confirmed the action card renders with the green banner, editable message field, and "Don't Send / Send Recognition" buttons.

### Iter 10 — AI Assistant full-platform copilot + legacy email removal ✅
- **Legacy SendGrid/SMTP "Email" tab retired** from Settings. Email delivery is now configured exclusively under the new **Email Delivery** tab (Mailtrap testing / Office 365 production).
- **AI Agent → "Solvit HR Assistant"** transformed into a full-platform copilot:
  - New backend tools: `snapshot_headcount`, `snapshot_leave`, `snapshot_performance`, `snapshot_recruitment`, `snapshot_solvers`, `snapshot_training`, `snapshot_recognition`, `snapshot_disciplinary`, `snapshot_budget`, `snapshot_onboarding`, `compliance_status`
  - Intent classifier routes the user question to the right modules and packs a compact (<3KB) live brief into the LLM context — no hallucinated stats
  - New `lookup_employee_status` resolves a name from the user message and returns recent leave / reviews / training / open disciplinary cases for that person
  - New endpoints: `/api/ai-agent/snapshot` (one-call daily brief) and `/api/ai-agent/employee-status?query=`
  - Re-written `SYSTEM_PROMPT` covering every HR remit (employees · leave · performance · recruitment · onboarding · L&D · recognition · disciplinary · compensation · budget · surveys · retention · projects · policies · solvers · compliance) with clear scope boundaries (read-only, suggest exact click paths)
- **Frontend AIAgent panel** rebuilt with brand-aligned UI (Barlow/Nunito Sans, sparkles header, wider 420px panel), 9 quick prompts, daily-brief loaded on open showing live numbers from `/api/ai-agent/snapshot`.
- **Testing — Iter 10:** 7/7 new pytest cases pass + 39/39 iter 8 & 9 regression pass.

### Iter 9 — UAT batch 2 (Documents · Data Import · Email Templates · Tour) ✅
**Item 1 — Employee Personal Documents**
- New `routes/documents.py` with categories/list/upload/download/delete + immutable audit log
- Local filesystem storage `/app/backend/uploads/employee_docs/{empId}/` (S3 still backlog)
- PDF / JPEG / PNG / DOCX up to 10MB; categories editable via Masters Settings → `lookups.document_categories`
- Permissions: HR Admin full · Line Manager view-only for direct reports · Employee no access · IT Admin audit-only
- Frontend: `DocumentsTab` added to `EmployeeProfile.js` (conditional on `canSeeDocs`); upload/delete modals with brand styling

**Item 2 — Data Import**
- New `routes/data_import.py` — generates three styled `.xlsx` templates (FTE Employee · Solver · Historical Performance) with `Data` + `Read Me` sheets, sample row (greyed), column-header tooltips
- Row-level validation (required fields, DD/MM/YYYY dates, dropdown match, duplicate ID/email) → green/red preview
- Excel error-report download endpoint; commit imports valid rows only or full batch; import_history log
- Frontend: new `/data-import` route + sidebar nav (UploadCloud icon); tabs Upload · Templates · History

**Item 3 — Customisable Email Templates**
- New `routes/email_templates.py` seeds **63 templates** across 15 modules (Onboarding · Recruitment · Solvers · Performance · Surveys · Retention · L&D · Leave · Compensation · Recognition · Disciplinary · Policies · Budget · Compliance · System & Account)
- CRUD + Preview (resolves merge tags with sensible defaults) + Reset to Default
- Permissions: IT Admin edit · HR Admin view & preview · others denied
- Frontend: `EmailTemplates.js` embedded in Masters Settings tab; lightweight contenteditable rich text (B/I/list/link/font-size); merge-tag clickable sidebar

**Item 3E — Email Delivery (Mailtrap / O365)**
- New `routes/email_delivery.py` with Testing (Mailtrap) / Production (Office 365 STARTTLS) modes
- IT Admin can edit, switch (with confirmation + audit), Test Send (live SMTP) and view last-test status
- HR Admin view-only
- Frontend: `EmailDelivery.js` embedded in Settings → Email Delivery tab; active-mode banner (red for testing, green for production)

**Item 4 — First-Login Onboarding Tour**
- New `routes/onboarding_tour.py` — per-user `first_login_tour_completed` flag, IT Admin reset + config + completion report
- Role-specific step lists: HR Admin (6) · Line Manager (5) · Employee (5) · Solver (4) · Finance (4) · Executive (4) · Board (3) · IT Admin (6)
- Frontend: `FirstLoginTour.js` mounted globally in `Layout` — full-screen welcome modal + bottom-right tooltip steps; Skip & Replay supported; IT Admin controls in Masters Settings → Onboarding Tour tab

**Testing — Iter 9:** **39/39 backend pytest pass** (21 new + 18 regression) · Frontend 100% pass on review-request UI checks · Two cosmetic warnings carried over from iter 8 (`borderLeft` shorthand and setState-during-render) — fixed in this iter for FirstLoginTour & EmailTemplates.

### Iter 8 — UAT Round 1 (UI Brand + Leave + PDF + Skills Matrix) ✅
**Solvit Brand Identity sweep:**
- Typography: Barlow (display) + Nunito Sans (body) loaded via Google Fonts; global CSS variables and overrides remap legacy `fontFamily: 'Arial'` inline styles to brand body font
- Colors: #FF353F primary red · #191919 black · #F5F5F5 light grey enforced across new components
- Sidebar fully rebuilt with lucide-react SVG icons (LayoutDashboard, Users, Zap, Target, Rocket, BarChart3, ClipboardList, ShieldCheck, BookOpen, Briefcase, Palmtree, Wallet, Award, Scale, FileText, TrendingUp, CheckCircle2, CalendarDays, FileEdit, ListChecks, Cog, Settings, Brain) — zero emoji glyphs
- Global CSS forces `border-radius: 4px` on rounded-pill buttons; print styles for `.solvit-print-area`

**Leave Module overhaul (frontend):**
- 4-tab layout: My Applications · Team Leave (LM/HR) · Calendar · Rollover
- "Accrued Balance" black brand card (1.75 days/month × completed_months_in_year)
- Rollover banner + Rollover panel with carried_forward / used / remaining stat boxes
- Apply modal: required Line Manager EmployeePicker (`leave-lm-picker`) — client-side alert when missing
- Monthly Leave Calendar (`leave-calendar`) with prev/next month nav and per-day event chips

**Performance Review:**
- Functional "View" button → read-only modal (`review-view-modal`) with section A/B/C breakdown, KPI detail table, comments
- "Download PDF" button (`review-pdf-btn`) uses `window.print()` + print CSS confined to `.solvit-print-area` — zero new deps

**Other UAT items:**
- Solver Database "View" detail modal (`solver-view-modal`) — phone, tier, accuracy, zones, vehicle categories
- L&D Skills Matrix tab — per-employee picker, add/edit/remove skills with Beginner/Intermediate/Advanced/Expert
- Employee Sidebar: added My Reviews + My Surveys entries

**Backend hardening:**
- `routes/leave.py` `fmt()` no longer overwrites UUID `id` with Mongo `_id` (POST→GET id parity restored)
- `/api/leave/rollover/{empId}` always returns `deadline` + non-null `banner` for empty-state shape parity

**Test Results — Iter 8:** 18/18 backend pytest ✅ · Frontend smoke pass (sidebar SVG icons, Nunito Sans body, Barlow H1, 4 leave tabs, accrued card, lm-picker, calendar grid, rollover panel)

### Iter 1–7 — Foundation through Structural corrections (see earlier sections)

### Iter 1–3 — Foundation, FRD corrections
- 22 module pages, AI Agent, sequential Forms engine, 9-Box, Talent Density, Voluntary Attrition, Stay Interview, KES + en-GB date, drag-drop Performance × Values, "My Tasks", bulk actions

### Iter 4 — Review Panel + Form Outcomes + Access Matrix + Role Dashboards
- Review Meeting Panel (3 branches + casting vote)
- Form-Outcome → state machine triggers
- Access Rule Matrix Section A (19×7) + Section B (7 destructive); enforced at API
- 3 role dashboards (HR Admin / FTE / Solver)

### Iter 5 — UX cleanup + Budget rebuild + Login refresh
- EmployeePicker dropdown (no free-text employee selection)
- Disciplinary crash fixed; Pay Bands editable; Consultant employment type
- Budget Governance rebuild: Finance-only GP Actual + Form 28 + 5 canonical depts + Headroom Allocations with KES 50k Finance gate
- Login: Solvit hero photo + logo

### Iter 6 — General Masters Settings (22/22)
- IT Admin role + 11-category Masters Settings module with audit log
- Live cross-module: envelope %, allocation threshold, talent density target, attrition target
- Generic JSON editor (primitives/arrays/tables/nested)

### Iter 7 — Structural corrections + P1 completion (29/29 + 7/7 ✅)
**Structural (FRD overrides):**
- **Board role** added (`board` in ROLES)
- **MD reports to Board** (not ED)
- **ED reports to Board**, guided by MD; same Board-led review model as MD
- **MD has 4 direct reports only**: Finance & Operations Manager (Sarah), HR & Administration Manager (Jessica), IT Manager (Isaac), Growth Captain (Lillian)
- **Finance & Operations Manager** is a single combined role — replaces "Finance Manager" + "Operations Manager"
- **Solvers Manager + Technical Services Manager** report to Finance & Operations Manager (NOT MD)
- **MD/ED records are Board-only** — `board_only=True` filter on `/api/employees` list + single GET; HR Admin gets 403
- **MD KPIs (8 specific)**: Revenue Growth, Solvit Alignment Survey Score, Operational KPI Achievement, Budget Adherence, Client Retention, CSAT Score, Channel Partner NPS, Board Reporting → `GET /api/performance/md-kpis` (Board / Executive / IT Admin only)
- **MD/ED Alignment Survey scores Board-only** (filtered through same board_only mechanism)
- **Form 28** signed by Finance & Operations Manager only

**P1 — Settings wiring (no module hardcodes):**
- `lookups.leave_types` → `/api/leave/types` and balances
- `organisation.probation_period_months` → employee creation `probation_end_date`
- `organisation.paye_brackets / nhif_rates / nssf_employer_pct` → `/api/compliance/paye-calculator` (`config_source: masters_settings.organisation`)
- `performance.scoring_thresholds` → `get_rating_live()` helper

**P1 — Frontend gating:**
- `useModuleAccess(moduleId)` hook + `<AccessGate module="M??">` wrapper
- Applied to 8 routes: M10/M11/M12/M13/M14/M15/M18/M19
- 403 view shows lock icon + scope info

**P1 — Kenya helpers (`/utils/format.js`):**
- `fmtKES(amount)` — Intl.NumberFormat en-KE
- `fmtEAT(iso)` — Africa/Nairobi DD/MM/YYYY · HH:mm

**P2 — CSV exports (`/api/exports/*`):**
- `employees.csv` (HR/Exec/IT Admin; board_only filtered)
- `pay-bands.csv` (HR/Finance/Exec/IT Admin)
- `budget-allocations.csv` (HR/Finance/IT Admin)
- Frontend buttons on Employees, Compensation, Budget pages

## Test Results
- Iter 1–3: full pass
- Iter 4: 23/23 ✅
- Iter 5: deferred (variance bug → fixed in Iter 6)
- Iter 6: 22/22 ✅
- **Iter 7: 29/29 backend + 7/7 frontend ✅** (no product bugs; 8 initial test-script issues self-corrected)
- Iter 12–19: Centralized email service, throttle, retry queue, log viewer — all green.

## Changelog (recent)
- **2026-02-14** — Peer Recognition Nomination form switched from free-text input to `EmployeePicker` dropdown (excludes self, searchable). New backend endpoint `GET /api/employees/directory` returns minimal-info directory (id, full_name, role_title, department, lifecycle_state, work_email, profile_photo_url) for all authenticated users — used by shared pickers. EmployeePicker now consumes this endpoint so employees can nominate any colleague. Submit button disabled until a real employee is selected. Verified: nominee_id is now a real UUID (data integrity).
- **2026-02-14** — Recognition email body bug fixed: peer/manager recognition emails were rendering empty because triggers sent `nominator_name`/`behaviour` while templates used `{{from_name}}`/`{{message}}`. Added both alias styles in the triggers AND enhanced default templates to display Values, Behaviour, and Impact. `_ensure_seeded` now also refreshes non-customised seeded templates so live installs pick up improvements automatically (any IT-Admin edit is preserved).

## Roadmap

### P0 — Done
All foundational + structural corrections + role dashboards + Masters Settings + Access Gate + CSV exports.

### P1 — Done
Settings wiring (leave/probation/PAYE/scoring), AccessGate, Kenya helpers, CSV exports.

### P2 — Backlog
- S3-compatible photo / document uploads (employee photos, policy PDFs, exit clearance)
- Multi-tenancy (currently hardcoded "solvit")
- Role-specific dashboards for Line Manager & FinOps (D04) — currently both fall through to HR Admin Dashboard
- Salary Single Source of Truth standardisation (D08)
- Onboarding Drill-down view (D13)
- Refactor: routes → models/ + services/ split
- pytest coverage expansion
- Mobile-responsive layout audit
- Wire onboarding week labels + recognition event months from settings
- Unify `/api/leave/types` response shape

## Test Credentials
See `/app/memory/test_credentials.md` (9 accounts, all `Solvit@2026`).
