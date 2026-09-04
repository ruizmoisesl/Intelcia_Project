/** Tokens de color de turnos (verde/azul/rojo/amarillo/morado) → clases Tailwind.
 *  Los tokens llegan desde la API; aquí solo se mapean a estilos de presentación. */

import type { ShiftColor } from "../services/api";

export interface ShiftStyle {
  badge: string;
  card: string;
  time: string;
  chip: string;
  dot: string;
}

const STYLES: Record<ShiftColor, ShiftStyle> = {
  green: {
    badge: "bg-emerald-100 text-emerald-800 ring-1 ring-inset ring-emerald-600/30",
    card: "border-emerald-300 bg-emerald-50",
    time: "text-emerald-900",
    chip: "bg-emerald-500",
    dot: "bg-emerald-500",
  },
  blue: {
    badge: "bg-sky-100 text-sky-800 ring-1 ring-inset ring-sky-600/30",
    card: "border-sky-300 bg-sky-50",
    time: "text-sky-900",
    chip: "bg-sky-500",
    dot: "bg-sky-500",
  },
  red: {
    badge: "bg-red-100 text-red-800 ring-1 ring-inset ring-red-600/30",
    card: "border-red-300 bg-red-50",
    time: "text-red-900",
    chip: "bg-red-500",
    dot: "bg-red-500",
  },
  yellow: {
    badge: "bg-amber-100 text-amber-900 ring-1 ring-inset ring-amber-600/30",
    card: "border-amber-300 bg-amber-50",
    time: "text-amber-900",
    chip: "bg-amber-500",
    dot: "bg-amber-500",
  },
  purple: {
    badge: "bg-violet-100 text-violet-800 ring-1 ring-inset ring-violet-600/30",
    card: "border-violet-300 bg-violet-50",
    time: "text-violet-900",
    chip: "bg-violet-500",
    dot: "bg-violet-500",
  },
};

const FALLBACK: ShiftStyle = {
  badge: "bg-slate-100 text-slate-700 ring-1 ring-inset ring-slate-500/30",
  card: "border-slate-200 bg-white",
  time: "text-slate-900",
  chip: "bg-slate-400",
  dot: "bg-slate-400",
};

export function shiftStyle(color: string | null | undefined): ShiftStyle {
  return color && color in STYLES ? STYLES[color as ShiftColor] : FALLBACK;
}