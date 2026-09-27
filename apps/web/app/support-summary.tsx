import { api } from "@/lib/api";

export async function SupportSummary() {
  const data = await api<{ today: string; contacted: number; positive: number;
    negative: number; scheduled: number }>("/admin/support-summary");
  return <section className="support-overview" aria-label="Today's customer support activity">
    <h2>Customer support today</h2>
    <p>{data.today} · India time · Across all customers and team members</p>
    <div className="support-metrics">
      {[["People contacted", data.contacted, "Unique customers reached; excludes unanswered calls"],
        ["Positive feedback", data.positive, "Conversations marked positive today"],
        ["Negative feedback", data.negative, "Conversations marked negative today"],
        ["Scheduled for today", data.scheduled, "Customers whose latest follow-up is due today"]
      ].map(([label, value, hint]) => <article className="metric" key={label}>
        <span>{label}</span><strong>{Number(value).toLocaleString("en-IN")}</strong>
        <small>{hint}</small>
      </article>)}
    </div>
  </section>;
}
