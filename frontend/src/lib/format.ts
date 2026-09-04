/**
 * Utilidades de presentación de fechas (es-*).
 *
 * Reglas anti-bug de zona horaria (v0.4):
 * 1. Las fechas de la API viajan como «YYYY-MM-DD» y se convierten a Date en
 *    UTC-midnight: TODO formateo de solo-fecha debe usar timeZone: "UTC".
 *    Si no, Intl usa la TZ del servidor y en zonas tras UTC (Bogotá, UTC-5)
 *    imprime el día anterior — el bug del «1 sep» en v0.3.
 * 2. «Hoy» NO se calcula aquí: llega desde el backend (zona horaria del
 *    negocio) dentro de las respuestas de horarios. El frontend nunca
 *    deduce la fecha actual por su cuenta.
 */

const dayMonthFmt = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  timeZone: "UTC",
});
const dayMonthYearFmt = new Intl.DateTimeFormat("es", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

export function addDaysIso(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

/** Lunes (ISO) de la semana a la que pertenece la fecha dada. */
export function mondayOfIso(iso: string): string {
  const date = parseIsoDate(iso);
  const offsetToMonday = (date.getUTCDay() + 6) % 7;
  return addDaysIso(iso, -offsetToMonday);
}

export function formatShortDate(iso: string): string {
  return dayMonthFmt.format(parseIsoDate(iso)); // «2 sep» — siempre en UTC
}

export function formatRange(startIso: string, endIso: string): string {
  const start = parseIsoDate(startIso);
  const end = parseIsoDate(endIso);
  if (start.getUTCFullYear() === end.getUTCFullYear()) {
    return `${dayMonthFmt.format(start)} — ${dayMonthYearFmt.format(end)}`;
  }
  return `${dayMonthYearFmt.format(start)} — ${dayMonthYearFmt.format(end)}`;
}