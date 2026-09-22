import { createHmac, timingSafeEqual } from "crypto";

export type Role = "admin" | "viewer";
export const SESSION_COOKIE = "thaazhai_session";
export const SESSION_SECONDS = 8 * 60 * 60;

export function equalSecret(a: string, b: string): boolean {
  const left = Buffer.from(a), right = Buffer.from(b);
  return left.length > 0 && left.length === right.length && timingSafeEqual(left, right);
}

export function loginRole(token: string): Role | null {
  const admin = process.env.ADMIN_API_TOKEN || "";
  const viewer = process.env.VIEWER_UI_TOKEN || "";
  // A viewer code must never double as an administrator credential.
  if (viewer && equalSecret(admin, viewer)) return null;
  if (equalSecret(token, admin)) return "admin";
  if (equalSecret(token, viewer)) return "viewer";
  return null;
}

function signature(payload: string, role: Role): string {
  const secret = process.env.ADMIN_UI_SESSION;
  const credential = role === "admin" ? process.env.ADMIN_API_TOKEN : process.env.VIEWER_UI_TOKEN;
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
  if (role !== "admin" && role !== "viewer") return null;
  if (!/^\d+$/.test(expires) || Number(expires) <= Math.floor(now / 1000)) return null;
  if (equalSecret(process.env.ADMIN_API_TOKEN || "", process.env.VIEWER_UI_TOKEN || "")) return null;
  try { return equalSecret(supplied, signature(`${role}.${expires}`, role)) ? role : null; }
  catch { return null; }
}

export function accessStatus(role: Role | null, method = "GET"): 200 | 401 | 403 {
  if (!role) return 401;
  return role === "admin" || ["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase()) ? 200 : 403;
}
