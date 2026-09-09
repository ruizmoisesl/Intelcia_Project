import { defineConfig } from "astro/config";
import node from "@astrojs/node";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  // SSR: permite proteger rutas en servidor vía middleware (no es una SPA).
  output: "server",
  adapter: node({ mode: "standalone" }),
  security: {
    checkOrigin: false
  },
  server: { 
    port: 4321,
    allowedHosts: [
      'nexuscentral.infoclass.site',
      'nexusapi.infoclass.site',
      'localhost'
    ]
  },
  vite: {
    plugins: [tailwindcss()],
    server: {
      allowedHosts: [
        'nexuscentral.infoclass.site',
        'nexusapi.infoclass.site',
        'localhost'
      ]
    }
  }
});