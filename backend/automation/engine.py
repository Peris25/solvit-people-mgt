"""Automation Rules Engine using APScheduler"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta
import logging
import uuid

logger = logging.getLogger(__name__)

EXIT_WORKFLOW_TASKS = [
    {"task_key": "ET01", "title": "Schedule and conduct exit interview (Form 21)", "assigned_role": "hr_admin", "days_due": 5},
    {"task_key": "ET02", "title": "Send resignation acknowledgement to employee", "assigned_role": "system", "days_due": 0},
    {"task_key": "ET03", "title": "Send Post-Employment Confidentiality form (Form 24)", "assigned_role": "system", "days_due": 0},
    {"task_key": "ET04", "title": "Issue Exit Clearance Checklist (Form 23)", "assigned_role": "hr_admin", "days_due": 0},
    {"task_key": "ET05", "title": "Assign handover plan to departing employee and line manager", "assigned_role": "hr_admin", "days_due": 2},
    {"task_key": "ET06", "title": "Send system access revocation checklist to IT", "assigned_role": "system", "days_due": 0},
    {"task_key": "ET07", "title": "Final pay calculation notification to Finance", "assigned_role": "system", "days_due": 0},
]


class AutomationEngine:
    def __init__(self):
        self.db = None
        self.scheduler = None
        self._started = False

    async def start(self, db):
        self.db = db
        if self._started:
            return
        self.scheduler = AsyncIOScheduler(timezone="Africa/Nairobi")
        # Cron rules — run daily checks
        self.scheduler.add_job(self._run_daily_cron, "cron", hour=8, minute=0, id="daily_cron")
        # Compliance check every 4 hours
        self.scheduler.add_job(self._run_compliance_check, "interval", hours=4, id="compliance_4h")
        # Anniversary check daily
        self.scheduler.add_job(self._check_anniversaries, "cron", hour=8, minute=30, id="anniversary_check")
        self.scheduler.start()
        self._started = True
        logger.info("✅ Automation Engine started")

    async def fire_event(self, event_name: str, data: dict):
        """Fire an event-driven automation rule"""
        if not self.db:
            return
        try:
            rules = await self.db.automation_rules.find({
                "trigger_type": "event",
                "trigger_event": event_name,
                "is_active": True,
                "tenant_id": "solvit"
            }).to_list(20)
            for rule in rules:
                await self._execute_rule(rule, data)
        except Exception as e:
            logger.error(f"Error firing event {event_name}: {e}")

    async def _execute_rule(self, rule: dict, data: dict):
        """Execute a single automation rule"""
        try:
            action_type = rule.get("action_type")
            payload = rule.get("action_payload_json", {})
            rule_id = rule.get("rule_id")

            if action_type == "create_task":
                await self._create_task_action(rule, data, payload)
            elif action_type == "send_notification":
                await self._send_notification_action(rule, data, payload)
            elif action_type == "change_state":
                await self._change_state_action(rule, data, payload)
            elif action_type == "trigger_workflow":
                await self._trigger_workflow_action(rule, data, payload)

            await self.db.automation_rules.update_one(
                {"_id": rule["_id"]},
                {"$set": {"last_executed_at": datetime.now(timezone.utc).isoformat(), "last_execution_status": "success"}}
            )
        except Exception as e:
            logger.error(f"Rule {rule.get('rule_id')} failed: {e}")
            try:
                await self.db.automation_rules.update_one(
                    {"_id": rule["_id"]},
                    {"$set": {"last_executed_at": datetime.now(timezone.utc).isoformat(), "last_execution_status": "failed"}}
                )
                await self._notify_hr_admin_failure(rule.get("rule_id"), str(e))
            except Exception:
                pass

    async def _create_task_action(self, rule: dict, data: dict, payload: dict):
        task_type = payload.get("task_type", "general")
        employee_id = data.get("employee_id")
        if task_type == "onboarding_setup":
            # Trigger onboarding task creation
            if employee_id:
                from routes.onboarding import FTE_ONBOARDING_TASKS
                tasks = []
                for template in FTE_ONBOARDING_TASKS:
                    tasks.append({
                        "id": str(uuid.uuid4()),
                        "tenant_id": "solvit",
                        "entity_id": employee_id,
                        "entity_type": "employee",
                        "task_key": template["task_key"],
                        "title": template["title"],
                        "assigned_role": template["assigned_role"],
                        "status": "Pending",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
                if tasks:
                    await self.db.onboarding_tasks.insert_many(tasks)
        elif task_type == "solver_induction":
            solver_id = data.get("solver_id")
            if solver_id:
                from routes.onboarding import SOLVER_INDUCTION_TASKS
                tasks = []
                for template in SOLVER_INDUCTION_TASKS:
                    tasks.append({
                        "id": str(uuid.uuid4()),
                        "tenant_id": "solvit",
                        "entity_id": solver_id,
                        "entity_type": "solver",
                        "task_key": template["task_key"],
                        "title": template["title"],
                        "assigned_role": template["assigned_role"],
                        "status": "Pending",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    })
                if tasks:
                    await self.db.onboarding_tasks.insert_many(tasks)
        else:
            # Generic task
            task = {
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "task_type": task_type,
                "title": payload.get("description", rule.get("description", "Automated task")),
                "status": "Pending",
                "rule_id": rule.get("rule_id"),
                "entity_id": employee_id or data.get("solver_id"),
                "assigned_role": "hr_admin",
                "days_due": payload.get("days_due"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.db.tasks.insert_one(task)

    async def _send_notification_action(self, rule: dict, data: dict, payload: dict):
        message = payload.get("message", rule.get("description", "Automated notification"))
        recipients = rule.get("notification_recipients_json", [])
        for recipient_role in recipients:
            notif = {
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "rule_id": rule.get("rule_id"),
                "recipient_role": recipient_role,
                "title": f"[{rule.get('category', 'System')}] {rule.get('rule_id', 'Notification')}",
                "message": message,
                "data": data,
                "is_read": False,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.db.notifications.insert_one(notif)
            # Best-effort email — does nothing if email provider not configured
            try:
                users = await self.db.users.find({"role": recipient_role, "tenant_id": "solvit"}).to_list(50)
                for u in users:
                    if u.get("email"):
                        from utils.email_service import send_email
                        await send_email(
                            self.db, u["email"],
                            subject=notif["title"],
                            html=f"<p>{message}</p><p><small>Sent by Solvit People Platform automation</small></p>"
                        )
            except Exception as e:
                logger.warning(f"Email notification skipped: {e}")

    async def _change_state_action(self, rule: dict, data: dict, payload: dict):
        new_state = payload.get("new_state")
        employee_id = data.get("employee_id")
        if new_state and employee_id:
            from bson import ObjectId
            try:
                await self.db.employees.update_one(
                    {"_id": ObjectId(employee_id)},
                    {"$set": {"lifecycle_state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
            except Exception:
                await self.db.employees.update_one(
                    {"id": employee_id},
                    {"$set": {"lifecycle_state": new_state, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )

    async def _trigger_workflow_action(self, rule: dict, data: dict, payload: dict):
        workflow = payload.get("workflow")
        if workflow == "exit_workflow":
            await self._create_exit_tasks(data.get("employee_id"))

    async def _create_exit_tasks(self, employee_id: str):
        """Create all 7 exit workflow tasks within 60 seconds"""
        if not employee_id:
            return
        tasks = []
        for template in EXIT_WORKFLOW_TASKS:
            tasks.append({
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "task_type": "exit_workflow",
                "task_key": template["task_key"],
                "title": template["title"],
                "entity_id": employee_id,
                "entity_type": "employee",
                "assigned_role": template["assigned_role"],
                "status": "Pending",
                "days_due": template["days_due"],
                "created_at": datetime.now(timezone.utc).isoformat()
            })
        if tasks:
            await self.db.tasks.insert_many(tasks)
        logger.info(f"✅ Created {len(tasks)} exit workflow tasks for employee {employee_id}")

    async def _notify_hr_admin_failure(self, rule_id: str, error: str):
        """Silent failures not acceptable — notify HR Admin"""
        await self.db.notifications.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": "solvit",
            "recipient_role": "hr_admin",
            "title": f"Automation Rule Failure: {rule_id}",
            "message": f"Rule {rule_id} failed with error: {error}",
            "is_read": False,
            "priority": "high",
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    async def _run_daily_cron(self):
        """Run daily cron automation checks"""
        if not self.db:
            return
        try:
            await self._check_onboarding_overdue()
            await self._check_probation_reviews()
            await self._check_solver_inactive()
            await self._check_leave_requests()
            logger.info("Daily cron completed")
        except Exception as e:
            logger.error(f"Daily cron error: {e}")

    async def _check_onboarding_overdue(self):
        now = datetime.now(timezone.utc)
        overdue_tasks = await self.db.onboarding_tasks.find({
            "tenant_id": "solvit",
            "status": "Pending",
            "due_date": {"$lt": (now - timedelta(days=3)).isoformat()[:10]}
        }).to_list(50)
        for task in overdue_tasks:
            await self.db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "recipient_role": "hr_admin",
                "rule_id": "AR-OB-04",
                "title": f"Onboarding Task Overdue: {task.get('title', '')}",
                "message": f"Onboarding task is 3+ days overdue for entity {task.get('entity_id')}",
                "is_read": False,
                "created_at": now.isoformat()
            })

    async def _check_probation_reviews(self):
        now = datetime.now(timezone.utc)
        probation_emps = await self.db.employees.find({
            "tenant_id": "solvit",
            "lifecycle_state": "Probation"
        }).to_list(50)
        for emp in probation_emps:
            start_date = emp.get("start_date")
            if not start_date:
                continue
            try:
                start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
                days_in_probation = (now - start_dt).days
                for check_day, rule_id, title in [(28, "AR-PR-01", "Month 1"), (56, "AR-PR-02", "Month 2"), (84, "AR-PR-03", "Month 3")]:
                    if check_day - 2 <= days_in_probation <= check_day:
                        existing = await self.db.tasks.find_one({
                            "entity_id": str(emp.get("id", str(emp["_id"]))),
                            "task_type": f"probation_review_{title.replace(' ', '_').lower()}",
                            "tenant_id": "solvit"
                        })
                        if not existing:
                            await self.db.tasks.insert_one({
                                "id": str(uuid.uuid4()),
                                "tenant_id": "solvit",
                                "task_type": f"probation_review_{title.replace(' ', '_').lower()}",
                                "title": f"Probation {title} Review — {emp.get('full_name')}",
                                "entity_id": str(emp.get("id", str(emp["_id"]))),
                                "entity_type": "employee",
                                "assigned_role": "hr_admin",
                                "status": "Pending",
                                "rule_id": rule_id,
                                "created_at": now.isoformat()
                            })
            except Exception as e:
                logger.error(f"Probation check error for {emp.get('full_name')}: {e}")

    async def _check_solver_inactive(self):
        """AR-EX-06: Solver inactive 60+ days"""
        now = datetime.now(timezone.utc)
        sixty_days_ago = (now - timedelta(days=60)).isoformat()[:10]
        active_solvers = await self.db.solvers.find({
            "tenant_id": "solvit",
            "lifecycle_state": "Active"
        }).to_list(100)
        for solver in active_solvers:
            activation_date = solver.get("activation_date", "")
            if activation_date and activation_date < sixty_days_ago:
                await self.db.solvers.update_one(
                    {"_id": solver["_id"]},
                    {"$set": {"lifecycle_state": "Inactive", "updated_at": now.isoformat()}}
                )
                await self.db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": "solvit",
                    "recipient_role": "line_manager",
                    "rule_id": "AR-EX-06",
                    "title": f"Solver Set Inactive: {solver.get('full_name')}",
                    "message": f"Solver {solver.get('full_name')} has been inactive for 60+ days",
                    "is_read": False,
                    "created_at": now.isoformat()
                })

    async def _check_leave_requests(self):
        """AR-LV-02: Leave unapproved 2 days"""
        now = datetime.now(timezone.utc)
        two_days_ago = (now - timedelta(days=2)).isoformat()
        overdue = await self.db.leave_requests.find({
            "tenant_id": "solvit",
            "status": "Pending_Manager",
            "created_at": {"$lt": two_days_ago}
        }).to_list(50)
        for lr in overdue:
            await self.db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": "solvit",
                "recipient_role": "hr_admin",
                "rule_id": "AR-LV-02",
                "title": "Leave Request Unapproved — 2 Days",
                "message": f"Leave request submitted 2+ days ago has not been actioned by line manager",
                "is_read": False,
                "created_at": now.isoformat()
            })

    async def _check_anniversaries(self):
        """AR-RK-01 to AR-RK-04: Anniversary milestones"""
        now = datetime.now(timezone.utc)
        employees = await self.db.employees.find({
            "tenant_id": "solvit",
            "lifecycle_state": "Active"
        }).to_list(200)
        for emp in employees:
            start_date = emp.get("start_date")
            if not start_date:
                continue
            try:
                start_dt = datetime.fromisoformat(start_date)
                tenure_years = (now.replace(tzinfo=None) - start_dt).days / 365.25
                for milestone in [2, 3, 5, 7, 10]:
                    if abs(tenure_years - milestone) < 0.014:  # ~5 days window
                        existing = await self.db.notifications.find_one({
                            "tenant_id": "solvit",
                            "rule_id": f"AR-RK-0{milestone}",
                            "data.employee_id": str(emp.get("id", str(emp["_id"]))),
                            "created_at": {"$gte": (now - timedelta(days=7)).isoformat()}
                        })
                        if not existing:
                            await self.db.notifications.insert_one({
                                "id": str(uuid.uuid4()),
                                "tenant_id": "solvit",
                                "recipient_role": "hr_admin",
                                "rule_id": f"AR-RK",
                                "title": f"{milestone}-Year Anniversary: {emp.get('full_name')}",
                                "message": f"{emp.get('full_name')} celebrates {milestone} years at Solvit today! Plan their recognition.",
                                "data": {"employee_id": str(emp.get("id", str(emp["_id"])))},
                                "is_read": False,
                                "created_at": now.isoformat()
                            })
            except Exception as e:
                logger.error(f"Anniversary check error: {e}")

    async def _run_compliance_check(self):
        """Run compliance check every 4 hours"""
        if not self.db:
            return
        try:
            now = datetime.now(timezone.utc)
            month_day = now.day
            # NSSF/SHA deadline warnings
            if month_day in [8, 14]:
                days_to_deadline = 15 - month_day
                await self.db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": "solvit",
                    "recipient_role": "finance",
                    "rule_id": "AR-CP-01" if days_to_deadline == 7 else "AR-CP-02",
                    "title": f"NSSF/SHA Remittance Due in {days_to_deadline} Days",
                    "message": f"NSSF and SHA remittance is due on the 15th ({days_to_deadline} days remaining).",
                    "is_read": False,
                    "created_at": now.isoformat()
                })
            # PAYE deadline
            if month_day in [2, 8]:
                days_to_paye = 9 - month_day
                await self.db.notifications.insert_one({
                    "id": str(uuid.uuid4()),
                    "tenant_id": "solvit",
                    "recipient_role": "finance",
                    "rule_id": "AR-CP-03",
                    "title": f"PAYE Filing Due in {days_to_paye} Days",
                    "message": f"PAYE filing is due on the 9th ({days_to_paye} days remaining).",
                    "is_read": False,
                    "created_at": now.isoformat()
                })
        except Exception as e:
            logger.error(f"Compliance check error: {e}")


# Singleton
automation_engine = AutomationEngine()
