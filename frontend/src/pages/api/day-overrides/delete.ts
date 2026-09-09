import type { APIRoute } from "astro";

import { ApiError, deleteDayOverride } from "../../../services/api";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "SUPERVISOR" && locals.user.role !== "ADMIN") {
    return redirect("/dashboard");
  }

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/personal?error=Formulario%20inv%C3%A1lido");

  const overrideId = String(form.get("override_id") ?? "");
  const next = String(form.get("next") ?? "/dashboard/personal");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/personal";

  if (!/^\d+$/.test(overrideId)) {
    return redirect(`${safeNext}?error=Personalizaci%C3%B3n%20inv%C3%A1lida`);
  }

  try {
    await deleteDayOverride(locals.token, Number(overrideId));
    return redirect(`${safeNext}?day_override_removed=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo quitar la personalización";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
}