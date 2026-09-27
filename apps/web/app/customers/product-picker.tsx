"use client";

import { useState } from "react";
export type CatalogueProduct = { id: string; name: string };

export function ProductPicker({ products, selected }: { products: CatalogueProduct[]; selected: string[] }) {
  const [ids, setIds] = useState(selected);
  const [search, setSearch] = useState("");
  return <div className="catalogue-picker">
    <input type="hidden" name="product_ids" value={ids.join(",")} />
    <label>Search catalogue<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Search your mapped products" /></label>
    <div className="selected-products">{ids.map(id => <button type="button" className="button" key={id}
      onClick={() => setIds(current => current.filter(value => value !== id))}>
      {products.find(product => product.id === id)?.name} ×</button>)}</div>
    <div className="catalogue-options" role="group" aria-label="Products to include">
      {products.filter(product => product.name.toLowerCase().includes(search.toLowerCase())).map(product =>
        <label key={product.id}><input type="checkbox" checked={ids.includes(product.id)}
          disabled={ids.length >= 5 && !ids.includes(product.id)} onChange={event => setIds(current => event.target.checked ? [...current, product.id] : current.filter(id => id !== product.id))} />
          <span>{product.name}</span></label>)}
      {!products.some(product => product.name.toLowerCase().includes(search.toLowerCase())) && <p>No catalogue products match your search.</p>}
    </div><small>{ids.length} of 5 products selected. No selection means all products.</small>
  </div>;
}
