import type { APIRoute } from "astro";

import { ApiError, createUser } from "../../../services/api";

const ROLES = ["ADMIN", "SUPERVISOR", "EMPLOYEE"];
const SHIFTS = ["SHIFT_1", "SHIFT_2", "SHIFT_3", "SHIFT_4"];

/** ADMIN: crea un usuario. El backend valida duplicados y enums. */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "ADMIN") return redirect("/dashboard");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/usuarios?error=Formulario%20inv%C3%A1lido");

  const name = String(form.get("name") ?? "").trim();
  const email = String(form.get("email") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const role = String(form.get("role") ?? "");
  const shift = String(form.get("shift") ?? "");
  const position = String(form.get("rotation_position") ?? "").trim();
  const isActive = form.get("is_active") !== null;

  if (!name || !email || !password || !ROLES.includes(role) || !SHIFTS.includes(shift)) {
    return redirect("/dashboard/usuarios?error=Datos%20incompletos%20o%20inv%C3%A1lidos");
  }

  const payload: Record<string, unknown> = { name, email, password, role, shift, is_active: isActive };
  if (/^\d+$/.test(position)) payload.rotation_position = Number(position);

  try {
    await createUser(locals.token, payload);
    return redirect("/dashboard/usuarios?user_created=1");
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo crear el usuario";
    return redirect(`/dashboard/usuarios?error=${encodeURIComponent(message)}`);
  }
};