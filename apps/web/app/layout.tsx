import type { Metadata } from "next";
import "./globals.css";
import { currentRole } from "@/lib/auth";
export const metadata: Metadata = { title: "Thaazhai Operations", description: "Business operations" };
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const role = await currentRole();
  return <html lang="en"><body>
    {role === "support" && <div className="viewer-banner" role="status">
      <strong>Customer support access</strong> View customers and order details, and record follow-ups.
    </div>}
    {role === "viewer" && <div className="viewer-banner" role="status">
      <strong>View-only access</strong> Explore reports, orders and customers. Changes are reserved for administrators.
    </div>}
    {children}</body></html>;
}
