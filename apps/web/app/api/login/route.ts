import { createHash, timingSafeEqual } from "crypto";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const data = await request.formData();
  const supplied = String(data.get("token") || "");
  const expected = process.env.ADMIN_API_TOKEN || "";

  // In Railway, use the public website address for redirects.
  const appUrl = process.env.APP_URL || request.nextUrl.origin;

  const valid =
    supplied.length === expected.length &&
    timingSafeEqual(Buffer.from(supplied), Buffer.from(expected));

  if (!valid || !expected) {
    return NextResponse.redirect(new URL("/login?error=1", appUrl), 303);
  }

  const session = process.env.ADMIN_UI_SESSION || "";

  if (!session) {
    return NextResponse.json(
      { error: "UI session is not configured" },
      { status: 503 }
    );
  }

  const response = NextResponse.redirect(new URL("/", appUrl), 303);

  response.cookies.set(
    "thaazhai_admin",
    createHash("sha256").update(session).digest("hex"),
    {
      httpOnly: true,
      sameSite: "strict",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 60 * 60 * 8,
    }
  );

  return response;
}