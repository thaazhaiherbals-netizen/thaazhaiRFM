"use client";

import { FormEvent, useState } from "react";

export type FollowUpStatus = "NOT_CONTACTED" | "CONTACTED" | "NO_ANSWER" | "CALLBACK" |
  "INTERESTED" | "NOT_INTERESTED" | "DO_NOT_CONTACT";
export type CustomerSegment = "CHAMPIONS" | "LOYAL_REPEAT" | "NEW_CUSTOMER" |
  "HIGH_VALUE_ONE_TIME" | "ACTIVE_ONE_TIME" | "AT_RISK_REPEAT" |
  "AT_RISK_HIGH_VALUE" | "DORMANT_ONE_TIME";
export type Customer = {
  id: string; customer_name?: string; normalized_phone?: string; email?: string;
  first_order_date?: string; last_order_date?: string; order_count: number; lifetime_value: string;
  average_order_value: string; recency_days: number; segment: CustomerSegment; tags: string[];
  follow_up_status: FollowUpStatus; follow_up_channel?: string; last_follow_up_by?: string;
  last_follow_up_at?: string; next_follow_up_at?: string;
  latest_sentiment?: string; latest_feedback_tags?: string[];
  latest_purchase_intent?: string; latest_offer_interest?: boolean;
  latest_expected_order_date?: string;
};
type Order = {
  id: string; source_record_id: string; order_date: string; order_value: string;
  payment_method?: string; delivery_city?: string; delivery_pincode?: string;
};
type Item = {
  id: string; raw_product_name: string; raw_variant_name?: string; canonical_name?: string;
  variant_name?: string; quantity: number; unit_price: string; line_total: string;
  mapping_status: string;
};
type FollowUp = {
  id: string; customer_id: string; status: FollowUpStatus; channel: string;
  contacted_by: string; sentiment: string; feedback_tags: string[];
  purchase_intent: string; offer_interest: boolean; expected_order_date?: string;
  notes?: string; contacted_at: string; next_follow_up_at?: string;
};
type CustomerDetail = { customer: Customer; orders: Order[]; follow_ups: FollowUp[] };
type OrderDetail = { order: Order; items: Item[] };

const segmentLabels: Record<CustomerSegment, string> = {
  CHAMPIONS: "Best repeat customers", LOYAL_REPEAT: "Regular repeat customers",
  NEW_CUSTOMER: "New first-order customers",
  HIGH_VALUE_ONE_TIME: "Big first-order customers",
  ACTIVE_ONE_TIME: "Recent one-time customers",
  AT_RISK_REPEAT: "Repeat customers becoming inactive",
  AT_RISK_HIGH_VALUE: "Big spenders becoming inactive",
  DORMANT_ONE_TIME: "Old one-time customers",
};
const tagLabels: Record<string, string> = {
  RECENT_30D: "Recent 30d", FIRST_TIME_BUYER: "First-time buyer",
  REPEAT_BUYER: "Repeat buyer", HIGH_VALUE: "High value", VIP_VALUE: "VIP value",
  HAIR_COLOR: "Hair colour", HAIR_CARE: "Hair care", SKIN_CARE: "Skin care",
  HYDROSOL: "Hydrosol", COMBO_BUYER: "Combo buyer",
};
const feedbackLabels: Record<string, string> = {
  POSITIVE_FEEDBACK: "Positive feedback", PRODUCT_LIKED: "Liked the product",
  PRODUCT_DISLIKED: "Did not like the product", HAS_CONCERNS: "Has concerns",
  PRICE_TOO_HIGH: "Price feels high", QUALITY_CONCERN: "Quality concern",
  PACKAGING_CONCERN: "Packaging concern", DELIVERY_CONCERN: "Delivery concern",
  RESULTS_NOT_SEEN: "Results not seen", WANTS_OFFER: "Interested in an offer",
  READY_TO_REORDER: "Ready to order again",
};
const intentLabels: Record<string, string> = {
  UNKNOWN: "Order chance not discussed", HIGH: "Likely to order soon",
  MEDIUM: "May order with follow-up", LOW: "Unlikely to order now",
  NONE: "Does not plan to order",
};
const sentimentLabels: Record<string, string> = {
  NOT_RECORDED: "Feeling not recorded", POSITIVE: "Positive", NEUTRAL: "Neutral",
  MIXED: "Mixed", NEGATIVE: "Negative",
};
const statusLabels: Record<FollowUpStatus, string> = {
  NOT_CONTACTED: "Not contacted", CONTACTED: "Contacted", NO_ANSWER: "No answer",
  CALLBACK: "Callback", INTERESTED: "Interested", NOT_INTERESTED: "Not interested",
  DO_NOT_CONTACT: "Do not contact",
};
const money = (value: string | number) =>
  "\u20B9" + Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2 });
