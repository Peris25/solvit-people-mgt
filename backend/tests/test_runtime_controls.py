"""Deployment switches: synthetic fixtures, mocked transports, no live services."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from copy import deepcopy
import pytest

from automation import engine as automation
from reminders import engine as reminders
from routes import email_delivery
from utils import email_service, runtime_controls
from .integrity_fakes import Database, Collection, employee


def run(awaitable):
    return asyncio.run(awaitable)


@pytest.fixture(autouse=True)
def explicit_default_environment(monkeypatch):
    monkeypatch.delenv("ENABLE_BACKGROUND_JOBS", raising=False)
    monkeypatch.delenv("OUTBOUND_EMAIL_ENABLED", raising=False)
    monkeypatch.setattr(email_service,"_MIN_INTERVAL_S",0)


@pytest.mark.parametrize("name",["ENABLE_BACKGROUND_JOBS","OUTBOUND_EMAIL_ENABLED"])
@pytest.mark.parametrize("value,expected",[(None,True),("true",True),(" YES ",True),("1",True),("false",False),(" FALSE ",False),("0",False),("off",False),("",False),("invalid",False)])
def test_switch_defaults_and_fail_closed_parsing(monkeypatch,name,value,expected):
    if value is not None: monkeypatch.setenv(name,value)
    check=runtime_controls.background_jobs_enabled if name=="ENABLE_BACKGROUND_JOBS" else runtime_controls.outbound_email_enabled
    assert check() is expected


def database():
    db=Database([employee()])
    for name in ["automation_rules","notifications","email_log","email_retry_queue","email_templates","masters_settings"]:
        setattr(db,name,Collection())
    config={"smtp_host":"smtp.example.invalid","smtp_port":587,"password":"synthetic-mail-password","from_email":"sender@example.com","encryption":"STARTTLS"}
    db.email_delivery_config=Collection([{"tenant_id":"solvit","active_mode":"testing","testing":{**config},"production":{**config}}])
    return db


def reminder_setup(engine):
    engine._ensure_config=AsyncMock();engine._ensure_indexes=AsyncMock()
    engine.get_config=AsyncMock(return_value={**reminders.DEFAULT_CONFIG})


@pytest.mark.parametrize("enabled",[False,True])
def test_both_engines_start_with_default_production_or_explicit_disabled(monkeypatch,enabled):
    if not enabled:monkeypatch.setenv("ENABLE_BACKGROUND_JOBS","false")
    db=database();auto=automation.AutomationEngine();rem=reminders.ReminderEngine();reminder_setup(rem)
    with patch.object(automation,"AsyncIOScheduler") as auto_scheduler,patch.object(reminders,"AsyncIOScheduler") as rem_scheduler:
        run(auto.start(db));run(rem.start(db))
    assert auto.db is db and rem.db is db
    if enabled:
        auto_scheduler.return_value.start.assert_called_once();rem_scheduler.return_value.start.assert_called_once()
        assert auto_scheduler.return_value.add_job.call_count==5
        assert rem_scheduler.return_value.add_job.call_count==len(reminders.RULES)
    else:
        auto_scheduler.assert_not_called();rem_scheduler.assert_not_called()
        assert auto.scheduler is None and rem.scheduler is None
        assert not auto._started and not rem._started
    rem._ensure_indexes.assert_awaited_once()


def test_disabled_schedule_cannot_be_reenabled_by_saved_settings(monkeypatch):
    monkeypatch.setenv("ENABLE_BACKGROUND_JOBS","false")
    rem=reminders.ReminderEngine();rem.db=database();rem.scheduler=MagicMock();rem.scheduler.running=True
    rem.scheduler.get_jobs.return_value=[SimpleNamespace(id="old-job")]
    run(rem.update_config({"master_enabled":True}))
    rem.scheduler.remove_job.assert_called_once_with("old-job")
    rem.scheduler.remove_all_jobs.assert_called_once();rem.scheduler.pause.assert_called_once()
    rem.scheduler.add_job.assert_not_called();rem.scheduler.start.assert_not_called()


def test_default_settings_updates_still_register_reminders():
    rem=reminders.ReminderEngine();rem.db=database();rem.scheduler=MagicMock()
    rem.scheduler.get_jobs.return_value=[]
    run(rem.update_config({"master_enabled":True}))
    assert rem.scheduler.add_job.call_count==len(reminders.RULES)


def test_disabled_scheduled_callbacks_do_not_process_records_or_send(monkeypatch):
    monkeypatch.setenv("ENABLE_BACKGROUND_JOBS","false")
    auto=automation.AutomationEngine();auto.db=MagicMock()
    rem=reminders.ReminderEngine();rem.run_rule=AsyncMock()
    with patch("utils.lifecycle_workflows.process_approved_exits",AsyncMock()) as exits,patch.object(email_service,"process_retry_queue",AsyncMock()) as retries:
        for name in ["_run_daily_cron","_run_compliance_check","_check_anniversaries","_process_approved_exits","_process_email_retries"]:
            run(getattr(auto,name)())
        run(rem._run_rule_job("synthetic-rule"))
    exits.assert_not_called();retries.assert_not_called();rem.run_rule.assert_not_called()
    assert not auto.db.mock_calls


def test_disabled_background_jobs_preserve_real_event_form_outcomes_and_notifications(monkeypatch):
    monkeypatch.setenv("ENABLE_BACKGROUND_JOBS","false")
    db=database();auto=automation.AutomationEngine()
    monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED","false")
    rule={"tenant_id":"solvit","trigger_type":"event","trigger_event":"idp.signed","is_active":True,
          "rule_id":"synthetic-rule","action_type":"send_notification","notification_recipients_json":["employee"]}
    run(db.automation_rules.insert_one(rule))
    run(db.users.insert_one({"role":"employee","email":"staff@example.com","tenant_id":"solvit"}))
    with patch.object(email_service,"_attempt_send",AsyncMock()) as smtp:
        run(auto.start(db));run(auto.fire_event("idp.signed",{"employee_id":"staff"}))
    assert db.employees.docs[0]["flags.idp_active"] is True
    assert db.audit_logs.docs[0]["action"]=="form.outcome.fired"
    assert db.notifications.docs[0]["recipient_id"]=="staff"
    assert db.automation_rules.docs[0]["last_execution_status"]=="success"
    assert db.email_log.docs[0]["status"]=="skipped"
    smtp.assert_not_called()



@pytest.mark.parametrize("template",[None,*sorted(email_service.FORMAL_TEMPLATE_KEYS)])
def test_disabled_email_short_circuits_normal_and_every_formal_template(monkeypatch,template):
    monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED","false");db=database()
    db.email_delivery_config.find_one=AsyncMock(side_effect=AssertionError("No credential lookup while disabled"))
    with patch.object(email_service,"_attempt_send",AsyncMock()) as smtp,patch.object(email_service,"_attempt_send_sender_net",AsyncMock()) as sender:
        result=run(email_service.send_email(db,"recipient@example.com",subject="Synthetic",html="Synthetic",template_key=template))
    assert result["status"]=="skipped" and result["reason"]=="outbound_email_disabled"
    smtp.assert_not_called();sender.assert_not_called();db.email_delivery_config.find_one.assert_not_called()
    assert not db.email_retry_queue.docs
    assert db.email_log.docs[0]["status"]=="skipped" and db.email_log.docs[0]["to"] is None


def test_disabled_transports_block_connections_even_if_called_directly(monkeypatch):
    monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED","false")
    with patch.object(email_service.smtplib,"SMTP") as smtp,patch.object(email_service.smtplib,"SMTP_SSL") as ssl,patch("httpx.AsyncClient") as http:
        for encryption in ["SSL","STARTTLS",""]:
            with pytest.raises(runtime_controls.OutboundEmailDisabled):
                run(email_service._attempt_send("smtp.example.invalid",587,encryption,"","synthetic","from@example.com","Synthetic sender","to@example.com",MagicMock()))
        with pytest.raises(runtime_controls.OutboundEmailDisabled):
            run(email_service._attempt_send_sender_net("synthetic","from@example.com","Synthetic","to@example.com","Synthetic","Synthetic","Synthetic"))
    smtp.assert_not_called();ssl.assert_not_called();http.assert_not_called()


@pytest.mark.parametrize("provider",["smtp","sender_net"])
def test_disabled_test_email_cannot_bypass_switch(monkeypatch,provider):
    monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED","false");db=database();db.email_delivery_config.docs[0]["testing"]["provider"]=provider
    request=SimpleNamespace(json=AsyncMock(return_value={"to":"recipient@example.com"}))
    with patch.object(email_delivery,"get_db",return_value=db),patch.object(email_delivery,"get_current_user",AsyncMock(return_value={"role":"it_admin"})),patch.object(email_delivery.smtplib,"SMTP") as smtp,patch.object(email_delivery.smtplib,"SMTP_SSL") as ssl,patch("httpx.post") as http:
        result=run(email_delivery.test_send(request))
    assert result["reason"]=="outbound_email_disabled"
    smtp.assert_not_called();ssl.assert_not_called();http.assert_not_called();request.json.assert_not_called()


def test_disabled_email_retry_queue_is_not_claimed_or_changed(monkeypatch):
    monkeypatch.setenv("OUTBOUND_EMAIL_ENABLED","false");db=database()
    db.email_retry_queue.docs=[{"id":"retry","status":"pending","next_attempt_at":"2020-01-01","tenant_id":"solvit"}]
    before=deepcopy(db.email_retry_queue.docs)
    with patch.object(email_service,"send_email",AsyncMock()) as send:
        assert run(email_service.process_retry_queue(db))==0
    send.assert_not_called();assert db.email_retry_queue.docs==before and db.email_retry_queue.writes==0


@pytest.mark.parametrize("provider,template",[("smtp",None),("sender_net",None),("smtp","recruitment.offer")])
def test_unset_email_flag_preserves_delivery_and_formal_override(provider,template):
    db=database();db.email_delivery_config.docs[0]["testing"].update(provider=provider,api_key="synthetic-provider-key")
    with patch.object(email_service,"_attempt_send",AsyncMock()) as smtp,patch.object(email_service,"_attempt_send_sender_net",AsyncMock()) as sender:
        result=run(email_service.send_email(db,"recipient@example.com",subject="Synthetic",html="Synthetic",template_key=template))
    assert result["status"]=="sent"
    assert result["mode"]==("production" if template else "testing")
    assert smtp.await_count==(1 if provider=="smtp" else 0)
    assert sender.await_count==(1 if provider=="sender_net" else 0)


@pytest.mark.parametrize("provider",["smtp","sender_net"])
def test_unset_email_flag_preserves_actual_transport_selection(provider):
    import httpx
    if provider=="smtp":
        with patch.object(email_service.smtplib,"SMTP_SSL") as smtp:
            run(email_service._attempt_send("smtp.example.invalid",465,"SSL","user","synthetic","from@example.com","Synthetic sender","to@example.com",MagicMock()))
        smtp.return_value.sendmail.assert_called_once()
    else:
        client=AsyncMock();client.post.return_value=SimpleNamespace(status_code=200)
        with patch.object(httpx,"AsyncClient") as http:
            http.return_value.__aenter__.return_value=client
            run(email_service._attempt_send_sender_net("synthetic","from@example.com","Synthetic","to@example.com","Synthetic","Synthetic","Synthetic"))
        client.post.assert_awaited_once()


def test_transport_policy_race_is_suppressed_without_retry():
    db=database()
    with patch.object(email_service,"_attempt_send",AsyncMock(side_effect=runtime_controls.OutboundEmailDisabled("Disabled"))):
        result=run(email_service.send_email(db,"recipient@example.com",subject="Synthetic",html="Synthetic"))
    assert result["reason"]=="outbound_email_disabled" and not db.email_retry_queue.docs


@pytest.mark.parametrize("provider",["smtp","sender_net"])
def test_unset_flag_preserves_test_email_endpoint(provider):
    db=database();db.email_delivery_config.docs[0]["testing"].update(provider=provider,api_key="synthetic-provider-key")
    request=SimpleNamespace(json=AsyncMock(return_value={"to":"recipient@example.com"}))
    with patch.object(email_delivery,"get_db",return_value=db),patch.object(email_delivery,"get_current_user",AsyncMock(return_value={"role":"it_admin","id":"operator"})),patch.object(email_delivery.smtplib,"SMTP") as smtp,patch("httpx.post",return_value=SimpleNamespace(status_code=200)) as http:
        result=run(email_delivery.test_send(request))
    assert result["status"]=="Success"
    if provider=="smtp":smtp.return_value.sendmail.assert_called_once();http.assert_not_called()
    else:http.assert_called_once();smtp.assert_not_called()


@pytest.mark.parametrize("suppressed",[False,True])
def test_default_retry_processing_and_midflight_suppression_preserve_state(suppressed):
    db=database()
    run(db.email_retry_queue.insert_one({"tenant_id":"solvit","status":"pending","next_attempt_at":"2020-01-01","to":"recipient@example.com","subject":"Synthetic","html":"Synthetic","retry_count":0}))
    result={"status":"skipped","reason":"outbound_email_disabled"} if suppressed else {"status":"sent"}
    with patch.object(email_service,"send_email",AsyncMock(return_value=result)):
        processed=run(email_service.process_retry_queue(db))
    row=db.email_retry_queue.docs[0]
    assert row["status"]==("pending" if suppressed else "sent")
    assert processed==(0 if suppressed else 1)
    if suppressed:assert "completed_at" not in row and row["retry_count"]==0


def test_application_startup_respects_switch_without_losing_engine_initialization(monkeypatch):
    import server
    monkeypatch.setenv("ENABLE_BACKGROUND_JOBS","false");monkeypatch.setenv("SEED_DEMO","false")
    db=database()
    for name in ["users","employees","solvers","notifications","tasks","audit_logs","revoked_refresh_tokens","user_session_invalidations"]:
        if not hasattr(db,name):setattr(db,name,Collection())
        getattr(db,name).create_index=AsyncMock()
    auto=automation.AutomationEngine();rem=reminders.ReminderEngine();reminder_setup(rem)
    with patch.object(server,"init_db",AsyncMock(return_value=db)),patch.object(server,"automation_engine",auto),patch.object(server,"reminder_engine",rem),patch("utils.access_matrix.load_runtime_state",AsyncMock()),patch.object(automation,"AsyncIOScheduler") as auto_scheduler,patch.object(reminders,"AsyncIOScheduler") as rem_scheduler:
        run(server.startup())
    auto_scheduler.assert_not_called();rem_scheduler.assert_not_called()
    assert auto.db is db and rem.db is db
