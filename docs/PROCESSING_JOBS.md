# Processing jobs (Phase 3)

Migration 008 adds processing_job_items: a fixed list of raw IDs for each job and
per-record outcome. This makes progress durable and bounds a job to the records
present when it was requested. New arrivals wait for the next job.
A partial unique index permits one QUEUED/RUNNING job at a time. Existing active
jobs must be inspected before applying this index to any existing deployment.

The worker uses a PostgreSQL session advisory lock to serialize workers and resumes
RUNNING jobs after a restart. Each item, normalized order, raw status and counters
commit in the same transaction; a crash rolls back that item. A lost DB connection
leaves the job recoverable. Individual record errors do not abort the job.
COMPLETED can contain failed records. FAILED is reserved for terminal job failures;
transient infrastructure errors remain RUNNING and are retried on later ticks.

No long processing runs inside an HTTP request. Admin endpoints require a secret
bearer token; unset credentials fail closed. Health endpoints remain public.

## How the new code is called

Swagger POST /admin/jobs/process-pending
  -> apps/api/admin.py: process_pending()
  -> apps/api/jobs.py: enqueue_job()
  -> inserts processing_jobs and processing_job_items; returns 202 immediately.

A separate container runs python -m workers.order_processor
  -> workers/order_processor/__main__.py polls every two seconds
  -> apps/api/jobs.py: run_next_job()
  -> apps/api/order_processing.py: process_single_order()
  -> commits one order and its job-item result/counters together.

The worker reads pending job items in batches of 50. A batch does not mean one
large transaction: each order gets its own transaction. Only one worker may drive
the queue at a time. There is no Redis or additional job broker.

## Use Swagger locally

1. Open http://localhost:8000/docs.
2. Copy ADMIN_API_TOKEN from the root .env.local file.
3. Click Authorize and paste only the token (HTTP Bearer adds the prefix).
4. GET /admin/ingestion/summary is a read-only way to verify access.
5. POST /admin/jobs/process-pending queues ALL currently NEW local raw records.
   It is a write operation: use it when ready to process the imported dataset.
6. Copy the returned id and call GET /admin/jobs/{job_id} to see progress.
7. GET /admin/jobs/{job_id}/items gives per-record outcomes.
8. GET /admin/errors lists raw processing errors.

The worker does not start processing merely because it is running; it needs a
QUEUED job. A second active-job request returns 409 instead of duplicating work.
The job membership is a snapshot: later arrivals wait for a new request.
Status COMPLETED means all selected records were attempted; check failed_count.

## Correct mappings through the API

GET /admin/unmapped-products lists pending item groups.
GET /admin/products supplies valid product and variant IDs.
POST /admin/product-aliases creates a confirmed mapping.
PUT /admin/product-aliases/{alias_id} corrects an existing alias.
DELETE /admin/product-aliases/{alias_id} deactivates it (no historical data deletion).
Ambiguous aliases need to be corrected/deactivated until exactly one active match exists.
POST /admin/jobs/resolve-mappings queues affected orders. Unresolved items count as
failed for this job type so incomplete corrections are visible. Existing sales,
prices and customers are preserved. Resolved historical items are not automatically
remapped after a later catalogue change.

POST /admin/ingestion/{ingestion_id}/retry retries one ERROR raw record.
POST /admin/jobs/retry-errors retries all currently ERROR records.
Successful pending-order processing can still leave product mappings pending;
use ingestion summary/unmapped-products to monitor that separate count.

## Running services

After explicit local migrations:
docker compose --env-file .env.local up -d --build api worker

Check: docker compose --env-file .env.local ps
Logs: docker compose --env-file .env.local logs --tail 50 worker
Restart after worker-code changes: docker compose --env-file .env.local restart worker

On a fresh checkout, set a long random ADMIN_API_TOKEN in .env.local first.
The local token was generated for this workspace without printing it. Rotate it by
editing .env.local and recreating the API container. It is not a Supabase key.
The V1 token is shared admin access, not individual user accounts; use HTTPS live.
Do not store it in NEXT_PUBLIC variables, screenshots, URLs, or Git.
Render now includes a worker service. Set the same live DATABASE_URL on API and
worker, and set ADMIN_API_TOKEN on the API. Use direct/session-pooler connections:
the worker's session advisory lock is not compatible with transaction pooling.
Review existing Supabase schema/history before applying migrations there.
No Render deployment or live migration is part of Phase 3 local setup.

## Limits

Infrastructure failures leave jobs RUNNING with pending items so a restart can
recover. Persistent infrastructure faults need investigation in worker logs.
No timeout-based takeover is used while a worker still owns the database lock.
Job status FAILED is reserved; current recoverable faults do not mark it terminal.
The worker may be terminated mid-job; already committed items remain completed.
The frontend operational pages, customer/order browser and analytics remain later phases.


## Phase 4 admin interface

The Next.js web server is the only browser-facing client. It calls FastAPI with
ADMIN_API_TOKEN from server-only environment variables; browser JavaScript never
receives the token. Users sign in with that token and receive an HTTP-only,
SameSite session cookie derived from ADMIN_UI_SESSION. This is shared V1 admin
access, not individual user accounts or role-based authorization.

Pages: Dashboard, Ingestion/errors, Processing jobs, Product mappings, Orders with
item detail, and Customers with order history. List pages are paginated; orders and
customers support server-side search. Forms call Next.js server actions, which call
protected FastAPI routes and then refresh affected pages.

Migration 009 introduces order_corrections. Missing dates can be corrected from the
Ingestion page with a confirmed date and reason. The processor reads that override
without modifying raw_payload. Only ERROR records can be corrected. Saving a date
queues a single-record retry unless another job is active.

Local web secrets live in apps/web/.env.local and are ignored by Git. For Render,
the web service needs API_URL, ADMIN_API_TOKEN, and ADMIN_UI_SESSION as private
variables. Rotate both admin secrets before live deployment and use HTTPS.
