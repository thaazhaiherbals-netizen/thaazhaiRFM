import { NextRequest, NextResponse } from "next/server";
import { createSession, loginRole, SESSION_COOKIE, SESSION_SECONDS } from "@/lib/session";
export async function POST(request: NextRequest) {
  const data = await request.formData();
  const role = loginRole(String(data.get("token") || ""));
  const appUrl = process.env.APP_URL || request.nextUrl.origin;
  if (!role) return NextResponse.redirect(new URL("/login?error=1", appUrl), 303);
  if (!process.env.ADMIN_UI_SESSION)
    return NextResponse.json({ error: "UI session is not configured" }, { status: 503 });
  const response = NextResponse.redirect(new URL(role === "support" ? "/customers" : "/", appUrl), 303);
  response.cookies.delete("thaazhai_admin");
  response.cookies.set(SESSION_COOKIE, createSession(role), {
    httpOnly: true, sameSite: "strict", secure: process.env.NODE_ENV === "production",
    path: "/", maxAge: SESSION_SECONDS,
  });
  return response;
}
