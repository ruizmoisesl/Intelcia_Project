import type { APIRoute } from "astro";

import { ApiError, createTask } from "../../../services/api";

export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "SUPERVISOR" && locals.user.role !== "ADMIN") return redirect("/dashboard");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tareas?error=Formulario%20inv%C3%A1lido");

  const title = String(form.get("title") ?? "").trim();
  if (title.length < 3) {
    return redirect("/dashboard/tareas?error=El%20t%C3%ADtulo%20necesita%20al%20menos%203%20caracteres");
  }

  const payload: Record<string, unknown> = { title };
  const description = String(form.get("description") ?? "").trim();
  if (description) payload.description = description;

  const priority = String(form.get("priority") ?? "");
  if (["LOW", "MEDIUM", "HIGH", "URGENT"].includes(priority)) payload.priority = priority;

  const due = String(form.get("due_date") ?? "");
  if (/^\d{4}-\d{2}-\d{2}$/.test(due)) payload.due_date = due;

  const assignee = String(form.get("assignee_id") ?? "");
  if (/^\d+$/.test(assignee)) payload.assignee_id = Number(assignee);

  try {
    const task = await createTask(locals.token, payload);
    return redirect(`/dashboard/tareas/${task.id}?task_created=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo crear la tarea";
    return redirect(`/dashboard/tareas?error=${encodeURIComponent(message)}`);
  }
};