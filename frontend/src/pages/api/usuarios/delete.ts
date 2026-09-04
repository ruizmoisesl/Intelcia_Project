import type { APIRoute } from "astro";

import { ApiError, deactivateUser } from "../../../services/api";

/** ADMIN: desactiva un usuario (borrado lógico; preserva el histórico). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "ADMIN") return redirect("/dashboard");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/usuarios?error=Formulario%20inv%C3%A1lido");

  const userId = String(form.get("user_id") ?? "");
  if (!/^\d+$/.test(userId)) return redirect("/dashboard/usuarios?error=Usuario%20inv%C3%A1lido");

  try {
    await deactivateUser(locals.token, Number(userId));
    return redirect("/dashboard/usuarios?user_deactivated=1");
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo desactivar el usuario";
    return redirect(`/dashboard/usuarios?error=${encodeURIComponent(message)}`);
  }
};