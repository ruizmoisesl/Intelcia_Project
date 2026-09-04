import type { APIRoute } from "astro";

import { ApiError, changePassword } from "../../../services/api";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/perfil?error=Formulario%20inv%C3%A1lido");

  const current = String(form.get("current_password") ?? "");
  const next = String(form.get("new_password") ?? "");
  const confirm = String(form.get("confirm_password") ?? "");

  if (next.length < 8) {
    return redirect("/dashboard/perfil?error=La%20nueva%20contrase%C3%B1a%20debe%20tener%20al%20menos%208%20caracteres");
  }
  if (next !== confirm) {
    return redirect("/dashboard/perfil?error=Las%20contrase%C3%B1as%20no%20coinciden");
  }

  try {
    await changePassword(locals.token, current, next);
    return redirect("/dashboard/perfil?password_changed=1");
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo cambiar la contraseña";
    return redirect(`/dashboard/perfil?error=${encodeURIComponent(message)}`);
  }
};