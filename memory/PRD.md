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
