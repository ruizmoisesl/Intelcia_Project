// <reference types="astro/client" />
import type { ApiUser} from "./services/api";
import type { Theme } from "./lib/theme";

declare global {
    namespace App {
        interface Locals {
            /** usuario autenticado (null si no hay una sesion valida) */
            user: ApiUser | nul;
            /** token JWT */
            token: string | null;

            /** Tema activo ("dark" | "light"), leído de la cookie en SSR. */
            theme: Theme;
        }
    }

    interface ImportMetaEnv {
        readonly API_URL?: string;
    }
}

export {};