const formatDateTime = (value?: string) => value
  ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
  : "";

export function CustomerTable({ customers, sort, direction, search, followUpStatus,
  segment, tag, salesSignal, canWrite }: {
  canWrite: boolean;
  customers: Customer[]; sort: string; direction: string; search: string;
  followUpStatus: string; segment: string; tag: string; salesSignal: string;
}) {
  function sortHref(column: string) {
    const query = new URLSearchParams({
      sort: column,
      direction: sort === column && direction === "desc" ? "asc" : "desc",
    });
    if (search) query.set("search", search);
    if (followUpStatus) query.set("follow_up_status", followUpStatus);
    if (segment) query.set("segment", segment);
    if (tag) query.set("tag", tag);
    if (salesSignal) query.set("sales_signal", salesSignal);
    return `/customers?${query.toString()}`;
  }
  function sortLabel(label: string, column: string) {
    const marker = sort === column ? (direction === "asc" ? " \u2191" : " \u2193") : " \u2195";
    return <a className={`sort-link ${sort === column ? "active" : ""}`}
      href={sortHref(column)}>{label}{marker}</a>;
  }
  const [openCustomer, setOpenCustomer] = useState<string>();
  const [openOrder, setOpenOrder] = useState<string>();
  const [customerDetails, setCustomerDetails] = useState<Record<string, CustomerDetail>>({});
  const [orderDetails, setOrderDetails] = useState<Record<string, OrderDetail>>({});
  const [followUpOverrides, setFollowUpOverrides] = useState<Record<string, Partial<Customer>>>({});
  const [loading, setLoading] = useState<string>();
  const [saving, setSaving] = useState<string>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();

  async function loadCustomer(id: string) {
    if (openCustomer === id) {
      setOpenCustomer(undefined); setOpenOrder(undefined); return;
    }
    setOpenCustomer(id); setOpenOrder(undefined); setError(undefined); setNotice(undefined);
    if (customerDetails[id]) return;
    setLoading(`customer:${id}`);
    try {
      const response = await fetch(`/api/customers/${id}`);
      if (!response.ok) throw new Error("Could not load this customer's details");
      const result: CustomerDetail = await response.json();
      setCustomerDetails(current => ({ ...current, [id]: result }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load customer");
    } finally { setLoading(undefined); }
  }

  async function loadOrder(id: string) {
    if (openOrder === id) { setOpenOrder(undefined); return; }
    setOpenOrder(id); setError(undefined);
    if (orderDetails[id]) return;
    setLoading(`order:${id}`);
    try {
      const response = await fetch(`/api/orders/${id}`);
      if (!response.ok) throw new Error("Could not load this order's details");
      const result: OrderDetail = await response.json();
      setOrderDetails(current => ({ ...current, [id]: result }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load order details");
    } finally { setLoading(undefined); }
  }

  async function saveFollowUp(customerId: string, formData: FormData) {
    setSaving(customerId); setError(undefined); setNotice(undefined);
    const nextValue = String(formData.get("next_follow_up_at") || "");
    const feedbackTags = formData.getAll("feedback_tags").map(String);
    try {
      const response = await fetch(`/api/customers/${customerId}/follow-ups`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          status: String(formData.get("status")),
          channel: String(formData.get("channel")),
          contacted_by: String(formData.get("contacted_by")),
          sentiment: String(formData.get("sentiment")),
          feedback_tags: feedbackTags,
          purchase_intent: String(formData.get("purchase_intent")),
          offer_interest: formData.get("offer_interest") === "yes",
          expected_order_date: String(formData.get("expected_order_date") || "") || null,
          notes: String(formData.get("notes") || "") || null,
          next_follow_up_at: nextValue ? new Date(nextValue).toISOString() : null,
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Could not save follow-up");
      }
      const saved: FollowUp = await response.json();
      setFollowUpOverrides(current => ({
        ...current,
        [customerId]: {
          follow_up_status: saved.status,
          follow_up_channel: saved.channel,
          last_follow_up_by: saved.contacted_by,
          last_follow_up_at: saved.contacted_at,
          next_follow_up_at: saved.next_follow_up_at,
          latest_sentiment: saved.sentiment,
          latest_feedback_tags: saved.feedback_tags,
          latest_purchase_intent: saved.purchase_intent,
          latest_offer_interest: saved.offer_interest,
          latest_expected_order_date: saved.expected_order_date,
        },
      }));
      setCustomerDetails(current => {
        const detail = current[customerId];
        return detail ? {
          ...current,
          [customerId]: { ...detail, follow_ups: [saved, ...(detail.follow_ups || [])] },
        } : current;
      });
      setNotice("Follow-up saved. The team can now see this contact.");
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not save follow-up");
      return false;
    } finally { setSaving(undefined); }
  }

  return <section className="panel table-wrap"><table className="customer-table">
    <thead><tr><th></th><th>{sortLabel("Customer", "customer_name")}</th>
      <th>{sortLabel("Segment", "segment")}</th><th>Phone</th>
      <th>{sortLabel("First purchase", "first_order_date")}</th>
      <th>{sortLabel("Last purchase", "last_order_date")}</th>
      <th>{sortLabel("Orders", "order_count")}</th>
      <th>{sortLabel("Lifetime value", "lifetime_value")}</th>
      <th>{sortLabel("Follow-up", "last_follow_up_at")}</th></tr></thead>
    <tbody>{customers.map((baseCustomer, index) => {
      const customer = { ...baseCustomer, ...followUpOverrides[baseCustomer.id] };
      const expanded = openCustomer === customer.id;
      const detail = customerDetails[customer.id];
      return <CustomerRows canWrite={canWrite} key={customer.id} customer={customer} expanded={expanded}
        tone={index % 2} detail={detail} openOrder={openOrder} orderDetails={orderDetails}
        loading={loading} saving={saving === customer.id}
        error={expanded ? error : undefined} notice={expanded ? notice : undefined}
        toggleCustomer={() => loadCustomer(customer.id)} toggleOrder={loadOrder}
        saveFollowUp={formData => saveFollowUp(customer.id, formData)} />;
    })}</tbody>
  </table></section>;
}

function CustomerRows({ customer, expanded, tone, detail, openOrder, orderDetails, loading,
  saving, error, notice, toggleCustomer, toggleOrder, saveFollowUp, canWrite }: {
  canWrite: boolean;
  customer: Customer; expanded: boolean; tone: number; detail?: CustomerDetail; openOrder?: string;
  orderDetails: Record<string, OrderDetail>; loading?: string; saving: boolean;
  error?: string; notice?: string; toggleCustomer: () => void;
  toggleOrder: (id: string) => void; saveFollowUp: (data: FormData) => Promise<boolean>;
}) {
  return <>
    <tr className={`expandable-row customer-band-${tone} ${expanded ? "expanded" : ""}`}>
      <td><button className="chevron" onClick={toggleCustomer} aria-expanded={expanded}
        aria-label={`${expanded ? "Collapse" : "Expand"} ${customer.customer_name || "customer"}`}>
        {expanded ? "\u2212" : "+"}</button></td>
      <td><button className="row-button" onClick={toggleCustomer}>
        {customer.customer_name || "Unknown"}</button><small>{customer.email}</small></td>
      <td><SegmentBadge customer={customer} /></td>
      <td>{customer.normalized_phone}</td><td>{customer.first_order_date}</td>
      <td>{customer.last_order_date}</td><td><span className="count-badge">
        {customer.order_count}</span></td>
      <td><strong className="money-highlight">{money(customer.lifetime_value)}</strong></td>
      <td><FollowUpBadge customer={customer} /></td>
    </tr>
    {expanded && <tr className={`expansion-row customer-band-${tone}`}><td colSpan={9}>
      <div className="expansion-panel">
        {loading === `customer:${customer.id}` && <p>Loading customer details...</p>}
        {error && <div className="alert error">{error}</div>}
        {notice && <div className="alert success">{notice}</div>}
        {detail && <>
          <section className="customer-orders-block">
            <div className="block-heading"><div><span>Purchase history</span>
              <h3>All customer orders</h3></div>
              <strong>{detail.orders.length} order{detail.orders.length === 1 ? "" : "s"}</strong>
            </div>
            <div className="order-stack">
              {detail.orders.map((order, index) => <div
                className={`nested-order order-tone-${index % 3} ${openOrder === order.id ? "open" : ""}`}
                key={order.id}>
                <button className="order-summary" onClick={() => toggleOrder(order.id)}
                  aria-expanded={openOrder === order.id}>
                  <span className="chevron">{openOrder === order.id ? "\u2212" : "+"}</span>
                  <strong className="order-id">#{order.source_record_id}</strong>
                  <span>{order.order_date}</span>
                  <span>{order.payment_method || "Payment unknown"}</span>
                  <span>{order.delivery_city || order.delivery_pincode || "Location unknown"}</span>
                  <strong className="nested-amount">{money(order.order_value)}</strong>
                </button>
                {openOrder === order.id && <OrderItems detail={orderDetails[order.id]}
                  loading={loading === `order:${order.id}`} error={error} />}
              </div>)}
            </div>
          </section>
          <section className="customer-contact-block">
            <div className="customer-analysis-strip">
              <div><span>Sales group</span><SegmentBadge customer={customer} /></div>
              <div><span>Last purchase</span><strong>{customer.recency_days} days ago</strong></div>
              <div><span>Average order</span><strong>{money(customer.average_order_value)}</strong></div>
              <div className="customer-tags"><span>Why this customer matters</span><div>
                {customer.tags.map(tag => <em key={tag}>{tagLabels[tag] || tag}</em>)}</div></div>
            </div>
            <FollowUpPanel canWrite={canWrite} customer={customer} history={detail.follow_ups || []}
              saving={saving} onSave={saveFollowUp} />
          </section>
        </>}
      </div>
    </td></tr>}
  </>;
}

function SegmentBadge({ customer }: { customer: Customer }) {
  return <div className="segment-summary">
    <span className={`segment-pill ${customer.segment.toLowerCase()}`}>
      {segmentLabels[customer.segment]}</span>
    <small>{customer.recency_days}d since purchase</small>
  </div>;
}

function FollowUpBadge({ customer }: { customer: Customer }) {
  return <div className="follow-up-summary">
    <span className={`follow-up-pill ${customer.follow_up_status.toLowerCase()}`}>
      {statusLabels[customer.follow_up_status]}</span>
    {customer.latest_purchase_intent && customer.latest_purchase_intent !== "UNKNOWN" &&
      <small className={`intent-text ${customer.latest_purchase_intent.toLowerCase()}`}>
        {intentLabels[customer.latest_purchase_intent]}</small>}
    {customer.latest_offer_interest && <small className="offer-signal">Interested in an offer</small>}
    {customer.last_follow_up_at && <small>
      {formatDateTime(customer.last_follow_up_at)}{customer.last_follow_up_by
        ? ` by ${customer.last_follow_up_by}` : ""}
    </small>}
    {customer.next_follow_up_at && <small className="next-contact">
      Next: {formatDateTime(customer.next_follow_up_at)}</small>}
  </div>;
}
function FollowUpPanel({ customer, history, saving, onSave, canWrite }: {
  canWrite: boolean;
  customer: Customer; history: FollowUp[]; saving: boolean;
  onSave: (data: FormData) => Promise<boolean>;
}) {
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canWrite || saving) return;
    const form = event.currentTarget;
    if (await onSave(new FormData(form))) form.reset();
  }
  const feedbackOptions = [
    ["POSITIVE_FEEDBACK", "Gave positive feedback"],
    ["PRODUCT_LIKED", "Liked the product"],
    ["PRODUCT_DISLIKED", "Did not like the product"],
    ["HAS_CONCERNS", "Has concerns"],
    ["PRICE_TOO_HIGH", "Feels the price is high"],
    ["QUALITY_CONCERN", "Has a quality concern"],
    ["PACKAGING_CONCERN", "Has a packaging concern"],
    ["DELIVERY_CONCERN", "Had a delivery concern"],
    ["RESULTS_NOT_SEEN", "Has not seen results"],
    ["READY_TO_REORDER", "Ready to order again"],
  ];
  return <section className="follow-up-panel">
    <div className="follow-up-heading">
      <div><span>Customer conversation</span><h3>{canWrite ? "Record what happened after the call" : "Explore the follow-up form"}</h3>
        <p>Structured answers help the whole team choose the right next action.</p></div>
      <FollowUpBadge customer={customer} />
    </div>
    {!canWrite && <p className="viewer-form-notice">View-only preview: you can try the fields below to learn how follow-ups work. Nothing you enter here will be saved.</p>}
    <form className="follow-up-form rich-follow-up-form" onSubmit={submit}>
      <label><span>Call result</span><select name="status" required defaultValue="CONTACTED">
        <option value="CONTACTED">Spoke to customer</option>
        <option value="NO_ANSWER">No answer</option>
        <option value="CALLBACK">Asked us to call again</option>
        <option value="INTERESTED">Interested</option>
        <option value="NOT_INTERESTED">Not interested</option>
        <option value="DO_NOT_CONTACT">Do not contact again</option>
      </select></label>
      <label><span>Contact method</span><select name="channel" required defaultValue="CALL">
        <option value="CALL">Phone call</option><option value="WHATSAPP">WhatsApp</option>
        <option value="EMAIL">Email</option><option value="OTHER">Other</option>
      </select></label>
      <label><span>Team member</span><input name="contacted_by" required minLength={2}
        maxLength={100} placeholder="Your name" /></label>
      <label><span>Customer feeling</span><select name="sentiment" defaultValue="NOT_RECORDED">
        <option value="NOT_RECORDED">Not discussed</option>
        <option value="POSITIVE">Positive</option><option value="NEUTRAL">Neutral</option>
        <option value="MIXED">Mixed</option><option value="NEGATIVE">Negative</option>
      </select></label>
      <label><span>Chance of next order</span><select name="purchase_intent" defaultValue="UNKNOWN">
        <option value="UNKNOWN">Not discussed</option>
        <option value="HIGH">Likely to order soon</option>
        <option value="MEDIUM">May order with follow-up</option>
        <option value="LOW">Unlikely to order now</option>
        <option value="NONE">Does not plan to order</option>
      </select></label>
      <label><span>Expected order date</span><input name="expected_order_date" type="date" /></label>
      <label><span>Next follow-up</span><input name="next_follow_up_at"
        type="datetime-local" /></label>
      <label className="offer-interest-check"><input name="offer_interest" value="yes"
        type="checkbox" /><span>Customer wants an offer or discount</span></label>
      <fieldset className="feedback-options"><legend>What did the customer say?</legend>
        {feedbackOptions.map(([value, label]) => <label key={value}>
          <input type="checkbox" name="feedback_tags" value={value} /><span>{label}</span>
        </label>)}
      </fieldset>
      <label className="follow-up-notes"><span>Call notes or full concern</span><textarea name="notes"
        maxLength={1000} placeholder="Write the important details for the next team member" /></label>
      <button className="button primary" disabled={!canWrite || saving}
        title={!canWrite ? "Only administrators can save call results" : undefined}>
        {!canWrite ? "Save call result (view only)" : saving ? "Saving call..." : "Save call result"}</button>
    </form>
    <div className="follow-up-history">
      <strong>Previous customer conversations</strong>
      {history.length === 0 ? <p>No follow-up recorded yet.</p> :
        history.slice(0, 10).map(item => <article key={item.id}>
          <span className={`follow-up-pill ${item.status.toLowerCase()}`}>
            {statusLabels[item.status]}</span>
          <div><strong>{item.contacted_by} via {item.channel.toLowerCase()}</strong>
            <small>{formatDateTime(item.contacted_at)}
              {item.next_follow_up_at ? ` | Next call: ${formatDateTime(item.next_follow_up_at)}` : ""}
              {item.expected_order_date ? ` | Expected order: ${item.expected_order_date}` : ""}
            </small>
            <div className="conversation-signals">
              <em>{sentimentLabels[item.sentiment] || item.sentiment}</em>
              <em>{intentLabels[item.purchase_intent] || item.purchase_intent}</em>
              {item.offer_interest && <em>Wants an offer</em>}
              {(item.feedback_tags || []).map(tag => <em key={tag}>
                {feedbackLabels[tag] || tag}</em>)}
            </div>
            {item.notes && <p>{item.notes}</p>}</div>
        </article>)}
    </div>
  </section>;
}
function OrderItems({ detail, loading, error }: {
  detail?: OrderDetail; loading: boolean; error?: string;
}) {
  if (loading) return <div className="order-detail-inline">Loading products...</div>;
  if (error) return <div className="order-detail-inline alert error">{error}</div>;
  if (!detail) return null;
  return <div className="order-detail-inline">
    <div className="order-meta"><span>Payment: {detail.order.payment_method || "Unknown"}</span>
      <span>Pincode: {detail.order.delivery_pincode || "Unknown"}</span></div>
    <table className="item-table"><thead><tr><th>Product</th><th>Catalogue match</th>
      <th>Qty</th><th>Unit price</th><th>Line total</th><th>Mapping</th></tr></thead>
      <tbody>{detail.items.map(item => <tr key={item.id}>
        <td>{item.raw_product_name}<small>{item.raw_variant_name}</small></td>
        <td>{item.canonical_name || "Unmapped"}<small>{item.variant_name}</small></td>
        <td>{item.quantity}</td><td>{money(item.unit_price)}</td><td>{money(item.line_total)}</td>
        <td><span className={`status-pill ${item.mapping_status.toLowerCase()}`}>
          {item.mapping_status}</span></td></tr>)}</tbody></table>
  </div>;
}
