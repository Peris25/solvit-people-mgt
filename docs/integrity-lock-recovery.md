# Controlled integrity-write recovery

There is deliberately no expiry, force-unlock API, scheduled cleaner or automatic
lock removal. A lock conflict/HTTP 409 is evidence of contention, not proof that
the owner crashed. Lock age and a missing PID on one host are insufficient: a
different replica may still be writing, and a timed-out MongoDB operation may
still be running on the server.

## Detection

The lock document has `_id: employee-account-writes`, a unique per-write `owner`,
`created_at`, a process-start `worker_instance` UUID and `process_id`. Compare
these with application/supervisor/container logs. Earlier locks may lack worker
metadata; that does not make them safe to remove.

Normal completion and known validation/duplicate-key rejection release only the
matching owner. Cancellation, network timeouts and unexpected exceptions retain
the lock because the write outcome is uncertain. Failure while acquiring or
releasing the lock can also be uncertain; inspect the database rather than
assuming the HTTP response proves no write happened.

## Operator procedure — separately authorized, never executed by the application

1. Confirm the intended cluster/database from deployment configuration. Obtain
   explicit authorization and open a maintenance window. Capture the exact lock
   document and relevant operation logs in a restricted incident artifact.
2. Stop **all** backend workers/replicas, automatic restarts/autoscaling,
   schedulers, importers, scripts and old deployments that can write employee or
   account data. Pause inbound mutations. Do not rely on a single host's PID.
3. Confirm shutdown on every instance and that no corresponding MongoDB
   operation remains active. Account for driver retries. If quiescence cannot be
   proved, do not unlock. Seek database/operator assistance.
4. Back up and reconcile the uncertain operation using read-only queries: it may
   have committed, partially completed a multi-document workflow, or failed.
   Check duplicate normalized identities, account links and manager cycles.
   Do not delete or merge employee/account records to repair a lock incident.
5. While writers remain stopped, remove only the captured lock using a
   compare-and-set filter. Include the captured `_id`, `owner`, `created_at` and
   `worker_instance` when present. For example, with placeholders only:

   ```javascript
   db.integrity_locks.deleteOne({
     _id: "employee-account-writes",
     owner: "<captured-owner>",
     created_at: "<captured-created-at>",
     worker_instance: "<captured-worker-instance>"
   })
   ```

   Require `deletedCount === 1`. A zero count means the snapshot no longer
   matches: stop and investigate; never fall back to deleting by `_id` alone.
   For an old document, match its captured fields and require missing worker
   metadata with `$exists: false` rather than inventing an instance identifier.
6. Record the incident, snapshot, reconciliation and removal result. Restart one
   writer, verify the lock is acquired/released normally, then restore the other
   approved workers. Run a read-only integrity audit before reopening mutations.

Only the lock collection is involved in removal. No employee/account deletion,
data migration or index installation is part of recovery. This procedure cannot
be safely reduced to an automated “stale lock” timer without transaction/fencing
changes and verified deployment-wide coordination.
