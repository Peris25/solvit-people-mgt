# Solvit People Management Platform — PRD

## Original Problem Statement
Build a full-stack People Management Platform for **Solvit Limited** (Kenyan tech-enabled vehicle inspection company) implementing the FRD: 19 modules, intelligent forms engine (32 forms), automation rules engine, employee lifecycle state machine (9 FTE + 5 Solver states), AI HR Agent (Policy Q&A + Compliance Guardian), HR Kanban dashboard, Kenya statutory compliance (KES, EAT, NSSF/SHA/PAYE), pre-populated launch data and demo-friendly auth (standard login + 6 quick-login role tiles).

## Tech Stack (deviation from FRD)
- **Backend**: FastAPI + Motor (async MongoDB) + APScheduler  *(FRD said Node + Postgres; user explicitly approved Python+Mongo)*
- **Frontend**: React 18 (JS, not TS) + Tailwind utility classes + shadcn/ui
- **Auth**: JWT in httpOnly cookies (custom)
- **AI**: Emergent LLM Key (configurable provider in Settings — gpt-5.2 / Claude / Gemini)
- **Scheduler**: APScheduler (replaces Redis+Bull)
- **Timezone**: Africa/Nairobi (EAT)

## Architecture
```
/app/
├── backend/
│   ├── server.py              # FastAPI app — mounts 22 routers, init DB, start automation engine, seed_all
│   ├── database.py            # init_db, get_db, close_db (Motor)
│   ├── utils/auth.py          # bcrypt + jwt + get_current_user + require_roles
│   ├── routes/
│   │   ├── auth_routes.py    employees.py  solvers.py  recruitment.py
│   │   ├── onboarding.py     performance.py surveys.py  retention.py
│   │   ├── lnd.py            projects.py   compensation.py recognition.py
│   │   ├── budget.py         policies.py   disciplinary.py leave.py
│   │   ├── calendar.py       compliance.py settings.py    ai_agent.py
│   │   ├── forms.py          automation_routes.py
│   └── automation/
│       ├── engine.py         # APScheduler — daily cron, anniversary, compliance, fire_event
│       └── seed_data.py      # 6 demo users · 10 employees · 3 solvers · pay bands · 60+ rules · holidays · exit interview
└── frontend/src/
    ├── App.js                # 21 routes
    ├── context/AuthContext.js
    ├── services/api.js       # axios wrapper — all module endpoints
    ├── components/
    │   ├── Layout.js Sidebar.js (4 sections, 19 menu items, role-filtered)
    │   ├── AIAgent.js (slide-in panel, compliance check + chat)
    │   └── StatusBadge.js
    └── pages/
        Login (incl. 6 demo tiles), Dashboard (kanban+list), Employees,
        Solvers, Recruitment, Onboarding, Performance, Surveys, Retention,
        LnD, Projects, Compensation, Recognition, Budget, Policies,
        Disciplinary, Leave, Calendar, Compliance, Forms, Settings
```

## What's Implemented (Feb 2026)
### Auth & Demo Data
- 6 demo accounts (HR Admin/Line Mgr/Finance/Employee/Solver/MD) — password `Solvit@2026`
- 10 demo employees including Jessica (Active), Robert (Onboarding), John (Probation), Stephen (Exited)
- 3 demo solvers (Active Elite/High_Performer + Registering)
- 5 pay bands (L1–L5 + B1a)
- 12 Kenya 2026 public holidays
- Stephen Kiragu exit interview record
- 3 active pay band alerts (at_minimum, below_minimum)

### Automation Engine
- APScheduler with Africa/Nairobi tz, started on FastAPI startup
- 60+ rules across Onboarding, Probation, Performance, Surveys, Retention, Recognition, Exit, Leave, Compliance
- Event-driven: `fire_event(name, data)` reads matching rules from DB and dispatches
- Cron: daily 08:00 (probation reviews, onboarding overdue, solver inactive, leave SLA), anniversaries 08:30, compliance every 4h
- Actions: create_task, send_notification, change_state, trigger_workflow (incl. 7-task exit_workflow)

### Backend API (22 routers, /api prefix)
- Full CRUD for employees, solvers, candidates, leave, projects, policies, disciplinary
- Performance reviews + 9-box matrix + active cycle
- Retention: flight risk, exit insights, stay interviews
- L&D: IDP, training requests, skills matrix
- Compensation: pay bands, alerts, bonus calculator (Tier 1/2), GP gate, salary reviews
- Budget: people cost envelope (50% GP), summary by dept/level
- Compliance: PAYE/NSSF/SHA calculator, deadlines, statutory rates (Kenya 2026)
- Calendar: aggregates holidays + leave + onboarding milestones + surveys + manual events
- Forms: 32 form schemas (8 fully populated incl. quizzes with auto-scoring), submission endpoint
- AI Agent: chat with provider routing (OpenAI/Anthropic/Gemini via Emergent LLM Key) + deterministic fallback (policy search + compliance guardian)
- Settings: LLM/email provider config, audit log
- Automation routes: list rules, toggle, list/update tasks, notifications

### Frontend (21 pages + AI panel + Sidebar)
- Login screen with 6 demo quick-login tiles
- HR Dashboard: 6 KPI strip + Kanban (4 columns) + List view + notifications banner
- All 19 module pages live with consistent design system (red #FF353F, dark #191919, Arial)
- AI Agent slide-in panel for HR Admin/Manager
- Role-filtered Sidebar
- KES formatting + en-GB date formatting throughout

## Known Limitations / P1 Backlog
- Forms-engine: 8/32 schemas fully populated; remaining 24 are placeholders that submit but have empty field arrays
- AI Agent: relies on user configuring an API key in Settings (else falls back to deterministic policy search + compliance check)
- Email notifications: settings UI exists; SendGrid/SMTP send pipeline not yet wired (in-app notifications work)
- 9-box visual matrix not yet rendered on Performance page (data endpoint exists)
- Stay-interview UI not yet built (data endpoint exists)
- File uploads (S3 pre-signed URLs) — pending P2

## Roadmap

### P0 (Done)
- [x] App boot, login, role-based nav
- [x] All 21 frontend pages render
- [x] All 22 backend routers respond
- [x] Seed data + demo accounts
- [x] Automation engine running
- [x] AI Agent with fallback
- [x] PAYE/NSSF/SHA calculator
- [x] Forms engine (renderer + 8 fully-spec'd forms + auto-scoring)

### P1 (next iterations)
- [ ] Wire Emergent LLM Key as default for AI Agent (auto-configure on first use)
- [ ] Implement remaining 24 form schemas (FRD §7 reference)
- [ ] 9-box matrix UI on Performance page
- [ ] Stay-interview workflow UI
- [ ] Per-employee profile drilldown (timeline, IDP, leave history, recognitions)
- [ ] Notifications bell on Sidebar (live count)

### P2
- [ ] Email send pipeline (SendGrid + SMTP)
- [ ] File uploads with pre-signed URLs (policies, signatures, exit clearance)
- [ ] Refactor: split routes/employees.py and similar into models/ + services/ + routes/
- [ ] Pytest coverage in /app/backend/tests
- [ ] CSV export on Employees, Compensation, Budget

## Test Credentials
See `/app/memory/test_credentials.md`
