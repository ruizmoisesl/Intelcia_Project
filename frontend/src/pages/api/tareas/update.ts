import type { APIRoute } from "astro";

import { ApiError, updateTask } from "../../../services/api";

const PRIORITIES = ["LOW", "MEDIUM", "HIGH", "URGENT"];
const STATUSES = ["PENDING", "IN_PROGRESS", "DONE"];

/**
 * Actualiza una tarea (solo los campos presentes) o cambia su estado.
 * Los permisos los aplica el backend:
 * - Empleado: solo el ESTADO de SUS tareas y solo avanzando
 *   (Pendiente → En proceso → Completada).
 * - Supervisor/admin: todos los campos y cualquier transición.
 */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tareas?error=Formulario%20inv%C3%A1lido");

  const taskId = String(form.get("task_id") ?? "");
  if (!/^\d+$/.test(taskId)) {
    return redirect("/dashboard/tareas?error=Tarea%20inv%C3%A1lida");
  }

  const next = String(form.get("next") ?? "/dashboard/tareas");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/tareas";

  const payload: Record<string, unknown> = {};

  // Título: obligatorio si viene (el formulario de edición siempre lo envía;
  // los botones de estado del empleado no lo envían).
  if (form.has("title")) {
    const title = String(form.get("title") ?? "").trim();
    if (title.length < 3) {
      return redirect(`${safeNext}?error=El%20t%C3%ADtulo%20necesita%20al%20menos%203%20caracteres`);
    }
    payload.title = title;
  }

  // Descripción: presente → se envía (vacía = null, limpia la descripción).
  if (form.has("description")) {
    payload.description = String(form.get("description") ?? "").trim() || null;
  }

  const priority = String(form.get("priority") ?? "");
  if (PRIORITIES.includes(priority)) payload.priority = priority;

  const status = String(form.get("status") ?? "");
  if (STATUSES.includes(status)) payload.status = status;

  // Fecha límite: válida → fecha; presente y vacía → null (quita la fecha).
  // Los botones de estado no envían este campo: no lo tocan.
  if (form.has("due_date")) {
    const due = String(form.get("due_date") ?? "");
    if (/^\d{4}-\d{2}-\d{2}$/.test(due)) payload.due_date = due;
    else if (due === "") payload.due_date = null;
  }

  // Asignación: presente con id → asignar; presente vacía → null (desasignar).
  // CRÍTICO usar has(): los formularios de estado del empleado no incluyen
  // este campo y NO deben desasignar la tarea por accidente.
  if (form.has("assignee_id")) {
    const assignee = String(form.get("assignee_id") ?? "");
    payload.assignee_id = /^\d+$/.test(assignee) ? Number(assignee) : null;
  }

  if (Object.keys(payload).length === 0) {
    return redirect(`${safeNext}?error=No%20hay%20cambios%20que%20guardar`);
  }

  try {
    await updateTask(locals.token, Number(taskId), payload);
    return redirect(`${safeNext}?task_updated=1`);
  } catch (error) {
    // Aquí caen los 403 del backend: "Solo puedes avanzar el estado…",
    // "Solo puedes cambiar el estado de tus tareas", etc. → se muestran como flash.
    const message = error instanceof ApiError ? error.message : "No se pudo actualizar la tarea";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};