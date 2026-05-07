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
- Refactor: routes → models/ + services/ split
- pytest coverage expansion
- Mobile-responsive layout audit
- Wire onboarding week labels + recognition event months from settings (low impact, mostly UI)
- Unify `/api/leave/types` response shape (currently dict; consider list-of-objects)

## Test Credentials
See `/app/memory/test_credentials.md` (9 accounts, all `Solvit@2026`).
