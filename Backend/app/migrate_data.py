"""Migración de datos SQLite → MySQL (u otro destino SQLAlchemy).

Uso (desde backend/):

    python -m app.migrate_data \\
        --source sqlite:///./portal.db \\
        --target "mysql+pymysql://portal:clave@localhost:3306/portal?charset=utf8mb4"

Comportamiento:
- Crea el esquema destino si no existe (create_all: equivalente a las
  migraciones 0001-0003).
- Copia users → schedule_changes → audit_logs PRESERVANDO IDs: los JWT
  emitidos llevan sub=<id> y las FK dependen de ellos. MySQL ajusta
  AUTO_INCREMENT automáticamente tras los insert con id explícito.
- Las contraseñas ya están hasheadas: se copian tal cual (nunca en claro).
- Aborta si el destino ya tiene usuarios (--force para saltar el chequeo).
"""
import argparse
import sys

from sqlalchemy import MetaData, create_engine, func, select
from sqlalchemy.orm import Session

from app.core.database import Base
import app.models  # noqa: F401  (registra la metadata)

#: Orden respetando FKs (padres primero).
TABLE_ORDER = ("users", "schedule_changes", "audit_logs")


def _connect(url: str):
    from app.core.database import _engine_kwargs

    return create_engine(url, pool_pre_ping=True, **_engine_kwargs(url))


def main() -> int:
    parser = argparse.ArgumentParser(description="Migra datos SQLite → MySQL")
    parser.add_argument("--source", default="sqlite:///./portal.db", help="URL de origen")
    parser.add_argument("--target", required=True, help="URL de destino (mysql+pymysql://…)")
    parser.add_argument("--force", action="store_true", help="Continuar aunque el destino tenga datos")
    args = parser.parse_args()

    source_engine = _connect(args.source)
    target_engine = _connect(args.target)

    try:
        source_engine.connect().close()
    except Exception as exc:
        print(f"✗ No se pudo conectar al ORIGEN ({args.source}): {exc}")
        return 1

    print("· Creando esquema en el destino (si no existe)…")
    Base.metadata.create_all(target_engine)

    with target_engine.connect() as conn:
        existing = conn.execute(select(func.count()).select_from(Base.metadata.tables["users"])).scalar()
    if existing and not args.force:
        print(f"✗ El destino ya tiene {existing} usuarios. Usa --force si estás seguro.")
        return 1
    if existing:
        print(f"· El destino ya tenía {existing} usuarios (modo --force): se añadirán los que falten…")

    migrated = {}
    with Session(source_engine) as src, Session(target_engine) as dst:
        for table_name in TABLE_ORDER:
            table = Base.metadata.tables[table_name]
            rows = [dict(row._mapping) for row in src.execute(select(table))]
            if rows:
                dst.execute(table.insert(), rows)
            migrated[table_name] = len(rows)
            print(f"  → {table_name}: {len(rows)} filas")
        dst.commit()

    # Verificación de conteos.
    print("\n· Verificación:")
    ok = True
    with Session(target_engine) as dst:
        for table_name, expected in migrated.items():
            table = Base.metadata.tables[table_name]
            actual = dst.execute(select(func.count()).select_from(table)).scalar()
            status = "✓" if actual >= expected else "✗"
            if actual < expected:
                ok = False
            print(f"  {status} {table_name}: {actual} en destino (migradas {expected})")

    print("\n✓ Migración completada." if ok else "\n✗ Migración con diferencias; revisa arriba.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())