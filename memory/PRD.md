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
│   ├── server.py                    # 22 routers mounted at /api
│   ├── database.py / utils/auth.py / utils/email_service.py
│   ├── routes/                      # 22 route files
│   │   ├── auth_routes employees solvers recruitment onboarding
│   │   ├── performance surveys retention lnd projects
│   │   ├── compensation recognition budget policies disciplinary
│   │   ├── leave calendar compliance settings ai_agent
│   │   ├── forms forms_data automation_routes
│   ├── automation/engine.py + seed_data.py
│   └── tests/test_solvit_platform.py + test_iteration_2.py
└── frontend/src/
    ├── App.js (22 routes including /employees/:id)
    ├── context/AuthContext.js (auth_hint gated probe)
    ├── services/api.js
    ├── components/{Layout,Sidebar (with bell),AIAgent,StatusBadge}.js
    └── pages/  # 22 pages
        Login, Dashboard, Employees, EmployeeProfile, Solvers, Recruitment,
        Onboarding, Performance (3x3 9-box), Surveys, Retention (Stay Interview),
        LnD, Projects, Compensation, Recognition, Budget, Policies, Disciplinary,
        Leave, Calendar, Compliance, Forms, Settings (AI/Email/Automation/Audit)
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
- 3×3 9-box Talent Matrix (Performance × Potential)
- Reset Demo Data button (HR Admin only) — wipes 22 collections, re-seeds
- Default exclusion of Exited employees from /api/employees

### Iteration 2 — Five P1 enhancements (current)
- **Employee Profile Drilldown** (`/employees/:id`): 7 tabs (Overview/Timeline/Performance/Leave/Recognitions/Training/IDP) with rich aggregator endpoint
- **24 Form Schemas** in `forms_data.py` (form-04 alignment survey, form-07 self-review, form-08 probation, form-09 PIP, form-10 exit notice, form-11 OKR, form-12 IDP, form-13 training request, form-14 skills self-assess, form-16 policy ack, form-17 hearing notice, form-18 outcome letter, form-19 grievance, form-20 whistleblower, form-22 stay interview, form-23 exit clearance 23-task, form-24 NDA, form-25 reference letter, form-26 360 peer review, form-27 manager recognition, form-28 long service, form-29 solver suspension, form-30 solver perf review, form-32 solver award nomination). Plus 5 missing form-03 quiz questions.
- **Sidebar Notifications Bell**: red badge with unread count, 60s polling, dropdown with mark-as-read + mark-all-read
- **Stay Interview Workflow UI**: tab in Retention page; Schedule modal triggered from at-risk rows; Conduct modal captures Form-22 fields; persists to DB
- **Email Pipeline**: SendGrid + SMTP support via `utils/email_service.py`; settings UI exposes provider-specific fields; HR Admin can send test email; automation engine fires email on rule notifications when configured

## Test Results
- **Iteration 1**: 46/46 backend + 19/19 frontend pages ✅
- **Iteration 1.5**: 9-box, reset, profile filter ✅
- **Iteration 2**: 22/22 new + 46/46 regression + all critical frontend flows ✅

## Roadmap

### P0 (Done)
- App boot + auth + role-based nav
- All 22 frontend pages render
- All 22 backend routers respond
- Seed data + reset endpoint
- Automation engine
- AI Agent (Emergent LLM Key)
- 9-box matrix UI
- 32 form schemas (~80% fully populated)
- Employee profile drilldown
- Notifications bell
- Stay interview workflow
- Email pipeline (SendGrid + SMTP)

### P1
- Drag-and-drop reassignment on 9-box matrix
- Per-employee IDP edit form (currently view-only)
- Bulk actions (e.g., assign training to multiple employees)
- Employee photo uploads + S3 pre-signed URLs

### P2
- File uploads (policies, signatures, exit clearance docs)
- CSV exports (Employees, Compensation, Budget)
- Refactor: routes → models/ + services/ split
- pytest coverage expansion in /app/backend/tests
- Mobile-responsive layout audit
- Multi-tenancy (currently hardcoded "solvit")

## Test Credentials
See `/app/memory/test_credentials.md`.
