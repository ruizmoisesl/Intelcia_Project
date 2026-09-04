import type { APIRoute } from "astro";

import { ApiError, reviewChange } from "../../../services/api";

/** Aprueba o rechaza una novedad pendiente (supervisor/admin). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/novedades?error=Formulario%20inv%C3%A1lido");

  const changeId = String(form.get("change_id") ?? "");
  const decisionValue = String(form.get("decision") ?? "");
  const note = String(form.get("note") ?? "").trim();
  const next = String(form.get("next") ?? "/dashboard/novedades");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/novedades";

  if (!/^\d+$/.test(changeId) || !["approve", "reject"].includes(decisionValue)) {
    return redirect(`${safeNext}?error=Datos%20inv%C3%A1lidos`);
  }

  const decision: "approve" | "reject" =
    decisionValue === "approve" ? "approve" : "reject";

  try {
    await reviewChange(locals.token, Number(changeId), decision, note || undefined);
    return redirect(`${safeNext}?reviewed=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo revisar la novedad";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};