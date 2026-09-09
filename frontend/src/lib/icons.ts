/** Iconos disponibles (las rutas SVG estan en  components/Icon.astro) */

export const ICON_NAMES = [
  "home", "calendar", "clock", "users", "clipboard", "ticket", "folder",
  "chart", "settings", "logout", "coffee", "building", "chevronLeft",
  "chevronRight", "chevronDown", "arrowDown", "bell","user","shield",
  "sun", "moon", "check"
] as const;

export type IconName = (typeof ICON_NAMES)[number];