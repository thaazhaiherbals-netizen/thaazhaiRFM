const { test, beforeEach, after } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const Module = require("node:module");
const root = path.resolve(__dirname, "..");
const originalEnv = { ...process.env };
let cookie, calls;
const response = {
  json: (body, init) => ({ body, status: init?.status || 200 }),
  redirect: (url, status = 307) => ({ url: String(url), status, cookies: {
    delete() {}, set(name, value, options) { this.value = value; this.options = options; },
  }}),
  next: () => ({ status: 200 }),
};
function load(file, cache = new Map()) {
  const full = path.resolve(root, file);
  if (cache.has(full)) return cache.get(full).exports;
  const mod = new Module(full); cache.set(full, mod);
  mod.filename = full;
  mod.paths = Module._nodeModulePaths(path.dirname(full));
  const base = mod.require.bind(mod);
  mod.require = id => {
    if (id === "server-only") return {};
    if (id === "next/headers") return { cookies: async () => ({ get: () => cookie ? { value: cookie } : undefined, delete() { cookie = undefined; } }) };
    if (id === "next/server") return { NextResponse: response };
    if (id === "next/navigation") return { redirect: () => {} };
    if (id === "next/cache") return { revalidatePath: () => {} };
    if (id.startsWith("@/") || id.startsWith(".")) {
      const target = id.startsWith("@/") ? path.join(root, id.slice(2)) : path.resolve(path.dirname(full), id);
      return load(target + ".ts", cache);
    }
    return base(id);
  };
  const code = ts.transpileModule(fs.readFileSync(full, "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  mod._compile(code, full);
  return mod.exports;
}
const session = load("lib/session.ts");
beforeEach(() => {
  process.env.ADMIN_API_TOKEN = "test-admin-code";
  process.env.VIEWER_UI_TOKEN = "test-viewer-code";
  process.env.ADMIN_UI_SESSION = "test-signing-secret";
  process.env.APP_URL = "https://example.test";
  cookie = undefined; calls = [];
});
after(() => { process.env = originalEnv; });
test("login separates roles, rejects missing, unicode and identical credentials", () => {
  assert.equal(session.loginRole("test-admin-code"), "admin");
  assert.equal(session.loginRole("test-viewer-code"), "viewer");
  assert.equal(session.loginRole(""), null);
  assert.equal(session.loginRole("é".repeat(15)), null);
  process.env.VIEWER_UI_TOKEN = process.env.ADMIN_API_TOKEN;
  assert.equal(session.loginRole("test-admin-code"), null);
});
test("sessions expire and cannot be changed from viewer to admin", () => {
  const value = session.createSession("viewer", 1000);
  assert.equal(session.sessionRole(value, 1000), "viewer");
  assert.equal(session.sessionRole(value.replace("viewer", "admin"), 1000), null);
  assert.equal(session.sessionRole(value + "x", 1000), null);
  assert.equal(session.sessionRole(value, 1000 + session.SESSION_SECONDS * 1000), null);
  assert.equal(session.sessionRole("old-admin-cookie"), null);
});
test("code rotation and missing configuration revoke sessions", () => {
  const value = session.createSession("viewer");
  process.env.VIEWER_UI_TOKEN = "replacement";
  assert.equal(session.sessionRole(value), null);
  delete process.env.VIEWER_UI_TOKEN;
  assert.equal(session.sessionRole(value), null);
  delete process.env.ADMIN_UI_SESSION;
  assert.throws(() => session.createSession("admin"));
});
test("API data layer blocks unauthenticated reads and every viewer write before fetch", async () => {
  const api = load("lib/api.ts").api;
  const originalFetch = global.fetch;
  global.fetch = async (...args) => { calls.push(args); return Response.json({ ok: true }); };
  try {
    await assert.rejects(api("/customers"), /sign in/);
    cookie = session.createSession("viewer");
    await api("/customers");
    for (const method of ["POST", "PUT", "PATCH", "DELETE", "post"]) {
      await assert.rejects(api("/admin/customer-segment-settings", { method }), /read-only/);
    }
    assert.equal(calls.length, 1);
    cookie = session.createSession("admin");
    await api("/admin/customer-segment-settings", { method: "PUT" });
    assert.equal(calls.length, 2);
  } finally { global.fetch = originalFetch; }
});
test("all Server Actions reject viewer writes even if proxy is bypassed; logout works", async () => {
  cookie = session.createSession("viewer");
  const actions = load("app/actions.ts");
  for (const name of ["startJob", "retryOrder", "correctDate", "saveMapping", "saveSegmentSettings"])
    await assert.rejects(actions[name](new FormData()), /read-only/);
  await actions.logout();
  assert.equal(cookie, undefined);
});
test("follow-up route returns 403 directly without reading body or calling API", async () => {
  cookie = session.createSession("viewer");
  const route = load("app/api/customers/[id]/follow-ups/route.ts");
  const result = await route.POST({ json() { throw Error("must not read body"); } }, { params: Promise.resolve({ id: "customer" }) });
  assert.equal(result.status, 403);
  cookie = undefined;
  assert.equal((await route.POST({}, {})).status, 401);
});
test("proxy allows viewer pages and GET details, rejects API writes and anonymous access", () => {
  const { proxy } = load("proxy.ts");
  const request = (pathname, method = "GET") => ({
    nextUrl: { pathname }, url: "http://0.0.0.0:8080" + pathname, method,
    cookies: { get: () => cookie ? { value: cookie } : undefined },
  });
  assert.equal(proxy(request("/api/customers/id")).status, 401);
  assert.equal(proxy(request("/customers")).url, "https://example.test/login");
  cookie = session.createSession("viewer");
  for (const page of ["/", "/customers", "/orders", "/ingestion", "/jobs", "/mappings", "/api/customers/id"])
    assert.equal(proxy(request(page)).status, 200);
  assert.equal(proxy(request("/api/customers/id/follow-ups", "POST")).status, 403);
});
test("viewer login sets a secure expiring cookie and redirects to public APP_URL", async () => {
  process.env.NODE_ENV = "production";
  const route = load("app/api/login/route.ts");
  const data = new FormData(); data.set("token", "test-viewer-code");
  const result = await route.POST({ formData: async () => data, nextUrl: { origin: "http://0.0.0.0:8080" } });
  assert.equal(result.url, "https://example.test/");
  assert.equal(result.status, 303);
  assert.equal(session.sessionRole(result.cookies.value), "viewer");
  assert.equal(result.cookies.options.httpOnly, true);
  assert.equal(result.cookies.options.secure, true);
  assert.equal(result.cookies.options.sameSite, "strict");
});
