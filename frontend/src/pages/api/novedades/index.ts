import type { APIRoute } from "astro";

import { ApiError, createChange } from "../../../services/api";

/** Crea una novedad (empleado) o una asignación directa (admin, con user_id). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/novedades?error=Formulario%20inv%C3%A1lido");

  const weekStart = String(form.get("week_start") ?? "");
  const shift = String(form.get("requested_shift") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  const userId = String(form.get("user_id") ?? "");
  const next = String(form.get("next") ?? "/dashboard/novedades");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/novedades";

  if (!/^\d{4}-\d{2}-\d{2}$/.test(weekStart) || !shift) {
    return redirect(`${safeNext}?error=Datos%20incompletos`);
  }

  const targetUserId = /^\d+$/.test(userId) ? Number(userId) : undefined;

  try {
    await createChange(locals.token, {
      week_start: weekStart,
      requested_shift: shift,
      reason: reason || undefined,
      user_id: targetUserId,
    });
    const assigningToOther = targetUserId !== undefined && targetUserId !== locals.user.id;
    return redirect(`${safeNext}?${assigningToOther ? "assigned" : "created"}=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo registrar la novedad";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};