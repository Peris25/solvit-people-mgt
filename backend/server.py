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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="Solvit People Management Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    # Seed initial data
    await seed_all(db)
    # Start automation engine
    await automation_engine.start(db)
    logger.info("✅ Solvit People Platform started successfully")


@app.on_event("shutdown")
async def shutdown():
    await close_db()
    if automation_engine.scheduler:
        automation_engine.scheduler.shutdown()
    logger.info("Solvit People Platform shut down")
