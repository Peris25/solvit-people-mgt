# Solvit People Management Platform — PRD

## Original Problem Statement
Build a full-stack People Management Platform for **Solvit Limited** (Kenyan tech-enabled vehicle inspection company) implementing the FRD: 19 modules, intelligent forms engine (32 forms), automation rules engine, employee lifecycle state machine (9 FTE + 5 Solver states), AI HR Agent (Policy Q&A + Compliance Guardian), HR Kanban dashboard, Kenya statutory compliance (KES, EAT, NSSF/SHA/PAYE), pre-populated launch data and demo-friendly auth (standard login + 7 quick-login role tiles).

## Tech Stack
- Backend: FastAPI + Motor (async MongoDB) + APScheduler + sendgrid (6.12.5)
- Frontend: React 18 + Tailwind utility classes
- Auth: JWT in httpOnly cookies (custom)
- AI: Emergent LLM Key (gpt-5.2 default; Claude/Gemini via Settings)
- Scheduler: APScheduler (replaces Redis+Bull from FRD)
- Email: SendGrid OR generic SMTP (configurable in Settings)
- Timezone: Africa/Nairobi (EAT)

## Architecture
```
/app/backend/
├── server.py                       # 24 routers mounted at /api
├── utils/{auth, email_service, access_matrix}.py
├── routes/
│   ├── access.py / masters_settings.py  # Section A/B + Masters Settings
│   ├── budget.py (live envelope_pct + allocation_threshold from settings)
│   ├── performance.py (talent_density target from settings)
│   ├── retention.py  (attrition target from settings)
│   └── 20 module routes
└── automation/{engine.py, seed_data.py}

/app/frontend/src/
├── App.js (RoleDashboard for /dashboard)
├── components/
│   ├── Layout.js (skips sidebar for solver)
│   ├── Sidebar.js (role-scoped MENU_ITEMS + custom employee menu)
│   ├── EmployeePicker.js (shared dropdown — never typed)
│   └── MastersValueEditor.js (generic JSON editor)
└── pages/
    ├── Dashboard.js (HR — alerts/kanban/calendar/talent gauge/stats)
    ├── EmployeeDashboard.js (FTE — 5 tabs)
    ├── SolverDashboard.js (mobile bottom-nav)
    ├── Budget.js (GP/Form 28/Headroom Allocations)
    ├── MastersSettings.js (11 tabs, audit log)
    └── 19 module pages
```

## Implemented (May–Feb 2026)

### Iter 1 — MVP foundation
- 7 demo accounts, 10 employees, 3 solvers, 5 pay bands, 60+ rules, 12 holidays
- 21 frontend pages, AI HR Agent, KES + en-GB date formatting

### Iter 1.5 / 2 / 3 — Bugs + enhancements
- 401-on-login fix, 9-Box Talent Matrix, Reset Demo Data
- Employee Profile Drilldown (7 tabs), 24 form schemas, Notifications Bell, Stay Interview UI, SendGrid + SMTP
- 9-Box axes corrected to **Performance × Values**, Talent Density (target 85%), Voluntary Attrition (≤10% target), Module renumbering, Sequential Form Workflow Matrix + signatures, "My Tasks", drag-and-drop 9-box, IDP edit, bulk actions, Q3 stay-interview, global Axios 401/500 interceptors

### Iter 4 — Review Panel + Form Outcomes + Access Matrix + Role Dashboards
- `GET /api/performance/review-panel/{id}` (3 branches + casting vote)
- Form-Outcome → state-machine triggers in `automation/engine.py`
- Access Rule Matrix Section A (19 modules × 7 roles) + Section B (7 destructive actions); enforcement at API layer
- 3 role dashboards: HR Admin (4-zone), FTE (5 tabs), Solver (mobile bottom-nav)

