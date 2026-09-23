import "server-only";
import { cookies } from "next/headers";
import { accessStatus, SESSION_COOKIE, sessionRole } from "./session";

export async function currentRole() {
  return sessionRole((await cookies()).get(SESSION_COOKIE)?.value);
}

export async function requireAccess(method = "GET", path = "") {
  const role = await currentRole();
  const status = accessStatus(role, method, path);
  if (status !== 200) throw new Error(status === 401 ? "Please sign in" : role === "viewer" ? "Viewer access is read-only" : "Administrator access required");
  return role;
}
