import type { APIRoute } from "astro";

import { ApiError, pushTask } from "../../../services/api";

const TARGETS = ["jira", "trello"];

/** Supervisor/admin: envía la tarea a Jira/Trello y vuelve a su ficha (ya enlazada). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  if (locals.user.role !== "SUPERVISOR" && locals.user.role !== "ADMIN") {
    return redirect("/dashboard");
  }

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tareas?error=Formulario%20inv%C3%A1lido");

  const taskId = String(form.get("task_id") ?? "");
  const target = String(form.get("target") ?? "");
  if (!/^\d+$/.test(taskId) || !TARGETS.includes(target)) {
    return redirect("/dashboard/tareas?error=Datos%20inv%C3%A1lidos");
  }

  // El push ocurre en la ficha: por defecto se vuelve a ella.
  const next = String(form.get("next") ?? `/dashboard/tareas/${taskId}`);
  const safeNext = next.startsWith("/dashboard/") ? next : `/dashboard/tareas/${taskId}`;

  try {
    await pushTask(locals.token, Number(taskId), target as "jira" | "trello");
    return redirect(`${safeNext}?task_pushed=1`);
  } catch (error) {
    // Sin credenciales o con error de la API externa → mensaje claro (fail-soft).
    const message = error instanceof ApiError ? error.message : "No se pudo enviar la tarea";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};