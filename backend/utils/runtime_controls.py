"""Deployment safety switches. Unset preserves production; invalid fails closed."""
import logging
import os

logger = logging.getLogger(__name__)


def _enabled(name):
    value = os.environ.get(name)
    if value is None:
        return True
    value = value.strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value not in {"false", "0", "no", "off"}:
        logger.warning("Invalid %s setting; functionality disabled", name)
    return False


def background_jobs_enabled():
    return _enabled("ENABLE_BACKGROUND_JOBS")


def outbound_email_enabled():
    return _enabled("OUTBOUND_EMAIL_ENABLED")


def pause_scheduled_jobs(scheduler):
    if scheduler is not None:
        scheduler.remove_all_jobs()
        if scheduler.running:
            scheduler.pause()


class OutboundEmailDisabled(RuntimeError):
    pass


def require_outbound_email():
    if not outbound_email_enabled():
        raise OutboundEmailDisabled("Outbound email is disabled by deployment policy")
