# Team viewer access

The web app supports two access codes on the same login page:
- `ADMIN_API_TOKEN`: administrator; can view and change data.
- `VIEWER_UI_TOKEN`: viewer; can browse all reports, customers, orders, ingestion status, mappings and jobs, including existing follow-up history. Cannot record calls, change group rules, correct orders, map products or start jobs.

## Railway rollout
1. Generate a new long random code (for example, locally: `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. Add `VIEWER_UI_TOKEN` to **thaazhai-web** variables only. Use a different value from `ADMIN_API_TOKEN`. Do not use a NEXT_PUBLIC prefix.
3. Keep existing `ADMIN_UI_SESSION`, `ADMIN_API_TOKEN`, `API_URL` and `APP_URL`. APP_URL is the public HTTPS web address.
4. Commit/push the code and deploy the web service. No database migration, seed, API or worker changes are needed.
5. Existing sessions must sign in again after this upgrade. Check admin login, then use a private browser window to sign in with the viewer code.
6. Confirm reports/search/filters/order drill-down and follow-up history work. Viewers see a banner and no write controls.
7. Share only the web URL and viewer code with the team. Do not share the admin code.

## Enforcement and limitations
Signed, HTTP-only cookies carry a role and an eight-hour expiry checked on the server. Changing/removing VIEWER_UI_TOKEN revokes viewer sessions on subsequent requests after the web service restarts. Changing ADMIN_UI_SESSION revokes all sessions.

The proxy checks access to pages and routes. The server API helper independently validates every session and blocks all viewer mutations before forwarding any request with the server-only admin credential. Each mutation Server Action and the follow-up route also checks authorization. Logout is available to either role.

The Python API retains its existing admin bearer-token protection; the viewer code is a website credential, not an API token. The worker runs independently and can continue processing incoming orders while viewers browse.

This is shared team viewer access, not individual accounts or per-person audit logging. All permitted customer information remains visible to viewers.

## Local verification
For the current local setup, add VIEWER_UI_TOKEN to apps/web/.env.local and restart Next.js. The root .env.local is used by the backend and is not automatically read by Next.js. Never commit a real code.
Run `npm --prefix apps/web run test:auth`, `npm --prefix apps/web run typecheck`, and `npm --prefix apps/web run build`.
After a build, run `npm --prefix apps/web run test:viewer` for an isolated production HTTP smoke test using an in-memory API fixture; it never uses real credentials or a database.

Auth tests exercise the actual session code, proxy, API data layer, Server Actions and follow-up route with request/transport mocks; they never connect to Supabase.
