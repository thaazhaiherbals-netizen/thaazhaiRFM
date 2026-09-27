const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");
const Module = require("node:module");
const filename = path.resolve(__dirname, "../lib/order-dates.ts");
const mod = new Module(filename);
mod._compile(ts.transpileModule(fs.readFileSync(filename, "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText, filename);
const { orderDateRange } = mod.exports;

test("today changes at India midnight, independent of UTC date", () => {
  assert.deepEqual(orderDateRange("today", new Date("2026-09-27T18:29:59Z")), { start: "2026-09-27", end: "2026-09-27" });
  assert.deepEqual(orderDateRange("today", new Date("2026-09-27T18:30:00Z")), { start: "2026-09-28", end: "2026-09-28" });
});
test("yesterday crosses year and leap-day boundaries", () => {
  assert.deepEqual(orderDateRange("yesterday", new Date("2026-01-01T00:00:00Z")), { start: "2025-12-31", end: "2025-12-31" });
  assert.deepEqual(orderDateRange("yesterday", new Date("2024-03-01T00:00:00Z")), { start: "2024-02-29", end: "2024-02-29" });
});
test("week starts Monday and month starts on the first, ending today", () => {
  assert.deepEqual(orderDateRange("week", new Date("2026-09-27T12:00:00Z")), { start: "2026-09-21", end: "2026-09-27" });
  assert.deepEqual(orderDateRange("week", new Date("2026-09-28T12:00:00Z")), { start: "2026-09-28", end: "2026-09-28" });
  assert.deepEqual(orderDateRange("month", new Date("2026-09-27T12:00:00Z")), { start: "2026-09-01", end: "2026-09-27" });
  assert.equal(orderDateRange("unsupported"), undefined);
});