### Iter 5 — UX cleanup + Budget rebuild + Login refresh
- **Leave types** simplified labels ("Annual leave", "Sick leave"…); description shown as helper text
- **EmployeePicker** shared searchable dropdown — used for Leave handover, Disciplinary employee — no free-text employee selection anywhere
- **Employee role sidebar** trimmed to "My Workspace" (My Tasks first, no Forms, no Finance & Admin)
- **Disciplinary** runtime crash fixed (defensive null on cases array)
- **Compensation** Pay Bands editable by HR Admin (PUT /pay-bands/{id} + edit modal)
- **Consultant** added to employment types (FTE / Solver / Consultant)
- **Budget Governance rebuild** per spec: Finance-only GP Actual + Form 28 + Tier confirmation + Department breakdown with 5 canonical labels (Operations / Commercial & Business Development / Finance / Technology / HR & People — "Leadership"/"Valuation" remapped) + Headroom Allocation panel with KES 50k Finance approval gate + variance-on-Spent returns to unallocated pool
- **Login** refreshed with Solvit hero photo + Solvit logo

### Iter 6 — General Masters Settings (CURRENT, 100% pass — 22/22)
- New role: **IT Admin** (`itadmin@solvit.co.ke`, dept Technology)
- New module: `routes/masters_settings.py` — 11 categories: organisation, workforce, performance, budget_compensation, onboarding, recruitment, alignment_surveys, retention, recognition, notifications, lookups
- Endpoints:
  - `GET /api/settings/masters` — categories + write_access summary for caller
  - `GET /api/settings/masters/all` — full snapshot (for frontend cache)
  - `GET /api/settings/masters/{category}` — single category
  - `PUT /api/settings/masters/{category}` — section-scoped writes (IT Admin always; HR/Finance per WRITE_ACCESS table)
  - `POST /api/settings/masters/{category}/reset` — IT Admin only
  - `GET /api/settings/masters/audit/log` — IT Admin + HR Admin
- All defaults pre-loaded (NHIF rates, PAYE brackets, notice periods, scoring thresholds, bonus multipliers, tier targets, onboarding weeks, recruitment stages, survey pillars, etc.)
- **Audit log** captures field-level diffs (old → new, by whom, when) on every save
- **Live cross-module integration** (no restart):
  - `budget_compensation.people_cost_envelope_pct_of_gp` → `/api/budget/envelope`
  - `budget_compensation.allocation_finance_approval_threshold_kes` → `POST /budget/allocations`
  - `performance.talent_density_target_pct` → `/api/performance/talent-density`
  - `retention.attrition_target_pct` → `/api/retention/voluntary-attrition`
- Frontend: `/masters` page with 11 tabs, generic JSON editor (primitive/array/table/nested), audit log modal
- Sidebar: "Masters Settings" visible to it_admin/hr_admin/finance; existing /settings renamed to "AI & Email Setup"
- Login: 7th demo tile "IT Admin"
- **Bug fix**: Budget allocation `variance returns to unallocated pool on Spent` — `allocations_summary` now sums `spent_amount_kes` for Spent rows instead of full `amount_kes`

## Test Results
- Iter 1: 65/65 ✅ · Iter 2: 22+46 ✅ · Iter 3: full pass ✅ · Iter 4: 23/23 + skip resolved ✅ · Iter 5: deferred (variance bug flagged, fixed in iter 6) · **Iter 6: 22/22 backend + 100% frontend role coverage ✅**

## Roadmap

### P0 (Done)
- All foundational features above; Masters Settings; access matrix; review panel; form outcomes; role dashboards.

### P1 (Next)
- Wire ALL remaining hardcoded values to Masters Settings (currently wired: 4 cross-module reads. Remaining: probation duration on auto-transitions, leave types lookup driving /api/leave/types response, recognition event months feeding calendar widget, NSSF/PAYE feeding compensation calculator, onboarding week labels driving the onboarding tracker UI, scoring thresholds in performance review form)
- Frontend page-level gating reading `/api/access/check/{module_id}`
- Kenya-specific helpers: KES formatter component, EAT timezone normaliser, statutory compliance rules per Employment Act
- Employee photo uploads (S3 pre-signed URLs)
- CSV exports

### P2
- File uploads (policies, signatures, exit clearance) — S3
- Refactor: routes → models/ + services/ split
- pytest coverage expansion
- Mobile-responsive layout audit
- Multi-tenancy (currently hardcoded "solvit")

## Test Credentials
See `/app/memory/test_credentials.md`. New: `itadmin@solvit.co.ke` / Solvit@2026 (it_admin).
