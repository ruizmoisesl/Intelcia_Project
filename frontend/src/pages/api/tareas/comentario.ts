import type { APIRoute } from "astro";

import { ApiError, createComment } from "../../../services/api";

/** Comenta una tarea (texto y/o archivos). Disponible para todos los usuarios. */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tareas?error=Formulario%20inv%C3%A1lido");

  const taskId = String(form.get("task_id") ?? "");
  if (!/^\d+$/.test(taskId)) {
    return redirect("/dashboard/tareas?error=Tarea%20inv%C3%A1lida");
  }

  const next = String(form.get("next") ?? `/dashboard/tareas/${taskId}`);
  const safeNext = next.startsWith("/dashboard/") ? next : `/dashboard/tareas/${taskId}`;

  const content = String(form.get("content") ?? "").trim();
  // File inputs vacíos llegan como entradas sin contenido: se filtran.
  const files = form
    .getAll("files")
    .filter((entry): entry is File => typeof entry !== "string" && entry.size > 0);

  if (!content && files.length === 0) {
    return redirect(`${safeNext}?error=El%20comentario%20necesita%20texto%20o%20al%20menos%20un%20archivo`);
  }

  const payload = new FormData();
  payload.set("content", content);
  for (const file of files) payload.append("files", file, file.name);

  try {
    await createComment(locals.token, Number(taskId), payload);
    return redirect(`${safeNext}?comment_created=1`);
  } catch (error) {
    // Aquí caen: tipo no permitido, >5 MB, tarea inexistente…
    const message = error instanceof ApiError ? error.message : "No se pudo publicar el comentario";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};