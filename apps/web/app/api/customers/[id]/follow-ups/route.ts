import { api } from "@/lib/api";

export async function POST(request: Request, context: { params: Promise<{ id: string }> }) {
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
