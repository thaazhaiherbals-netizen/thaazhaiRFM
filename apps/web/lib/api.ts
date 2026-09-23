import "server-only";
import { requireAccess } from "./auth";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  await requireAccess(init?.method || "GET", path);
  const token = process.env.ADMIN_API_TOKEN;
  if (!token) throw new Error("ADMIN_API_TOKEN is not configured for the web server");
  const response = await fetch(API_URL + path, {
    ...init,
    cache: "no-store",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      // FastAPI validation errors arrive as a list of {loc, msg} objects.
      if (Array.isArray(body.detail)) {
        message = body.detail.map((item: { msg?: string }) =>
          String(item?.msg || "Invalid request").replace(/^Value error, /, "")).join("; ");
      } else if (typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {}
    throw new Error(message);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export type Page<T> = { items: T[]; total: number };
