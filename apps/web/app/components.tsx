import Link from "next/link";
import { logout } from "./actions";

export type IconName = "dashboard" | "database" | "jobs" | "tag" | "bag" | "users" |
  "rupee" | "trend" | "repeat" | "package" | "calendar" | "spark" | "megaphone";

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    dashboard: <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="4" rx="2" /><rect x="14" y="11" width="7" height="10" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /></>,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5" /><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
    jobs: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    tag: <><path d="M20 13 13 20 4 11V4h7l9 9Z" /><circle cx="8.5" cy="8.5" r="1.2" /></>,
    bag: <><path d="M5 8h14l-1 13H6L5 8Z" /><path d="M9 9V6a3 3 0 0 1 6 0v3" /></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M22 21v-2a4 4 0 0 0-3-3.8M16 3.2a4 4 0 0 1 0 7.6" /></>,
    rupee: <><path d="M6 4h12M6 8h12M7 4c6 0 7 8 0 8h-1l8 8" /></>,
    trend: <><path d="m3 17 6-6 4 4 8-9" /><path d="M15 6h6v6" /></>,
    repeat: <><path d="m17 1 4 4-4 4" /><path d="M3 11V9a4 4 0 0 1 4-4h14M7 23l-4-4 4-4" /><path d="M21 13v2a4 4 0 0 1-4 4H3" /></>,
    package: <><path d="m12 2 9 5-9 5-9-5 9-5Z" /><path d="m3 7 9 5 9-5v10l-9 5-9-5V7Z" /><path d="M12 12v10" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    megaphone: <><path d="M3 11v2a1 1 0 0 0 1 1h3l7 5V5L7 10H4a1 1 0 0 0-1 1Z" /><path d="M18 8.5a5 5 0 0 1 0 7" /></>,
    spark: <><path d="m12 2 1.7 5.3L19 9l-5.3 1.7L12 16l-1.7-5.3L5 9l5.3-1.7L12 2Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></>,
  };
  return <svg className="icon" width={size} height={size} viewBox="0 0 24 24"
    fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
    strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export function Shell({ title, subtitle, children }: {
  title: string; subtitle?: string; children: React.ReactNode;
}) {
  const links: [string, string, IconName][] = [
    ["/", "Dashboard", "dashboard"], ["/ingestion", "Ingestion", "database"],
    ["/jobs", "Jobs", "jobs"], ["/mappings", "Mappings", "tag"],
    ["/orders", "Orders", "bag"], ["/customers", "Customers", "users"],
    ["/marketing", "Marketing", "megaphone"],
  ];
  return <div className="shell">
    <aside>
      <Link className="brand" href="/"><span className="brand-mark">T</span>
        <span className="brand-copy"><strong>thaazhai</strong><small>BUSINESS INTELLIGENCE</small></span>
      </Link>
      <div className="nav-label">Workspace</div>
      <nav>{links.map(([href, label, icon]) => <Link href={href} key={href}>
        <Icon name={icon} size={18} /><span>{label}</span></Link>)}</nav>
      <div className="sidebar-foot"><div className="environment"><i />
        <span><strong>{process.env.NEXT_PUBLIC_APP_ENV === "production"
          ? "Live environment" : "Local environment"}</strong>
          <small>PostgreSQL connected</small></span></div>
        <form action={logout}><button className="link-button">Sign out</button></form></div>
    </aside>
    <main className="content">
      <header><div><p className="eyebrow"><Icon name="spark" size={14} /> Executive workspace</p>
        <h1>{title}</h1>{subtitle && <p className="page-subtitle">{subtitle}</p>}</div>
        <span className="badge"><i /> {process.env.NEXT_PUBLIC_APP_ENV === "production"
          ? "Live business data" : "Local snapshot"}</span></header>
      {children}
    </main>
  </div>;
}

export function Money({ value, compact = false }: { value: string | number; compact?: boolean }) {
  const amount = Number(value);
  const rendered = compact && Math.abs(amount) >= 100000
    ? new Intl.NumberFormat("en-IN", { notation: "compact", maximumFractionDigits: 1 }).format(amount)
    : amount.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return <><span className="currency">{"\u20B9"}</span>{rendered}</>;
}

export function Status({ value }: { value: string }) {
  return <span className={`status-pill ${value.toLowerCase()}`}>{value}</span>;
}

export function Pager({ total, offset, limit, path, query = "" }: {
  total: number; offset: number; limit: number; path: string; query?: string;
}) {
  const previous = Math.max(0, offset - limit), next = offset + limit;
  const join = query ? "&" : "";
  return <div className="pager"><span>{total.toLocaleString()} records</span><div>
    {offset > 0 && <Link href={`${path}?${query}${join}offset=${previous}`}>Previous</Link>}
    {next < total && <Link href={`${path}?${query}${join}offset=${next}`}>Next</Link>}
  </div></div>;
}

export function SortLink({ label, column, current, direction, path, params = {} }: {
  label: string; column: string; current: string; direction: string; path: string;
  params?: Record<string, string>;
}) {
  const nextDirection = current === column && direction === "desc" ? "asc" : "desc";
  const query = new URLSearchParams(params);
  query.set("sort", column);
  query.set("direction", nextDirection);
  const active = current === column;
  return <Link className={`sort-link ${active ? "active" : ""}`}
    href={`${path}?${query.toString()}`}
    aria-label={`Sort by ${label} ${nextDirection === "asc" ? "ascending" : "descending"}`}>
    {label}<span aria-hidden="true">{active ? (direction === "asc" ? " \u2191" : " \u2193") : " \u2195"}</span>
  </Link>;
}
