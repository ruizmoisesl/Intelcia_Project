// <reference types="astro/client" />
import type { ApiUser} from "./services/api";

declare global {
    namespace App {
        interface Locals {
            /** usuario autenticado (null si no hay una sesion valida) */
            user: ApiUser | nul;
            /** token JWT */
            token: string | null;
        }
    }

    interface ImportMetaEnv {
        readonly API_URL?: string;
    }
}

export {};