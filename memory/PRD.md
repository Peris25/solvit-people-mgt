# Solvit People Management Platform — PRD

## Original Problem Statement
Build a full-stack People Management Platform for **Solvit Limited** (Kenyan tech-enabled vehicle inspection company) implementing the FRD: 19 modules, intelligent forms engine (32 forms), automation rules engine, employee lifecycle state machine (9 FTE + 5 Solver states), AI HR Agent (Policy Q&A + Compliance Guardian), HR Kanban dashboard, Kenya statutory compliance (KES, EAT, NSSF/SHA/PAYE), pre-populated launch data and demo-friendly auth (standard login + 6 quick-login role tiles).

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
/app/
├── backend/
│   ├── server.py                       # 23 routers mounted at /api
│   ├── database.py / utils/auth.py / utils/email_service.py / utils/access_matrix.py
│   ├── routes/                          # 23 route files (incl. access.py)
│   ├── automation/engine.py             # FORM_OUTCOME_HANDLERS + APScheduler
│   └── tests/test_iteration_*.py        # iters 1–4
└── frontend/src/
    ├── App.js (uses RoleDashboard)
    ├── components/Layout.js (skips sidebar for solver)
    ├── components/Sidebar.js (MENU_ITEMS aligned with Section A matrix)
    └── pages/
        Dashboard.js (HR Admin — 4 zones)
        EmployeeDashboard.js (FTE — 5 tabs)
        SolverDashboard.js (Solver — bottom nav, mobile)
        RoleDashboard.js (router by role)
        + 19 module pages
