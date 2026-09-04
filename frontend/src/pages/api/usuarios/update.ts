import type { APIRoute } from "astro";

import { ApiError, updateUser } from "../../../services/api";

const ROLES = ["ADMIN", "SUPERVISOR", "EMPLOYEE"];
const SHIFTS = ["SHIFT_1", "SHIFT_2", "SHIFT_3", "SHIFT_4"];

/** ADMIN: actualiza un usuario (solo se envían los campos presentes). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "ADMIN") return redirect("/dashboard");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/usuarios?error=Formulario%20inv%C3%A1lido");

  const userId = String(form.get("user_id") ?? "");
  if (!/^\d+$/.test(userId)) return redirect("/dashboard/usuarios?error=Usuario%20inv%C3%A1lido");

  const payload: Record<string, unknown> = {};

  const name = String(form.get("name") ?? "").trim();
  if (name) payload.name = name;

  const email = String(form.get("email") ?? "").trim();
  if (email) payload.email = email;

  const password = String(form.get("password") ?? "");
  if (password) payload.password = password;

  const role = String(form.get("role") ?? "");
  if (ROLES.includes(role)) payload.role = role;

  const shift = String(form.get("shift") ?? "");
  if (SHIFTS.includes(shift)) payload.shift = shift;

  const position = String(form.get("rotation_position") ?? "").trim();
  if (/^\d+$/.test(position)) payload.rotation_position = Number(position);

  // El checkbox «activo» solo se interpreta si el formulario lo declara.
  if (form.get("has_active") !== null) {
    payload.is_active = form.get("is_active") !== null;
  }

  if (Object.keys(payload).length === 0) {
    return redirect("/dashboard/usuarios?error=No%20hay%20cambios%20que%20guardar");
  }

  try {
    await updateUser(locals.token, Number(userId), payload);
    return redirect("/dashboard/usuarios?user_updated=1");
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo actualizar el usuario";
    return redirect(`/dashboard/usuarios?error=${encodeURIComponent(message)}`);
  }
};