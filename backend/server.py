from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from database import init_db, close_db
from automation.engine import automation_engine
from automation.seed_data import seed_all

# Routes
from routes.auth_routes import router as auth_router
from routes.employees import router as employees_router
from routes.solvers import router as solvers_router
from routes.recruitment import router as recruitment_router
from routes.onboarding import router as onboarding_router
from routes.performance import router as performance_router
from routes.surveys import router as surveys_router
from routes.retention import router as retention_router
from routes.lnd import router as lnd_router
from routes.projects import router as projects_router
from routes.compensation import router as compensation_router
from routes.recognition import router as recognition_router
from routes.budget import router as budget_router
from routes.policies import router as policies_router
from routes.disciplinary import router as disciplinary_router
from routes.calendar import router as calendar_router
from routes.leave import router as leave_router
from routes.compliance import router as compliance_router
from routes.settings import router as settings_router
from routes.ai_agent import router as ai_agent_router
from routes.forms import router as forms_router
from routes.automation_routes import router as automation_router
from routes.access import router as access_router
from routes.masters_settings import router as masters_settings_router
from routes.exports import router as exports_router
from routes.documents import router as documents_router
from routes.data_import import router as data_import_router
from routes.email_templates import router as email_templates_router
from routes.email_delivery import router as email_delivery_router
from routes.onboarding_tour import router as onboarding_tour_router
from routes.dashboard import router as dashboard_router
from routes.reminders import router as reminders_router
from reminders.engine import reminder_engine

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Solvit People Management Platform", version="1.0.0")

_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://people.solvit.co.ke,http://localhost:3000"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(employees_router, prefix=API_PREFIX)
app.include_router(solvers_router, prefix=API_PREFIX)
app.include_router(recruitment_router, prefix=API_PREFIX)
app.include_router(onboarding_router, prefix=API_PREFIX)
app.include_router(performance_router, prefix=API_PREFIX)
app.include_router(surveys_router, prefix=API_PREFIX)
app.include_router(retention_router, prefix=API_PREFIX)
app.include_router(lnd_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(compensation_router, prefix=API_PREFIX)
app.include_router(recognition_router, prefix=API_PREFIX)
app.include_router(budget_router, prefix=API_PREFIX)
app.include_router(policies_router, prefix=API_PREFIX)
app.include_router(disciplinary_router, prefix=API_PREFIX)
app.include_router(calendar_router, prefix=API_PREFIX)
app.include_router(leave_router, prefix=API_PREFIX)
app.include_router(compliance_router, prefix=API_PREFIX)
app.include_router(settings_router, prefix=API_PREFIX)
app.include_router(ai_agent_router, prefix=API_PREFIX)
app.include_router(forms_router, prefix=API_PREFIX)
app.include_router(automation_router, prefix=API_PREFIX)
app.include_router(access_router, prefix=API_PREFIX)
app.include_router(masters_settings_router, prefix=API_PREFIX)
app.include_router(exports_router, prefix=API_PREFIX)
app.include_router(documents_router, prefix=API_PREFIX)
app.include_router(data_import_router, prefix=API_PREFIX)
app.include_router(email_templates_router, prefix=API_PREFIX)
app.include_router(email_delivery_router, prefix=API_PREFIX)
app.include_router(onboarding_tour_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)
app.include_router(reminders_router, prefix=API_PREFIX)


@app.get("/api/health")
async def health():
    return {"status": "healthy", "app": "Solvit People Platform"}


@app.on_event("startup")
async def startup():
    logger.info("Starting Solvit People Platform...")
    db = await init_db()
    # Create indexes
    await db.users.create_index("email", unique=True)
    await db.employees.create_index([("tenant_id", 1), ("work_email", 1)])
    await db.solvers.create_index([("tenant_id", 1), ("phone_number", 1)])
    await db.notifications.create_index([("tenant_id", 1), ("recipient_role", 1), ("is_read", 1)])
    await db.tasks.create_index([("tenant_id", 1), ("status", 1)])

    # Seed initial data — only runs when SEED_DEMO=true (dev/first-boot only)
    if os.environ.get("SEED_DEMO", "false").lower() == "true":
        await seed_all(db)
    else:
        logger.info("SEED_DEMO is not set — skipping demo data seed")
    
    # Hydrate runtime access overrides + custom roles from MongoDB
    from utils.access_matrix import load_runtime_state
    await load_runtime_state(db)
    # Start automation engine
    await automation_engine.start(db)
    # Start reminder engine (registers cron jobs for all enabled rules)
    await reminder_engine.start(db)
    logger.info("✅ Solvit People Platform started successfully")


@app.on_event("shutdown")
async def shutdown():
    await close_db()
    if automation_engine.scheduler:
        automation_engine.scheduler.shutdown()
    await reminder_engine.shutdown()
    logger.info("Solvit People Platform shut down")
