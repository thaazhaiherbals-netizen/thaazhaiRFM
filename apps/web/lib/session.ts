import { createHmac, timingSafeEqual } from "crypto";

export type Role = "admin" | "viewer" | "support";
export const SESSION_COOKIE = "thaazhai_session";
export const SESSION_SECONDS = 8 * 60 * 60;

export function equalSecret(a: string, b: string): boolean {
  const left = Buffer.from(a), right = Buffer.from(b);
  return left.length > 0 && left.length === right.length && timingSafeEqual(left, right);
}

export function loginRole(token: string): Role | null {
  const admin = process.env.ADMIN_API_TOKEN || "";
  const viewer = process.env.VIEWER_UI_TOKEN || "";
  const support = process.env.SUPPORT_UI_TOKEN || "";
  if (credentialsOverlap()) return null;
  if (equalSecret(token, admin)) return "admin";
  if (equalSecret(token, viewer)) return "viewer";
  if (equalSecret(token, support)) return "support";
  return null;
}

function credentialsOverlap(): boolean {
  const codes = [process.env.ADMIN_API_TOKEN, process.env.VIEWER_UI_TOKEN, process.env.SUPPORT_UI_TOKEN].filter(Boolean) as string[];
  return codes.some((code, index) => codes.slice(index + 1).some(other => equalSecret(code, other)));
}

function signature(payload: string, role: Role): string {
  const secret = process.env.ADMIN_UI_SESSION;
  const credential = role === "admin" ? process.env.ADMIN_API_TOKEN
    : role === "support" ? process.env.SUPPORT_UI_TOKEN : process.env.VIEWER_UI_TOKEN;
  if (!secret || !credential) throw new Error("Access is not configured");
  return createHmac("sha256", secret).update(`${payload}:${credential}`).digest("hex");
}

export function createSession(role: Role, now = Date.now()): string {
  const payload = `${role}.${Math.floor(now / 1000) + SESSION_SECONDS}`;
  return `${payload}.${signature(payload, role)}`;
}

export function sessionRole(value: string | undefined, now = Date.now()): Role | null {
  const parts = (value || "").split(".");
  if (parts.length !== 3) return null;
  const [role, expires, supplied] = parts;
  if (role !== "admin" && role !== "viewer" && role !== "support") return null;
  if (!/^\d+$/.test(expires) || Number(expires) <= Math.floor(now / 1000)) return null;
  if (credentialsOverlap()) return null;
  try { return equalSecret(supplied, signature(`${role}.${expires}`, role)) ? role : null; }
  catch { return null; }
}

export function accessStatus(role: Role | null, method = "GET", path = ""): 200 | 401 | 403 {
  if (!role) return 401;
  if (role === "support") {
    const route = path.split("?")[0];
    const read = ["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase());
    if (read && (/^\/(?:api\/)?customers(?:\/[a-zA-Z0-9_-]+)?$/.test(route)
      || /^\/(?:api\/)?orders\/[a-zA-Z0-9_-]+$/.test(route)
      || route === "/admin/customer-segments")) return 200;
    if (method.toUpperCase() === "POST"
      && /^\/(?:admin|api)\/customers\/[a-zA-Z0-9_-]+\/follow-ups$/.test(route)) return 200;
    return 403;
  }
  return role === "admin" || ["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase()) ? 200 : 403;
}
