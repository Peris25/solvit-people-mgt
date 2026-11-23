"""One-time, explicitly approved Finance weight correction, with no notifications.

Runs only this fixed repair during deployment startup. A durable audit marker
prevents future startups from rewriting later HR amendments. No arbitrary input
or public mutation endpoint is exposed.
"""
import logging
from fastapi import HTTPException
from scripts.repair_grace_kpis import REPAIR_ID, prepare, fingerprint, apply

logger=logging.getLogger(__name__)


async def run(db):
    try:
        if await db.audit_logs.find_one({'_id':REPAIR_ID}): return 'applied'
        result=await apply(db,fingerprint(await prepare(db)))
        return 'applied' if result['status'] in {'corrected_and_verified','already_correct','already_applied'} else 'needs_review'
    except HTTPException:
        logger.warning('Approved Finance KPI correction needs operator review; no automatic retry.')
        return 'needs_review'
    except Exception as error:
        logger.error('Approved Finance KPI correction could not be confirmed (%s); inspect the repair audit before retrying.', type(error).__name__)
        return 'unconfirmed'
