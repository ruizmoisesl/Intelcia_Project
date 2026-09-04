"""Limitación de intentos fallidos de login (en memoria, por proceso).

- Clave: email normalizado (un atacante puede rotar IP; el email no).
- Bloqueo: tras MAX_FAILURES fallos dentro de WINDOW_SECONDS, el login se
  rechaza con 429 aunque la contraseña sea correcta, hasta que venza la
  ventana. Un login exitoso limpia el historial del email.
- Limitación conocida: estado por proceso (un worker de uvicorn). Para
  múltiples workers/instancias se necesitará Redis (futura fase).
"""
import threading
import time

MAX_FAILURES = 5
WINDOW_SECONDS = 15 * 60  # 15 minutos

_lock = threading.Lock()
_failures: dict[str, list[float]] = {}


def _prune(attempts: list[float], now: float) -> list[float]:
    return [ts for ts in attempts if now - ts < WINDOW_SECONDS]


def is_blocked(email: str) -> bool:
    key = email.strip().lower()
    with _lock:
        now = time.monotonic()
        attempts = _prune(_failures.get(key, []), now)
        _failures[key] = attempts
        return len(attempts) >= MAX_FAILURES


def record_failure(email: str) -> None:
    key = email.strip().lower()
    with _lock:
        now = time.monotonic()
        attempts = _prune(_failures.get(key, []), now)
        attempts.append(now)
        _failures[key] = attempts


def reset(email: str) -> None:
    """Limpia el historial (login exitoso)."""
    with _lock:
        _failures.pop(email.strip().lower(), None)


def reset_all() -> None:
    """Vacía todo el estado (pruebas / diagnóstico)."""
    with _lock:
        _failures.clear()