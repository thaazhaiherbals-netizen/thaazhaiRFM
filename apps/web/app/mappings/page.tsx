import { currentRole } from "@/lib/auth";
import { api, Page } from "@/lib/api";
import { Shell, Money } from "../components";
import { saveMapping, startJob } from "../actions";

type Missing = { source_system: string; raw_product_name: string; raw_variant_name?: string;
  affected_items: number; affected_orders: number; item_revenue: string; mapping_error: string };
type Product = { product_id: string; canonical_name: string; variant_id?: string; variant_name?: string };

const allowedSorts = ["affected_orders", "affected_items", "item_revenue", "product_name"];

export default async function Mappings({ searchParams }: {
  searchParams: Promise<{ sort?: string; direction?: string }>;
}) {
  const canWrite = (await currentRole()) === "admin";
  const params = await searchParams;
  const sort = allowedSorts.includes(params.sort || "") ? params.sort! : "affected_orders";
  const direction = params.direction === "asc" ? "asc" : "desc";
  const [missing, products] = await Promise.all([
    api<Page<Missing>>("/admin/unmapped-products?limit=200&sort=" + sort + "&direction=" + direction),
    api<Page<Product>>("/admin/products?limit=200"),
  ]);
  return <Shell title="Product mappings">
    <div className="panel-heading"><div><h2>Needs mapping</h2>
      <p>Save the confirmed catalogue match; affected orders are then resolved in the background.</p></div>
      {canWrite && <form action={startJob}><input type="hidden" name="kind" value="mappings" />
        <button className="button">Resolve all again</button></form>}</div>
    <form className="sort-controls">
      <label>Sort by <select name="sort" defaultValue={sort}>
        <option value="affected_orders">Affected orders</option>
        <option value="affected_items">Affected items</option>
        <option value="item_revenue">Revenue</option>
        <option value="product_name">Product name</option>
      </select></label>
      <label>Direction <select name="direction" defaultValue={direction}>
        <option value="desc">Descending</option><option value="asc">Ascending</option>
      </select></label>
      <button className="button small">Apply</button>
    </form>
    {missing.total === 0 ? <div className="empty">All order items are mapped.</div> :
      <div className="mapping-grid">{missing.items.map((row, index) =>
        <div className="panel mapping-card" key={index}>

          <div><h3>{row.raw_product_name}</h3><p>{row.raw_variant_name || "No variant"} -{" "}
            {row.affected_orders} orders - <Money value={row.item_revenue} /></p>
            <small>{row.mapping_error}</small></div>
          {canWrite && <form action={saveMapping}>
          <input type="hidden" name="source_system" value={row.source_system} />
          <input type="hidden" name="alias_name" value={row.raw_product_name} />
          <input type="hidden" name="alias_variant" value={row.raw_variant_name || ""} />
          <select name="catalogue" required defaultValue=""><option value="" disabled>Select product and variant</option>
            {products.items.map(p => <option key={p.variant_id || p.product_id}
              value={p.product_id + "|" + (p.variant_id || "")}>
              {p.canonical_name}{p.variant_name ? " - " + p.variant_name : ""}
            </option>)}</select>
          <button className="button primary">Save mapping</button>
        </form>}</div>)}</div>}
  </Shell>;
}
