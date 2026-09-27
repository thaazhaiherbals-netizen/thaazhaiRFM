import { api, Page } from "@/lib/api";
import { currentRole } from "@/lib/auth";
import { Shell, Pager } from "../../components";
import { ListSummary } from "../../list-summary";
import { CatalogueProduct } from "../product-picker";
import { Customer, CustomerTable } from "../customer-table";
import { OpportunityForm } from "./opportunity-form";

type Candidate = Customer & { a_orders: number; b_orders: number; a_last: string; b_last?: string };
type Opportunities = Page<Candidate> & { summary: { lifetime_value: string; repeat_a: number; a_orders: number } };

export default async function ProductOpportunities({ searchParams }: {
  searchParams: Promise<{ product_a?: string; product_b?: string; combo?: string; mode?: string; search?: string; offset?: string }>;
}) {
  const params = await searchParams;
  const [products, role] = await Promise.all([api<CatalogueProduct[]>("/admin/product-options"), currentRole()]);
  const resolve = (value?: string) => products.find(product => product.id === value || product.name.toLowerCase() === value?.trim().toLowerCase());
  const a = resolve(params.product_a), b = resolve(params.product_b), offer = resolve(params.combo);
  const search = (params.search || "").trim().slice(0, 150);
  const mode = params.mode === "cross_sell" ? "cross_sell" : "combo";
  const offset = Math.max(0, Math.floor(Number(params.offset) || 0)), limit = 50;
  const ready = !!a && !!b && a.id !== b.id && (!params.combo || !!offer);
  const query = new URLSearchParams({ product_a: a?.id || "", product_b: b?.id || "", combo: offer?.id || "", mode, search });
  const data = ready ? await api<Opportunities>(`/admin/product-opportunities?${query}&offset=${offset}&limit=${limit}`) : null;
  const customers = (data?.items || []).map(customer => ({ ...customer, product_purchases: [
    { product: a!.name, orders: customer.a_orders, last_purchase: customer.a_last },
    { product: b!.name, orders: customer.b_orders, last_purchase: customer.b_last || "Not purchased" },
  ] }));
  return <Shell title="Product opportunities" subtitle="Find an audience, review their orders and record your follow-up">
    <section className="opportunity-intro"><h2>Turn purchase history into your next offer</h2>
      <p><strong>Upsell:</strong> customers who bought A and B in different orders may be interested in your combined or upgraded offer.</p>
      <p><strong>Cross-sell:</strong> customers who bought A but have never bought B may be interested in the complementary product.</p>
    </section>
    <OpportunityForm key={query.toString()} products={products} initialA={a?.id || ""} initialB={b?.id || ""}
      initialCombo={offer?.id || ""} mode={mode} search={search} />
    {!ready && <p className={params.product_a || params.product_b ? "alert warning" : "panel"}>
      Choose two different catalogue products to see matching customers. If an offer product is specified, it must also be in the catalogue.</p>}
    {data && <>
      <ListSummary title={mode === "combo" ? "Upsell audience" : "Cross-sell audience"}
        description="All eligible customers across every page. These figures describe recorded purchases, not predicted sales."
        cards={[
          { label: "Eligible customers", value: data.total, hint: mode === "combo" ? "Both products in separate orders" : "Product A purchased; product B never purchased" },
          { label: "Repeat A buyers", value: data.summary.repeat_a, hint: "Product A in at least two separate orders" },
          { label: "Product A orders", value: data.summary.a_orders, hint: "Distinct A orders across eligible customers" },
          { label: "Lifetime value", value: data.summary.lifetime_value, money: true, hint: "Historical all-product spending" },
        ]} />
      <p>{mode === "combo" ? `These customers purchased ${a!.name} and ${b!.name} in separate orders.` : `These customers purchased ${a!.name} but have never purchased ${b!.name}.`}
        {offer ? ` Previous buyers of ${offer.name} are excluded.` : " No offer-product exclusion is applied."} Latest “Do not contact” customers are excluded.</p>
      <p>Click a customer row to expand their orders. Use <strong>Customer follow-up</strong> to record feedback and schedule the next contact.</p>
      <CustomerTable key={query.toString()} customers={customers} canWrite={role === "admin" || role === "support"}
        sortable={false} sort="last_order_date" direction="desc" search="" followUpStatus="" segment="" tag=""
        salesSignal="" productSearch="" minProductOrders="2" productMatch="any" />
      <Pager total={data.total} offset={offset} limit={limit} path="/customers/opportunities" query={query.toString()} />
    </>}
  </Shell>;
}
