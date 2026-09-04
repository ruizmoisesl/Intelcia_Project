import type { APIRoute } from "astro";

import { SESSION_COOKIE, SESSION_COOKIE_MAX_AGE } from "../../lib/session";
import { login } from "../../services/api";

/**
 * Recibe el formulario de /login, valida credenciales contra el backend y
 * guarda el JWT en una cookie httpOnly (el token nunca se expone al cliente).
 */
export const POST: APIRoute = async ({ request, cookies, redirect }) => {
  const formData = await request.formData().catch(() => null);
  const email = String(formData?.get("email") ?? "").trim();
  const password = String(formData?.get("password") ?? "");

  if (!email || !password) {
    return redirect("/login?error=incompleto");
  }

  try {
    const { access_token } = await login(email, password);
    cookies.set(SESSION_COOKIE, access_token, {
      path: "/",
      httpOnly: true,
      sameSite: "lax",
      maxAge: SESSION_COOKIE_MAX_AGE,
      secure: import.meta.env.PROD,
    });
    return redirect("/dashboard");
  } catch {
    return redirect("/login?error=credenciales");
  }
};