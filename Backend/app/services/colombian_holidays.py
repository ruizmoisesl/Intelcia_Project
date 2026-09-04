"""Días festivos de Colombia.

18 festivos al año según la Ley 51 de 1983 («Ley Emiliani»): los festivos de
fecha trasladable que no caen en lunes se mueven al lunes siguiente. Excepciones
que NO se mueven: los de fecha fija y Jueves/Viernes Santo.

Implementación propia (sin dependencias): Pascua vía el algoritmo de
Meeus/Jones/Butcher. Verificada con tests contra calendarios oficiales.
"""
from datetime import date, timedelta
from functools import lru_cache


@lru_cache(maxsize=64)
def easter_sunday(year: int) -> date:
    """Domingo de Pascua para el calendario gregoriano."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _next_monday(day: date) -> date:
    """Traslada la fecha al lunes siguiente si no cae en lunes (Ley Emiliani)."""
    return day + timedelta(days=(7 - day.weekday()) % 7)


# Festivos de fecha fija (sin traslado).
_FIXED: tuple[tuple[tuple[int, int], str], ...] = (
    ((1, 1), "Año Nuevo"),
    ((5, 1), "Día del Trabajo"),
    ((7, 20), "Día de la Independencia"),
    ((8, 7), "Batalla de Boyacá"),
    ((12, 8), "Inmaculada Concepción"),
    ((12, 25), "Navidad"),
)

# Festivos trasladables al lunes siguiente.
_MOVABLE: tuple[tuple[tuple[int, int], str], ...] = (
    ((1, 6), "Reyes Magos"),
    ((3, 19), "San José"),
    ((6, 29), "San Pedro y San Pablo"),
    ((8, 15), "Asunción de la Virgen"),
    ((10, 12), "Día de la Raza"),
    ((11, 1), "Todos los Santos"),
    ((11, 11), "Independencia de Cartagena"),
)


@lru_cache(maxsize=64)
def colombian_holidays(year: int) -> dict[date, str]:
    """Mapa {fecha: nombre} de los festivos de un año.

    Si dos festivos coinciden tras los traslados, se combinan los nombres
    (p. ej. el lunes 30 de junio de 2025). El diccionario devuelto NO debe
    mutarse (está cacheado).
    """
    easter = easter_sunday(year)
    holidays: dict[date, str] = {}

    def add(day: date, name: str) -> None:
        if day in holidays:
            holidays[day] = f"{holidays[day]} / {name}"
        else:
            holidays[day] = name

    for (month, day), name in _FIXED:
        add(date(year, month, day), name)
    for (month, day), name in _MOVABLE:
        add(_next_monday(date(year, month, day)), name)

    # Semana Santa y festivos móviles derivados de Pascua.
    add(easter - timedelta(days=3), "Jueves Santo")
    add(easter - timedelta(days=2), "Viernes Santo")
    add(_next_monday(easter + timedelta(days=39)), "Ascensión del Señor")
    add(_next_monday(easter + timedelta(days=60)), "Corpus Christi")
    add(_next_monday(easter + timedelta(days=68)), "Sagrado Corazón de Jesús")

    return holidays


def is_colombian_holiday(day: date) -> bool:
    return day in colombian_holidays(day.year)


def holiday_name(day: date) -> str | None:
    return colombian_holidays(day.year).get(day)