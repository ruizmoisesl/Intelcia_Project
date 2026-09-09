"""Crea usuarios de demostración. Uso:  python -m app.seed  (idempotente)."""
from datetime import date

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, ShiftId, User
from app.services import rotation_service
from app.services.schedule_service import to_monday


DEMO_PASSWORD = "Demo1234!"

# (nombre, email, rol, turno base, activo, posición de rotación)
DEMO_USERS = [
    ("Moisés Administrador", "admin@empresa.com", Role.ADMIN, ShiftId.SHIFT_1, True, None),
    ("Sofía Supervisora", "supervisor@empresa.com", Role.SUPERVISOR, ShiftId.SHIFT_2, True, None),
    ("Ana Empleada", "empleado1@empresa.com", Role.EMPLOYEE, ShiftId.SHIFT_1, True, 1),
    ("Luis Empleado", "empleado2@empresa.com", Role.EMPLOYEE, ShiftId.SHIFT_2, True, 2),
    ("Carla Empleado", "empleado3@empresa.com", Role.EMPLOYEE, ShiftId.SHIFT_3, True, 3),
    ("Pedro Empleado", "empleado4@empresa.com", Role.EMPLOYEE, ShiftId.SHIFT_4, True, 4),
    ("Marta Inactiva", "inactivo@empresa.com", Role.EMPLOYEE, ShiftId.SHIFT_1, False, None),
]


def main() -> None:
    with SessionLocal() as db:
        for name, email, role, shift, is_active, position in DEMO_USERS:
            exists = db.scalars(select(User).where(User.email == email)).first()
            if exists:
                print(f"  = {email} ya existe, se omite")
                continue
            db.add(
                User(
                    name=name, email=email, role=role, shift=shift,
                    is_active=is_active, rotation_position=position,
                    password_hash=hash_password(DEMO_PASSWORD),
                )
            )
            print(f"  + {email} ({role.value}, base {shift.value})")

        # Backfill de posiciones para bases v0.1 ya existentes.
        employees = db.scalars(
            select(User)
            .where(User.role == Role.EMPLOYEE, User.is_active.is_(True))
            .order_by(User.id)
        ).all()
        next_position = max((e.rotation_position or 0 for e in employees), default=0)
        for employee in employees:
            if employee.rotation_position is None:
                next_position += 1
                employee.rotation_position = next_position
                print(f"  ~ {employee.email}: posición de rotación {next_position}")
        db.commit()

        print("\nRotación de la semana actual (empleados):")
        monday = to_monday(date.today())
        for employee in rotation_service.get_rotating_employees(db):
            effective = rotation_service.get_effective_shift(db, employee, monday)
            print(f"  {employee.name:<22} {effective.shift_id.value:<9} ({effective.source.value})")

    print(f"\nContraseña de los usuarios demo: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()