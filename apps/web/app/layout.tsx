import type { Metadata } from "next";
import "./globals.css";
import { currentRole } from "@/lib/auth";
export const metadata: Metadata = { title: "Thaazhai Operations", description: "Business operations" };
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const role = await currentRole();
  return <html lang="en"><body>
    {role === "viewer" && <div className="viewer-banner" role="status">
      <strong>View-only access</strong> Explore reports, orders and customers. Changes are reserved for administrators.
    </div>}
    {children}</body></html>;
}
