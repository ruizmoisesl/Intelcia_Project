import { defineMiddleware } from "astro:middleware";

import { SESSION_COOKIE } from "./lib/session";
import { ApiError, fetchMe } from "./services/api";
import { DEFAULT_THEME, THEME_COOKIE } from "./lib/theme";

/**
 * Protege en SERVIDOR las rutas privadas y mantiene la sesión en `locals`.
 * - /dashboard/* y /api/novedades* requieren sesión (cookie httpOnly con JWT).
 * - /login redirige a /dashboard si ya hay sesión.
 * La validación real del token la hace el backend (GET /api/v1/auth/me).
 */
export const onRequest = defineMiddleware(async ({ url, cookies, locals, redirect }, next) => {
  locals.user = null;
  locals.token = null;
  locals.theme = cookies.get(THEME_COOKIE)?.value === "light" ? "light" : DEFAULT_THEME;

  const path = url.pathname;
  const isLoginPage = path === "/login";
  const isProtectedPage = path.startsWith("/dashboard");
 const isProtectedApi = path.startsWith("/api/novedades") || path.startsWith("/api/usuarios") || path.startsWith("/api/perfil") || path.startsWith("/api/day-overrides") || path.startsWith("/api/tareas") || path.startsWith("/archivos");

  const token = cookies.get(SESSION_COOKIE)?.value ?? null;

  if (token) {
    try {
      locals.user = await fetchMe(token);
      locals.token = token;
    } catch (error) {
      if (error instanceof ApiError && (error.status === 401 || error.status === 403)) {
        cookies.delete(SESSION_COOKIE, { path: "/" });
      }
    }
  }

  if ((isProtectedPage || isProtectedApi) && !locals.user) {
    if (path.startsWith("/archivos")) {
      return new Response("No autenticado", { status: 401 });
    }
    return redirect("/login");
  }

  if (isLoginPage && locals.user) {
    return redirect("/dashboard");
  }

  return next();
});