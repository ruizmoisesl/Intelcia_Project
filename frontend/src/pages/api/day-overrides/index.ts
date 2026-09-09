import type { APIRoute } from "astro";

import { ApiError, createDayOverride } from "../../../services/api";

const SHIFTS = ["SHIFT_1", "SHIFT_2", "SHIFT_3", "SHIFT_4"];

/** SUPERVISOR/ADMIN: personaliza un día (turno de un día u horas exactas). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "SUPERVISOR" && locals.user.role !== "ADMIN") {
    return redirect("/dashboard");
  }

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/personal?error=Formulario%20inv%C3%A1lido");

  const userId = String(form.get("user_id") ?? "");
  const day = String(form.get("date") ?? "");
  const shift = String(form.get("shift") ?? "");
  const start = String(form.get("start") ?? "");
  const end = String(form.get("end") ?? "");
  const reason = String(form.get("reason") ?? "").trim();
  const next = String(form.get("next") ?? "/dashboard/personal");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/personal";

  if (!/^\d+$/.test(userId) || !/^\d{4}-\d{2}-\d{2}$/.test(day)) {
    return redirect(`${safeNext}?error=Datos%20incompletos%20o%20inv%C3%A1lidos`);
  }

  const hasShift = SHIFTS.includes(shift);
  const hasHours = start !== "" && end !== "";
  if (hasShift === hasHours) {
    return redirect(`${safeNext}?error=Indica%20un%20turno%2C%20o%20una%20hora%20de%20inicio%20y%20fin`);
  }

  const payload: Record<string, unknown> = {
    user_id: Number(userId),
    date: day,
    reason: reason || undefined,
  };
  if (hasShift) payload.shift = shift;
  else {
    payload.start = start;
    payload.end = end;
  }

  try {
    await createDayOverride(locals.token, payload as Parameters<typeof createDayOverride>[1]);
    return redirect(`${safeNext}?day_override=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo personalizar el día";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};