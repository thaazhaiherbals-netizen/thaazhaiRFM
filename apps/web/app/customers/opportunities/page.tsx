import Link from "next/link";
import { api, Page } from "@/lib/api";
import { Shell, Money, Pager } from "../../components";
import { ListSummary } from "../../list-summary";

type Candidate = { id: string; customer_name?: string; normalized_phone?: string; email?: string;
  lifetime_value: string; a_orders: number; b_orders: number; a_last: string; b_last?: string };
type Opportunities = Page<Candidate> & { summary: { lifetime_value: string; repeat_a: number; a_orders: number } };

export default async function ProductOpportunities({ searchParams }: {
  searchParams: Promise<{ product_a?: string; product_b?: string; combo?: string; mode?: string; search?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const a = (params.product_a || "").trim().slice(0, 150), b = (params.product_b || "").trim().slice(0, 150);
  const combo = (params.combo || "").trim().slice(0, 150), search = (params.search || "").trim().slice(0, 150);
  const mode = params.mode === "cross_sell" ? "cross_sell" : "combo";
  const offset = Math.max(0, Math.floor(Number(params.offset) || 0)), limit = 50;
  const ready = a.length >= 2 && b.length >= 2 && a.toLowerCase() !== b.toLowerCase();
  const query = new URLSearchParams({ product_a: a, product_b: b, combo, mode, search });
  const [options, data] = await Promise.all([
    api<string[]>("/admin/product-options"),
    ready ? api<Opportunities>(`/admin/product-opportunities?${query}&offset=${offset}&limit=${limit}`) : Promise.resolve(null),
  ]);
  return <Shell title="Product opportunities" subtitle="Build a customer shortlist for a combo or a complementary product">
    <section className="opportunity-intro"><h2>Turn purchase history into your next offer</h2>
      <p><strong>Combo opportunity:</strong> find customers who bought product A and product B in different orders.</p>
      <p><strong>Cross-sell opportunity:</strong> find customers who bought product A but have never bought product B.</p>
      <p>For example, select aloe vera gel and hair colour, then enter your existing combo to exclude customers who already bought it.</p>
      <Link className="button" href="/customers">Find repeat product buyers</Link>
    </section>
    <form className="product-behavior-filter" key={query.toString()}>
      <h2>Find an audience</h2><datalist id="purchased-products">{options.map(name => <option value={name} key={name} />)}</datalist>
      <div><label>Opportunity type<select name="mode" defaultValue={mode}>
        <option value="combo">Combo · Bought both separately</option><option value="cross_sell">Cross-sell · Bought A, not B</option></select></label>
        <label>Product A · Already purchased<input name="product_a" required minLength={2} maxLength={150} list="purchased-products" defaultValue={a} placeholder="e.g. Aloe vera gel" /></label>
        <label>Product B · Complementary product<input name="product_b" required minLength={2} maxLength={150} list="purchased-products" defaultValue={b} placeholder="e.g. Hair colour" /></label></div>
      <div><label>Exclude an existing combo (optional)<input name="combo" maxLength={150} list="purchased-products" defaultValue={combo} placeholder="Select your combo's product name" /></label>
        <label>Search customers<input name="search" maxLength={150} defaultValue={search} placeholder="Name, phone or email" /></label></div>
      <small>Suggestions come from recorded purchases. Names match case-insensitively, including partial names. Matching both names on a single product line is not treated as two separate products.</small>
      <div className="opportunity-actions"><button className="button primary">Find opportunities</button><Link className="button" href="/customers/opportunities">Clear</Link></div>
    </form>
    {!ready && <p className={a || b ? "alert warning" : "panel"}>{a || b ? "Choose two different product names, each at least two characters." : "Choose two products above to see matching customers and purchase evidence."}</p>}
    {data && <>
      <ListSummary title={mode === "combo" ? "Combo audience" : "Cross-sell audience"}
        description="All matching customers across every page. Based on recorded purchases; these are potential audiences, not predicted sales."
        cards={[
          { label: "Eligible customers", value: data.total, hint: mode === "combo" ? "Both products in separate orders" : "Product A purchased; product B never purchased" },
          { label: "Repeat A buyers", value: data.summary.repeat_a, hint: "Product A in at least two distinct orders" },
          { label: "Product A orders", value: data.summary.a_orders, hint: "Distinct A orders across eligible customers" },
          { label: "Lifetime value", value: data.summary.lifetime_value, money: true, hint: "Historical all-product spend, not forecast revenue" },
        ]} />
      <p>Latest “Do not contact” customers are excluded. {combo ? `Previous buyers of “${combo}” are also excluded.` : "No combo exclusion is selected."} All purchase history is considered.</p>
      <section className="panel table-wrap"><table><thead><tr><th>Customer</th><th>Product A: {a}</th><th>Product B: {b}</th><th>Opportunity</th><th>Lifetime value</th></tr></thead>
        <tbody>{!data.items.length && <tr><td colSpan={5}>No matching customers. Try a broader product name, check spelling, or switch opportunity type.</td></tr>}
          {data.items.map(customer => <tr key={customer.id}>
            <td><Link className="row-button" href={`/customers/${customer.id}`}>{customer.customer_name || "Unknown customer"}</Link><small>{customer.normalized_phone || customer.email}</small></td>
            <td>{customer.a_orders} orders<small>Last purchase: {customer.a_last}</small></td>
            <td>{customer.b_orders} orders<small>{customer.b_last ? `Last purchase: ${customer.b_last}` : "Not purchased"}</small></td>
            <td>{mode === "combo" ? `Consider ${combo || "your combo"}: both products were purchased in separate orders.` : `Introduce ${b} alongside their ${a} purchase.`}</td>
            <td><Money value={customer.lifetime_value} /></td></tr>)}</tbody></table></section>
      <Pager total={data.total} offset={offset} limit={limit} path="/customers/opportunities" query={query.toString()} />
    </>}
  </Shell>;
}
