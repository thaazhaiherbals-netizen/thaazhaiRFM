import { api } from "@/lib/api";
import { currentRole } from "@/lib/auth";
import { accessStatus } from "@/lib/session";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
  const status = accessStatus(await currentRole(), "POST", "/api/customers/customer/follow-ups");
  if (status !== 200) return Response.json({ detail: "Administrator access required" }, { status });
  const { id } = await context.params;
  const body = await request.json();
  try {
    return Response.json(await api(`/admin/customers/${id}/follow-ups`, {
      method: "POST",
      body: JSON.stringify(body),
    }), { status: 201 });
  } catch (reason) {
    return Response.json({
      detail: reason instanceof Error ? reason.message : "Could not save follow-up",
    }, { status: 400 });
  }
}
