import type { APIRoute } from "astro";

import { API_URL } from "../../services/api";

/**
 * Proxy autenticado de adjuntos: el navegador pide /archivos/{id} (cookie de
 * sesión), el middleware valida, y aquí se streamea el archivo desde el
 * backend con el Bearer token. Los archivos nunca quedan expuestos públicamente.
 */
export const GET: APIRoute = async ({ params, locals }) => {
  if (!locals.user || !locals.token) return new Response("No autenticado", { status: 401 });

  const id = Number(params.id);
  if (!Number.isInteger(id) || id < 1) return new Response("Inválido", { status: 400 });

  const upstream = await fetch(`${API_URL}/api/v1/attachments/${id}/content`, {
    headers: { Authorization: `Bearer ${locals.token}` },
  }).catch(() => null);

  if (!upstream || !upstream.ok || !upstream.body) {
    return new Response("No encontrado", { status: 404 });
  }

  const headers = new Headers();
  headers.set("Content-Type", upstream.headers.get("content-type") ?? "application/octet-stream");
  const disposition = upstream.headers.get("content-disposition");
  if (disposition) headers.set("Content-Disposition", disposition);
  headers.set("Cache-Control", "private, max-age=3600");
  return new Response(upstream.body, { headers });
};