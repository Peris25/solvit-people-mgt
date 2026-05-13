# Solvit People Management Platform

A full-stack HR + workforce management platform for **Solvit Limited** (Kenyan tech-enabled vehicle inspection company). 19 modules covering the full employee lifecycle — Onboarding, Performance, Leave, L&D, Recognition, Disciplinary, Compensation, Budget, Compliance, Solvers, Recruitment, Surveys, Retention/Flight-Risk, Project Ownership, Policy Library, HR Calendar, Statutory Compliance, Intelligent Forms, and an actionable AI HR Assistant.

> **Brand:** Solvit Identity — Barlow font · Red `#FF353F` · Black · Light mode default.
> **Locale:** Kenya — KES currency, EAT timezone (UTC+3), NSSF / SHA / PAYE compliance built-in.

---

## Table of Contents
1. [Tech Stack](#tech-stack)
2. [Repository Layout](#repository-layout)
3. [Prerequisites](#prerequisites)
4. [Quick Start (Local)](#quick-start-local)
5. [Environment Variables](#environment-variables)
6. [Seed Data & Demo Accounts](#seed-data--demo-accounts)
7. [Running the Tests](#running-the-tests)
8. [Project Architecture](#project-architecture)
9. [Roles & Permissions Model](#roles--permissions-model)
10. [Common Tasks](#common-tasks)
11. [Production Deployment](#production-deployment)
12. [Troubleshooting](#troubleshooting)
13. [Security Notes](#security-notes)

---

## Tech Stack

| Layer | Choice |
|---|---|
| Backend | **FastAPI** (Python 3.11+), Motor (async MongoDB driver), APScheduler (automation rules) |
| Frontend | **React 18** (JS), React Router v6, Axios, Lucide icons, Shadcn/UI primitives, Barlow + Nunito Sans |
| Database | **MongoDB** 6+ |
| Process manager | **Supervisor** (`/etc/supervisor/conf.d/*.conf`) |
| AI | **Emergent LLM Key** (one key → GPT, Claude Sonnet, Gemini, Nano Banana) via `emergentintegrations` |
| Auth | JWT (HS256) — bcrypt password hashing |
| File storage | Local filesystem (S3-compatible swap is on the roadmap) |

---

## Repository Layout

```
/app
├── backend/
│   ├── server.py                 # FastAPI app entry — registers all routers
│   ├── database.py               # Motor client + index setup
│   ├── routes/                   # 30+ feature routers (employees, leave, ai_agent, …)
│   ├── automation/
│   │   ├── engine.py             # APScheduler + event bus
│   │   └── seed_data.py          # First-boot demo data + idempotent migrations
│   ├── utils/
│   │   ├── auth.py               # JWT + bcrypt
│   │   ├── access_matrix.py      # 19-module × 9-role permission matrix
│   │   └── kenya.py              # KES / EAT formatters, NSSF/SHA/PAYE calcs
│   ├── tests/                    # Pytest regression suite (iter_8 → iter_17)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.js                # Route table + AccessGate wrapping
│   │   ├── pages/                # One file per module (Leave, Performance, RolesPermissions, …)
│   │   ├── components/           # Sidebar, AIAgent, EmployeePicker, AccessGate, FirstLoginTour…
│   │   ├── context/              # AuthContext + ThemeContext
│   │   └── services/api.js       # Axios client + every endpoint helper
│   ├── public/index.html
│   └── package.json
├── memory/
│   ├── PRD.md                    # Product requirements + change log
│   └── test_credentials.md       # Test account credentials
├── .gitguardian.yml              # Secret-scanner allowlist
└── README.md                     # ← you are here
```

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| **Python** | 3.11 or newer | |
| **Node.js** | 18 or newer | |
| **Yarn** | 1.22+ (Classic) | **Do not** use `npm install` — Yarn is the supported package manager. |
| **MongoDB** | 6+ running on `localhost:27017` | Or any cluster — set `MONGO_URL` in `backend/.env`. |
| **Supervisor** *(prod only)* | 4+ | For background process management. Dev can run services directly. |

> **macOS dev setup:** `brew install python@3.11 node yarn mongodb-community supervisor`
> **Ubuntu dev setup:** `sudo apt install python3.11 python3-pip nodejs yarn mongodb supervisor`

---

## Quick Start (Local)

```bash
# 1) Clone
git clone https://github.com/Solvit17/Solvit-People-Platform.git
cd Solvit-People-Platform

# 2) Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

# Configure env (see "Environment Variables" below)
cp .env.example .env   # if you don't have one, write your own using the template below

# Start MongoDB (skip if already running)
sudo systemctl start mongod   # Linux
# OR
brew services start mongodb-community   # macOS

# Start backend (listens on :8001)
uvicorn server:app --host 0.0.0.0 --port 8001 --reload

# 3) Frontend (in a new terminal)
cd ../frontend
yarn install
# Configure env (see below)
echo "REACT_APP_BACKEND_URL=http://localhost:8001" > .env
yarn start   # opens http://localhost:3000
```

> **First-boot behavior:** the backend auto-seeds 9 demo users, 13 demo employees, holidays, pay bands, 47 automation rules, the reporting tree, and policies on startup. Re-runs are idempotent.

---

## Environment Variables

### `backend/.env`

```env
# --- Core ---
MONGO_URL="mongodb://localhost:27017"
DB_NAME="solvit_platform"
CORS_ORIGINS="*"                                  # comma-separated origins in prod
JWT_SECRET="<run: openssl rand -hex 32>"          # Required. Rotate per env.

# --- Demo / seeding ---
DEMO_SEED_PASSWORD="ChangeMe@2026"                # Initial password for all seeded demo users
ADMIN_EMAIL="jessica@solvit.co.ke"                # Bootstrap HR Admin account email
ADMIN_PASSWORD="ChangeMe@2026"                    # Bootstrap HR Admin password
FRONTEND_URL="http://localhost:3000"              # Used in outgoing email links

# --- AI ---
EMERGENT_LLM_KEY="sk-emergent-xxxxxxxxxxxx"       # Required for the AI HR Assistant
                                                  # (Emergent universal key for OpenAI/Claude/Gemini)

# --- Optional ---
ENCRYPTION_KEY=""                                 # Reserved for at-rest field encryption (not active yet)
```

### `frontend/.env`

```env
REACT_APP_BACKEND_URL=http://localhost:8001   # Local dev
# In production this should be your public API URL (no trailing slash). The
# frontend always prefixes API calls with /api so all backend routes resolve.
```

> **Never** commit `.env` files. They are git-ignored by default. Rotate `JWT_SECRET`, `DEMO_SEED_PASSWORD`, and `ADMIN_PASSWORD` for every environment.

---

## Seed Data & Demo Accounts

After the first boot, the platform contains 9 demo logins. **All use the same password from `DEMO_SEED_PASSWORD`** (default `ChangeMe@2026`).

| Role | Email | Purpose |
|---|---|---|
| HR Admin | `jessica@solvit.co.ke` | Full HR operational control |
| HR Manager *(seed as `hr_admin` — flip via Roles & Permissions)* | — | |
| Line Manager | `manager@solvit.co.ke` | David Ochieng — has direct reports |
| Finance & Ops Manager | `finance@solvit.co.ke` | Sarah Njoroge — Finance + LM layer |
| Employee | `employee@solvit.co.ke` | James Kamau |
| Solver | `solver@solvit.co.ke` | Mobile Solver app view |
| Executive (MD) | `md@solvit.co.ke` | Michael Omondi |
| Executive (ED) | `ed@solvit.co.ke` | Esther Wanjala |
| IT Admin | `itadmin@solvit.co.ke` | System configuration + Roles & Permissions |
| Board | `board@solvit.co.ke` | Board Chair (MD/ED's line manager) |

> Force a **clean reseed** any time via `Platform Settings → Automation → Reset Demo Data` (HR Admin only). User logins are preserved; only transactional data is wiped and re-seeded.

---

## Running the Tests

```bash
# Backend regression suite (latest iteration covers the access matrix + custom roles)
cd backend
export REACT_APP_BACKEND_URL="http://localhost:8001"   # required by the suite
pytest tests/test_iteration_17.py -v                   # latest
pytest tests/ -v                                       # full

# Lint
ruff check backend/
cd ../frontend && yarn eslint src/
```

There are 19 regression test modules (`test_iteration_8.py` → `test_iteration_17.py`). The newest module is always the canonical regression for the most recent features.

---

## Project Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                      Browser (React 18)                         │
│  Routes → AccessGate → Page → api.js (axios) ─────────────┐    │
└────────────────────────────────────────────────────────────┼───┘
                                                             │
                  REACT_APP_BACKEND_URL + /api/*             │
                                                             ▼
┌────────────────────────────────────────────────────────────────┐
│                  FastAPI (uvicorn :8001)                        │
│                                                                 │
│   routes/        ──→  utils/access_matrix.py (RBAC enforce)     │
│       ai_agent          ↓                                       │
│       leave             utils/auth.py (JWT)                     │
│       employees         ↓                                       │
│       budget            database.py (Motor) ──┐                 │
│       ...                                      │                 │
│                                                ▼                 │
│   automation/engine.py ── APScheduler ──► MongoDB              │
│       47 cron / event rules                                     │
└────────────────────────────────────────────────────────────────┘
```

### Key concepts

- **AccessGate** – Every protected route is wrapped in `<AccessGate module="M??">` in `App.js`. It calls `/api/access/check/M??` and blocks render if the response is `null`.
- **Runtime overrides** – `utils/access_matrix.py` holds two in-process stores (`RUNTIME_OVERRIDES`, `CUSTOM_ROLE_DEFINITIONS`) that are hydrated from MongoDB on boot and mutated by IT Admin via `/api/access/matrix/cell` and `/api/access/roles`. Enforcement reflects edits on the **next** request — no restart.
- **Automation engine** – 47 rules (cron + event-driven) defined in `seed_data.py` and stored in `automation_rules`. APScheduler runs daily/weekly crons; the event bus fires on `employee_created`, `leave_submitted`, etc.
- **AI HR Assistant** – Deterministic actions. `/api/ai-agent/chat` parses intent and returns a *proposal card*; HR Admin must click **Confirm** → `/api/ai-agent/execute` actually mutates data. Every action is audited.
- **Solvit Brand Identity** – Light mode default; Dark mode toggle (`ThemeContext.js`). Barlow for headings, Nunito Sans for body. Solvit red `#FF353F`.

---

## Roles & Permissions Model

9 roles × 19 modules. Permission **levels**: `Full` > `Manage` > `Read` > `None`. Optional **scope qualifier** (`own_record`, `own_team`, `own_reports`, `aggregate`, `salary_band`, `statutory_only`, …) narrows what data the role sees.

**Additive Layering Rule:**
Every user is an **Employee** first. Roles are *layers on top* of that base — Line Managers gain a team view, Finance gains a Finance & Admin panel, HR gains the org. **IT Admin only configures the system** (no Finance / Budget view).

### Edit the matrix at runtime
**Tools → Roles & Permissions** (IT Admin only):

1. **Access Matrix** tab – click any cell to change `Level` / `Scope` or revert to the seed default. Audited.
2. **User Assignments** tab – change any user's primary role from a dropdown. Audited.
3. **Custom Roles** tab – create a new role that **inherits** all permissions from any base role, then override individual cells in the Matrix tab. Delete a custom role and any user on it auto-rebases to `employee`.

---

## Common Tasks

| Task | How |
|---|---|
| **Add a new employee** | Login as HR Admin → Employees → Add Employee → fill form (Line Manager is mandatory) → Save |
| **Approve leave** | Login as Line Manager → Leave → Team tab → Approve / Reject |
| **Reset demo data** | HR Admin → Platform Settings → Automation → "Reset Demo Data" (user logins preserved) |
| **Pause the automation engine** | HR Admin → Platform Settings → Automation → uncheck "Enable Automation Rules Engine" → Save |
| **Change AI provider / temperature** | HR Admin → Platform Settings → AI Agent tab |
| **Import employees from Excel** | HR Admin → Data Import → download template → fill → upload |
| **Edit an email template** | HR Admin → Platform Settings → Email Delivery → choose template → edit Subject / Body / Merge Tags |
| **Test as another role** *(planned)* | IT Admin → Roles & Permissions → role switcher |

---

## Production Deployment

The application is designed for **Supervisor-managed deployments** behind an HTTP reverse proxy (nginx / Caddy / k8s ingress) that:
- Routes `/api/*` to the FastAPI backend on `:8001`
- Routes everything else to the React static build (or `node serve`) on `:3000`

Example supervisor config (`/etc/supervisor/conf.d/solvit.conf`):

```ini
[program:backend]
command=/app/backend/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8001
directory=/app/backend
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/backend.out.log
stderr_logfile=/var/log/supervisor/backend.err.log
environment=PYTHONUNBUFFERED=1

[program:frontend]
command=yarn start
directory=/app/frontend
autostart=true
autorestart=true
stdout_logfile=/var/log/supervisor/frontend.out.log
stderr_logfile=/var/log/supervisor/frontend.err.log
```

Restart after `.env` changes or dependency installs:
```bash
sudo supervisorctl restart backend frontend
```

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| **`Module 'emergentintegrations' not found`** | Install with the extra index URL — `pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/` |
| **Login works but redirects to login again** | `JWT_SECRET` mismatch between backend restarts — make sure it's static in `.env`, then restart backend |
| **`No access to module Mxx`** on every page | The logged-in user has a role with no access. Check `/api/access/matrix` and adjust in **Roles & Permissions**. |
| **Frontend loads but every API call 404s** | `REACT_APP_BACKEND_URL` missing or wrong in `frontend/.env`. Must point to the **public** URL when frontend is served from a different origin. |
| **`Cannot connect to MongoDB`** | Mongo not running or `MONGO_URL` is wrong. `mongo --eval 'db.runCommand({ping:1})'` to test. |
| **AI Agent says "AI not configured"** | `EMERGENT_LLM_KEY` missing in backend `.env`. Get one from Emergent Profile → Universal Key. |
| **Reset Demo Data button is greyed** | You're not HR Admin. Sign in as `jessica@solvit.co.ke`. |
| **`Reporting tree: corrected line_manager_id for N employees`** in logs | Normal — the migration runs idempotently on every boot. |

Logs:
```bash
tail -f /var/log/supervisor/backend.err.log       # backend errors
tail -f /var/log/supervisor/backend.out.log       # backend stdout (incl. seed messages)
tail -f /var/log/supervisor/frontend.err.log      # frontend build errors
```

---

## Security Notes

- **Demo seed password** is read from `DEMO_SEED_PASSWORD` in `backend/.env`. The previous hard-coded value has been removed. **Rotate per environment.**
- **PostHog key** in `frontend/public/index.html` is a public `phc_` project key — write-only ingest, safe to embed (this is PostHog's official integration pattern). Whitelisted in `.gitguardian.yml`.
- **Email templates** contain `{{temp_password}}` *merge tags* and a sample preview string. No real credentials. Whitelisted in `.gitguardian.yml`.
- **JWT secret** must be at least 32 random hex bytes. Generate with `openssl rand -hex 32`.
- **CORS** is wide-open by default (`*`) for local dev. Lock it down in production via `CORS_ORIGINS`.
- **Audit log** records every role change, matrix-cell edit, custom-role create/delete, destructive HR action, and AI Agent execution in the `audit_logs` collection.

---

## License

Proprietary — Solvit Limited. All rights reserved.
