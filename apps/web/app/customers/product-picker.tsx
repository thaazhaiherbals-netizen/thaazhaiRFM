"use client";

import { useEffect, useRef, useState } from "react";
export type CatalogueProduct = { id: string; name: string };

export function ProductPicker({ products, selected }: { products: CatalogueProduct[]; selected: string[] }) {
  const [ids, setIds] = useState(selected);
  const [search, setSearch] = useState("");
  const dropdown = useRef<HTMLDetailsElement>(null);
  const visible = products.filter(product => product.name.toLowerCase().includes(search.trim().toLowerCase()));
  function close() {
    if (dropdown.current) {
      dropdown.current.open = false;
      dropdown.current.querySelector("summary")?.focus();
    }
  }
  useEffect(() => {
    function outside(event: PointerEvent) {
      if (dropdown.current?.open && !dropdown.current.contains(event.target as Node)) dropdown.current.open = false;
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  return <div className="catalogue-picker">
    <input type="hidden" name="product_ids" value={ids.join(",")} />
    <details ref={dropdown} className="catalogue-dropdown" onToggle={event => { if (!event.currentTarget.open) setSearch(""); }}
      onKeyDown={event => {
        if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
        if (event.key === "Enter" && event.target instanceof HTMLInputElement) event.preventDefault();
      }}>
      <summary><span>{ids.length ? `${ids.length} product${ids.length === 1 ? "" : "s"} selected` : "Choose products"}</span><span aria-hidden="true">⌄</span></summary>
      <div className="catalogue-dropdown-body">
        <label className="catalogue-search">Search products<input value={search} onChange={event => setSearch(event.target.value)} placeholder="Type a product name…" /></label>
        <div className="catalogue-options" role="group" aria-label="Products to include">
          {visible.map(product => <label key={product.id} className={ids.includes(product.id) ? "is-selected" : ""}>
            <input type="checkbox" checked={ids.includes(product.id)} disabled={ids.length >= 5 && !ids.includes(product.id)}
              onChange={event => { const checked = event.target.checked; setIds(current => checked ? [...current, product.id] : current.filter(id => id !== product.id)); }} />
            <span>{product.name}</span></label>)}
          {!visible.length && <p>No products found.</p>}
        </div>
        <div className="catalogue-dropdown-footer"><small>{ids.length}/5 selected</small>
          <button type="button" className="button" disabled={!ids.length} onClick={() => setIds([])}>Clear selection</button>
          <button type="button" className="button primary" onClick={close}>Done</button></div>
      </div>
    </details>
    {!!ids.length && <div className="selected-products">{ids.map(id => <button type="button" className="product-chip" key={id}
      aria-label={`Remove ${products.find(product => product.id === id)?.name}`}
      onClick={() => setIds(current => current.filter(value => value !== id))}>
      {products.find(product => product.id === id)?.name} <span aria-hidden="true">×</span></button>)}</div>}
    <small>Choose up to 5 products, then apply your filters. No selection means all products.</small>
  </div>;
}
