"use client";
import { useState } from "react";
import Link from "next/link";
import { CatalogueProduct } from "../product-picker";

export function OpportunityForm({ products, initialA, initialB, initialCombo, mode, search }: {
  products: CatalogueProduct[]; initialA: string; initialB: string; initialCombo: string; mode: string; search: string;
}) {
  const [a, setA] = useState(initialA), [b, setB] = useState(initialB);
  const [combo, setCombo] = useState(initialCombo);
  const repeat = new URLSearchParams({ product_ids: [...new Set([a, b].filter(Boolean))].join(","), min_product_orders: "2", product_match: "any" });
  const options = products.map(product => <option key={product.id} value={product.id}>{product.name}</option>);
  return <form className="product-behavior-filter">
    <h2>Find an audience</h2>
    <div><label>Opportunity type<select name="mode" defaultValue={mode}>
      <option value="combo">Upsell · Bought both separately</option><option value="cross_sell">Cross-sell · Bought A, not B</option></select></label>
      <label>Product A · Already purchased<select name="product_a" required value={a} onChange={event => setA(event.target.value)}>
        <option value="">Choose a catalogue product</option>{options}</select></label>
      <label>Product B · Complementary product<select name="product_b" required value={b} onChange={event => setB(event.target.value)}>
        <option value="">Choose a catalogue product</option>{options}</select></label></div>
    <div><label>Offer product · Exclude previous buyers<select name="combo" value={combo} onChange={event => setCombo(event.target.value)}>
      <option value="">No exclusion — keep all eligible customers</option>{options}</select>
      <small>If you plan to promote an existing bundle or upgraded product, choose it here. Anyone who has already purchased that exact product will be removed from the audience. Otherwise leave “No exclusion” selected.</small></label>
      <label>Search customers<input name="search" maxLength={150} defaultValue={search} placeholder="Name, phone or email" /></label></div>
    <p className="catalogue-note">Products come from your mapped catalogue. All variants of a selected product count; unmapped order items do not.</p>
    <div className="opportunity-actions"><button className="button primary">Find opportunities</button><Link className="button" href="/customers/opportunities">Clear</Link>
      {a || b ? <Link className="button" href={`/customers?${repeat}#product-purchase-behaviour`}>Find repeat buyers of selected products</Link>
        : <span>Select a product above to find its repeat buyers.</span>}</div>
    <small>Repeat buyers means two or more separate orders for any selected product. This opens Lead Centre with those product filters applied.</small>
  </form>;
}
