import type { APIRoute } from "astro";

import { ApiError, linkJiraAccount } from "../../../services/api";

/** Vincula la cuenta de Jira del usuario actual (búsqueda por su email). */
export const POST: APIRoute = async ({ request, locals, redirect }) => {
  if (!locals.user || !locals.token) return redirect("/login");
  const form = await request.formData().catch(() => null);
  if (!form) return redirect("/dashboard/tickets?error=Formulario%20inv%C3%A1lido");
  try {
    await linkJiraAccount(locals.token);
    return redirect("/dashboard/tickets?scope=mine&jira_linked=1");
  } catch (error) {
    const message = error instanceof ApiError ? error.message : "No se pudo vincular la cuenta de Jira";
    return redirect(`/dashboard/tickets?scope=mine&error=${encodeURIComponent(message)}`);
  }
};