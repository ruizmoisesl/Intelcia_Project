import type { APIRoute } from "astro";

import { ApiError, deleteComment } from "../../../services/api";

/** Elimina un comentario: su autor o supervisión (lo valida el backend). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");

  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tareas?error=Formulario%20inv%C3%A1lido");

  const commentId = String(form.get("comment_id") ?? "");
  if (!/^\d+$/.test(commentId)) {
    return redirect("/dashboard/tareas?error=Comentario%20inv%C3%A1lido");
  }

  const next = String(form.get("next") ?? "/dashboard/tareas");
  const safeNext = next.startsWith("/dashboard/") ? next : "/dashboard/tareas";

  try {
    await deleteComment(locals.token, Number(commentId));
    return redirect(`${safeNext}?comment_deleted=1`);
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo eliminar el comentario";
    return redirect(`${safeNext}?error=${encodeURIComponent(message)}`);
  }
};