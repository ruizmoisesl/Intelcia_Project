v0.5 — Base de datos MySQL
Cómo usar MySQL (local)
Instala MySQL ≥ 5.7 (recomendado 8.x) y crea la BD:
CREATE DATABASE portal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;CREATE USER 'portal'@'localhost' IDENTIFIED BY 'portalpass-dev';GRANT ALL PRIVILEGES ON portal.* TO 'portal'@'localhost';
backend/.env → DATABASE_URL=mysql+pymysql://portal:portalpass-dev@localhost:3306/portal?charset=utf8mb4(si la contraseña tiene caracteres especiales, URL-encódalos).
alembic upgrade head && python -m app.seed y arranca como siempre.
Migrar datos existentes de SQLite
python -m app.migrate_data --source sqlite:///./portal.db \  --target "mysql+pymysql://portal:portalpass-dev@localhost:3306/portal?charset=utf8mb4"
Preserva IDs (los JWT activos siguen válidos), contraseñas ya hasheadas ytablas en orden de FK. Aborta si el destino ya tiene usuarios.

Docker
docker compose up --build levanta MySQL 8.4 (con healthcheck, utf8mb4 y TZUTC forzada) + backend + frontend. Los datos persisten en el volumenmysql_data.

Pruebas con MySQL real
TEST_DATABASE_URL="mysql+pymysql://portal:…@localhost:3306/portal_test?charset=utf8mb4" \  pytest tests/test_mysql_compatibility.py -v
Los tests de negocio siguen en SQLite en memoria (instantáneos); este archivovalida migraciones + tipos + UTF-8 contra MySQL de verdad. CI corre ambos.

Decisiones técnicas v0.5
PyMySQL + cryptography: puro Python (sin build deps en Docker/Windows);cryptography es necesario para caching_sha2_password (auth por defectode MySQL 8). mysqlclient descartado por sus dependencias nativas.
UTCDateTime (TypeDecorator): MySQL no guarda datetimes aware → eltipo guarda naive-UTC y devuelve aware-UTC. Uniforme para SQLite/Postgres.
La app es dueña del tiempo: created_at/updated_at ahora tienendefault Python (UTC); el servidor MySQL se fuerza a TZ UTC en Docker.No dependemos de la zona horaria del servidor de BD.
utf8mb4 en toda la cadena (URL, servidor, BD): utf8 de MySQL esde 3 bytes y rompería nombres/emojis.
pool_recycle=3600 solo para MySQL (junto al pool_pre_ping existente):evita «MySQL server has gone away» tras wait_timeout.
Alembic batch solo en SQLite: en MySQL los ALTER TABLE son nativos.
Sin migración nueva: el DDL de 0001–0003 es dialecto-agnóstico;alembic upgrade head sobre MySQL crea el esquema completo.
Requisito documentado: MySQL ≥ 5.7/8.x con InnoDB DYNAMIC (default) por elíndice único sobre email VARCHAR(255) utf8mb4.