"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { api } from "@/lib/api";
import { SESSION_COOKIE } from "@/lib/session";
import { requireAccess } from "@/lib/auth";

export async function logout() {
  (await cookies()).delete(SESSION_COOKIE);
  (await cookies()).delete("thaazhai_admin");
  redirect("/login");
}

export async function startJob(formData: FormData) {
  await requireAccess("POST");
  const kind = String(formData.get("kind"));
  const routes: Record<string, string> = {
    pending: "/admin/jobs/process-pending",
    errors: "/admin/jobs/retry-errors",
    mappings: "/admin/jobs/resolve-mappings",
  };
  if (!routes[kind]) throw new Error("Unknown job type");
  await api(routes[kind], { method: "POST" });
  revalidatePath("/");
  revalidatePath("/ingestion");
  revalidatePath("/jobs");
}

export async function retryOrder(formData: FormData) {
  await requireAccess("POST");
  const id = String(formData.get("id"));
  await api(`/admin/ingestion/${id}/retry`, { method: "POST" });
  revalidatePath("/ingestion");
  revalidatePath("/jobs");
}

export async function correctDate(formData: FormData) {
  await requireAccess("POST");
  const id = String(formData.get("id"));
  await api(`/admin/ingestion/${id}/order-date`, {
    method: "PUT",
    body: JSON.stringify({
      order_date: String(formData.get("order_date")),
      reason: String(formData.get("reason")),
    }),
  });
  revalidatePath("/ingestion");
  revalidatePath("/jobs");
}

export async function saveMapping(formData: FormData) {
  await requireAccess("POST");
  const [product_id, variant_id] = String(formData.get("catalogue")).split("|");
  await api("/admin/product-aliases", {
    method: "POST",
    body: JSON.stringify({
      source_system: String(formData.get("source_system")),
      alias_name: String(formData.get("alias_name")),
      alias_variant: String(formData.get("alias_variant") || "") || null,
      product_id,
      variant_id: variant_id || null,
    }),
  });
  await api("/admin/jobs/resolve-mappings", { method: "POST" });
  revalidatePath("/mappings");
  revalidatePath("/jobs");
}

export async function saveSegmentSettings(formData: FormData) {
  await requireAccess("POST");
  await api("/admin/customer-segment-settings", {
    method: "PUT",
    body: JSON.stringify({
      new_customer_days: Number(formData.get("new_customer_days")),
      active_customer_days: Number(formData.get("active_customer_days")),
      champion_recency_days: Number(formData.get("champion_recency_days")),
      champion_min_orders: Number(formData.get("champion_min_orders")),
      high_value_percentile: Number(formData.get("high_value_percentile")) / 100,
      vip_value_percentile: Number(formData.get("vip_value_percentile")) / 100,
    }),
  });
  revalidatePath("/customers");
}

