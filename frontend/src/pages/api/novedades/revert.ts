import type { APIRoute } from "astro";

import { ApiError, revertChange } from "../../../services/api";

/** ADMIN: quita un cambio aprobado; el usuario vuelve a la rotación/turno fijo. */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/personal?error=Formulario%20inv%C3%A1lido");

  const changeId = String(form.get("change_id") ?? "");
  const next = String(form.get("next") ?? "/dashboard/personal");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/personal";

  if (!/^\d+$/.test(changeId)) {
    return redirect(`${safeNext}?error=Datos%20inv%C3%A1lidos`);
  }

  try {
    await revertChange(locals.token, Number(changeId));
    return redirect(`${safeNext}?reverted=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo revertir el cambio";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};