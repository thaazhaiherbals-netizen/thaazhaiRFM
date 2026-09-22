import { createHash, timingSafeEqual } from "crypto";
import { NextRequest, NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname;
  if (path.startsWith("/login") || path.startsWith("/api/login") || path.startsWith("/_next") || path === "/favicon.ico") {
    return NextResponse.next();
  }
  const secret = process.env.ADMIN_UI_SESSION || "";
  const expected = createHash("sha256").update(secret).digest("hex");
  const supplied = request.cookies.get("thaazhai_admin")?.value || "";
  const valid = secret && supplied.length === expected.length &&
    timingSafeEqual(Buffer.from(supplied), Buffer.from(expected));
  if (!valid) return NextResponse.redirect(new URL("/login", request.url));
  return NextResponse.next();
}

export const config = { matcher: ["/((?!_next/static|_next/image).*)"] };
