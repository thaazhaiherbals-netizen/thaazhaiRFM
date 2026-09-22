import { currentRole } from "@/lib/auth";
import { api, Page } from "@/lib/api";
import { Icon, Pager, Shell, SortLink, Status } from "../components";
import { correctDate, retryOrder, startJob } from "../actions";

type Row = { id: string; source_record_id: string; source_system: string; status: string;
  retry_count: number; ingested_at: string; processed_at?: string; error_message?: string };
type Summary = {
  NEW: number; PROCESSING: number; PROCESSED: number; ERROR: number; pending_mapping_items: number;
};

const allowedSorts = ["ingested_at", "processed_at", "retry_count", "status", "source_record_id"];

export default async function Ingestion({ searchParams }: {
  searchParams: Promise<{ status?: string; offset?: string; sort?: string; direction?: string }>;
}) {
  const canWrite = (await currentRole()) === "admin";
  const params = await searchParams, offset = Number(params.offset || 0), limit = 50;
  const status = params.status || "";
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "ingested_at";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const query = new URLSearchParams({ sort, direction });
  if (status) query.set("status", status);
  const [data, summary] = await Promise.all([
    api<Page<Row>>("/admin/ingestion?limit=" + limit + "&offset=" + offset + "&" + query),
    api<Summary>("/admin/ingestion/summary"),
  ]);
  const sortParams: Record<string, string> = status ? { status } : {};
  function tabHref(nextStatus: string) {
    const next = new URLSearchParams({ sort, direction });
    if (nextStatus) next.set("status", nextStatus);
    return "/ingestion?" + next;
  }
  return <Shell title="Ingestion control"
    subtitle="Monitor raw orders, run processing jobs and correct source errors.">
    <section className="panel operations-command">
      <div className="operations-copy"><span className="metric-icon"><Icon name="database" /></span>
        <div><span className="section-kicker">Processing command centre</span>
          <h2>Order ingestion pipeline</h2>
          <p>Convert pending raw records into analytics-ready customers, orders and products.</p></div>
        {canWrite && <div className="actions">
          <form action={startJob}><input type="hidden" name="kind" value="pending" />
            <button className="button primary"><Icon name="jobs" size={17} />Process pending</button></form>
          <form action={startJob}><input type="hidden" name="kind" value="errors" />
            <button className="button"><Icon name="repeat" size={17} />Retry errors</button></form>
        </div>}
      </div>
      <div className="status-grid pipeline-status">
        <div><span className="status-dot pending" /><strong>{summary.NEW}</strong><span>Pending</span></div>
        <div><span className="status-dot running" /><strong>{summary.PROCESSING}</strong><span>Processing</span></div>
        <div><span className="status-dot success" /><strong>{summary.PROCESSED}</strong><span>Processed</span></div>
        <div><span className="status-dot error" /><strong>{summary.ERROR}</strong><span>Errors</span></div>
      </div>
    </section>

    <div className="list-heading"><div><span className="section-kicker">Source records</span>
      <h2>Ingestion activity</h2></div>
      <div className="tabs">{["", "NEW", "PROCESSED", "ERROR"].map(s =>
        <a className={status === s ? "selected" : ""} href={tabHref(s)} key={s}>{s || "All"}</a>)}</div>
    </div>
    <section className="panel table-wrap"><table><thead><tr>
      <th><SortLink label="Order" column="source_record_id" current={sort} direction={direction}
        path="/ingestion" params={sortParams} /></th><th>Source</th>
      <th><SortLink label="Status" column="status" current={sort} direction={direction}
        path="/ingestion" params={sortParams} /></th>
      <th><SortLink label="Ingested" column="ingested_at" current={sort} direction={direction}
        path="/ingestion" params={sortParams} /></th>
      <th><SortLink label="Retries" column="retry_count" current={sort} direction={direction}
        path="/ingestion" params={sortParams} /></th><th>Issue / action</th></tr></thead>
      <tbody>{data.items.map(row => <tr key={row.id}><td>{row.source_record_id}</td>
        <td>{row.source_system}</td><td><Status value={row.status} /></td>
        <td>{new Date(row.ingested_at).toLocaleDateString("en-IN")}</td><td>{row.retry_count}</td>
        <td>{row.error_message ? <div className="issue"><span>{row.error_message}</span>
          {canWrite && (row.error_message.includes("order_date") ?
            <form action={correctDate} className="inline-form"><input type="hidden" name="id" value={row.id} />
              <input type="date" name="order_date" required /><input name="reason" minLength={5}
                placeholder="Source used to confirm date" required /><button className="button small">Correct &amp; retry</button></form>
            : <form action={retryOrder}><input type="hidden" name="id" value={row.id} />
                <button className="button small">Retry</button></form>)}</div> : "-"}</td></tr>)}</tbody>
    </table></section>
    <Pager total={data.total} offset={offset} limit={limit} path="/ingestion" query={query.toString()} />
  </Shell>;
}
