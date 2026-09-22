import { api, Page } from "@/lib/api";
import { Shell, Pager, SortLink, Status } from "../components";

type Job = { id: string; job_type: string; status: string; total_records: number;
  processed_count: number; success_count: number; failed_count: number; created_at: string };

const allowedSorts = ["created_at", "total_records", "processed_count", "success_count", "failed_count", "status"];

export default async function Jobs({ searchParams }: {
  searchParams: Promise<{ offset?: string; sort?: string; direction?: string }>;
}) {
  const params = await searchParams, offset = Number(params.offset || 0), limit = 50;
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "created_at";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const query = new URLSearchParams({ sort, direction });
  const data = await api<Page<Job>>("/admin/jobs?limit=" + limit + "&offset=" + offset + "&" + query);
  return <Shell title="Processing jobs"><section className="panel table-wrap"><table>
    <thead><tr>
      <th><SortLink label="Created" column="created_at" current={sort} direction={direction} path="/jobs" /></th>
      <th>Type</th>
      <th><SortLink label="Status" column="status" current={sort} direction={direction} path="/jobs" /></th>
      <th><SortLink label="Progress" column="processed_count" current={sort} direction={direction} path="/jobs" /></th>
      <th><SortLink label="Success" column="success_count" current={sort} direction={direction} path="/jobs" /></th>
      <th><SortLink label="Failed" column="failed_count" current={sort} direction={direction} path="/jobs" /></th>
    </tr></thead><tbody>{data.items.map(job =>
      <tr key={job.id}><td>{new Date(job.created_at).toLocaleString("en-IN")}</td>
        <td>{job.job_type.replaceAll("_", " ")}</td><td><Status value={job.status} /></td>
        <td>{job.processed_count} / {job.total_records}</td><td>{job.success_count}</td>
        <td>{job.failed_count}</td></tr>)}</tbody></table></section>
    <Pager total={data.total} offset={offset} limit={limit} path="/jobs" query={query.toString()} />
  </Shell>;
}