```

## Implemented (May 2026)

### Iteration 1 — MVP foundation
- 6 demo accounts, 10 employees, 3 solvers, 5 pay bands, 60+ rules, 12 holidays
- 21 frontend pages with consistent design system (red #FF353F, dark #191919, Arial)
- AI HR Agent with Emergent LLM Key default + deterministic fallback
- HR Kanban (4 cols), 6 KPIs, role-filtered sidebar
- KES + en-GB date formatting; PAYE/NSSF/SHA calculator

### Iteration 1.5 — Bug fix + enhancements
- Fixed 401-on-login bug via localStorage auth_hint gating
- 3×3 9-box Talent Matrix
- Reset Demo Data button (HR Admin only)

### Iteration 2 — Five P1 enhancements
- Employee Profile Drilldown (7 tabs)
- 24 Form Schemas (form-04 alignment, form-08 probation, form-22 stay interview, form-23 exit clearance, etc.)
- Sidebar Notifications Bell with unread badge
- Stay Interview Workflow UI
- Email Pipeline (SendGrid + SMTP)

### Iteration 3 — FRD Corrections + Form Workflow Matrix
- 9-Box axes corrected to **Performance × Values**
- Talent Density score (composite KPI, target 85%) backend + frontend gauge
- Voluntary Attrition KPI (rolling 12mo, target ≤10%) excluding probation exits
- Module renumbering matches FRD §3
- Sequential Form Workflow Matrix (Form-Workflow-User Matrix.docx) with role-based step routing + signatures
- "My Tasks" page for pending form sign-offs
- Drag-and-drop 9-box reassignment
- IDP edit form, bulk transitions, bulk training assignment
- Q3 stay-interview one-click trigger
- Global Axios 401/500 interceptors

### Iteration 4 — Review Panel + Form Outcomes + Access Matrix + Role Dashboards (CURRENT)
- **Review Meeting Panel** (`GET /api/performance/review-panel/{employee_id}`):
  - MD/CEO → `[]` (board-led, is_md=true)
  - reports_to_md=true → `[md, hr_admin]`
  - reports_to_finance_ops=true → `[hr_admin, line_manager:finance_ops]`
  - default → `[hr_admin, line_manager]`
  - HR has casting vote (`casting_vote_role: hr_admin`)
  - `EmployeeUpdate` Pydantic now exposes `is_md`, `reports_to_md`, `reports_to_finance_ops` so HR can configure routing through PUT `/api/employees/{id}`
- **Form Outcome Triggers** in `automation/engine.py` (`FORM_OUTCOME_HANDLERS`):
  - form-08 Probation Pass/Extend/Fail → Active / Probation / Exiting
  - form-09 PIP → state=PIP
  - form-10 Below score → state=Realignment
  - form-19 Suspension → state=Suspended
  - form-31 Resignation → state=Exiting + 7 exit workflow tasks (safety-net inline call)
  - form-23 Exit Clearance fully signed → state=Exited
  - + 15 more outcomes flag/audit + downstream event chain
- **Access Rule Matrix** (Section A: 19 modules × 7 roles; Section B: 7 destructive actions):
  - `utils/access_matrix.py` — authoritative source
  - `GET /api/access/matrix` — returns full matrix + `my_access` for caller
  - `GET /api/access/check/{module_id}` — single-module check
  - `enforce_module()` and `enforce_destructive()` helpers
  - Section B applied to `POST /api/employees/{id}/transition` and `POST /api/employees/bulk-transition` (HR Admin only)
- **Role-Specific Dashboards** (`/dashboard` routes via `RoleDashboard.js` by `user.role`):
  - **HR Admin / Manager / Executive / Line Manager / Finance** → 4-zone control surface (alerts banner with critical/elevated/info colour-coded cards · Kanban board with search · Calendar widget (next 14 days) · Talent Density gauge · 6-tile Quick Stats Bar including Attrition + Talent Density)
  - **Employee (FTE)** → personal action surface with horizontal 5-tab nav (Dashboard / Reviews / Development / Recognition / Leave); My Tasks zone, My Performance zone with Section A/B/C breakdown, My Leave balance, My Recognition recent 3
  - **Solver** → mobile-only bottom-nav with 5 tabs (Home / Performance / Recognition / Surveys / Tasks); tier card · 4 score dials · NO sidebar
- **Sidebar role visibility** aligned to Section A matrix (per-module roles list)

## Test Results
- **Iter 1**: 46/46 backend + 19/19 frontend ✅
- **Iter 2**: 22/22 new + 46/46 regression ✅
- **Iter 3**: matrix-routing + KPIs + 9-box drag-drop + bulk + IDP all green ✅
- **Iter 4**: 23/23 new pass (1 skipped — md_direct_report; now resolved) + all regression ✅
  - Backend: access matrix endpoints, review panel (3 branches), form outcomes (form-08/09/10/31), enforce_destructive 403 on line_manager
  - Frontend: HR Admin 4-zone dashboard, Employee 5-tab dashboard, Solver bottom-nav dashboard

## Roadmap

### P0 (Done)
- App boot + auth + role-based nav
- All 22 frontend pages render
- All 23 backend routers respond
- Seed data + reset endpoint
- Automation engine + form outcome triggers
- AI Agent (Emergent LLM Key)
- 9-box matrix UI (drag-drop, Performance × Values)
- 32 form schemas with sequential workflow + signatures
- Employee profile drilldown
- Notifications bell
- Stay interview workflow
- Email pipeline (SendGrid + SMTP)
- Talent Density / Voluntary Attrition KPIs
- Form Workflow Matrix (sequential routing)
- Review Meeting Panel logic (3 branches + casting vote)
- Form Outcome Triggers → state-machine integration
- Access Rule Matrix (Section A + B) + enforcement at API
- Role dashboards (HR / FTE / Solver)

### P1 (Next)
- Kenya-specific logic: KES currency formatter component, EAT timezone normaliser, statutory compliance rules per Kenyan Employment Act
- Frontend gating using `/api/access/check/{module_id}` (currently sidebar shows by role; pages don't yet read the matrix)
- Per-employee IDP edit form polish
- Employee photo uploads (S3 pre-signed URLs)
- CSV exports (Employees, Compensation, Budget)
- /access/matrix should hide other-role rows for non-admin (metadata leak — minor)

### P2
- File uploads (policies, signatures, exit clearance docs) — S3
- Refactor: routes → models/ + services/ split
- pytest coverage expansion
- Mobile-responsive layout audit (FTE dashboard mainly)
- Multi-tenancy (currently hardcoded "solvit")

## Test Credentials
See `/app/memory/test_credentials.md`.
