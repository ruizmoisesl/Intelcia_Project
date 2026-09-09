import type { APIRoute } from "astro";

import { ApiError, deleteTask } from "../../../services/api";

/** Supervisor/admin: elimina la tarea (su historial y comentarios van en cascada) y vuelve al tablero. */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "SUPERVISOR" && locals.user.role !== "ADMIN") {
    return redirect("/dashboard");
  }

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tareas?error=Formulario%20inv%C3%A1lido");

  const taskId = String(form.get("task_id") ?? "");
  if (!/^\d+$/.test(taskId)) {
    return redirect("/dashboard/tareas?error=Tarea%20inv%C3%A1lida");
  }

  try {
    await deleteTask(locals.token, Number(taskId));
    return redirect("/dashboard/tareas?task_deleted=1");
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo eliminar la tarea";
    return redirect(`/dashboard/tareas?error=${encodeURIComponent(message)}`);
  }
};