# Portal v0.5 — Base de Datos MySQL

## Uso con MySQL Local

### 1. Instalar MySQL

Instala **MySQL 5.7 o superior** (recomendado **MySQL 8.x**) y crea la base de datos y el usuario:

```sql
CREATE DATABASE portal
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

CREATE USER 'portal'@'localhost'
IDENTIFIED BY 'portalpass-dev';

GRANT ALL PRIVILEGES ON portal.* TO 'portal'@'localhost';

FLUSH PRIVILEGES;
```

### 2. Configurar la conexión

En `backend/.env`:

```env
DATABASE_URL=mysql+pymysql://portal:portalpass-dev@localhost:3306/portal?charset=utf8mb4
```

> Si la contraseña contiene caracteres especiales, deben codificarse mediante URL Encoding.

### 3. Crear el esquema e insertar datos demo

```bash
alembic upgrade head
python -m app.seed
```

Luego inicia la aplicación normalmente.

---

## Migrar Datos desde SQLite

Para migrar los datos existentes desde SQLite a MySQL:

```bash
python -m app.migrate_data \
  --source sqlite:///./portal.db \
  --target "mysql+pymysql://portal:portalpass-dev@localhost:3306/portal?charset=utf8mb4"
```

### Características de la migración

* Preserva los IDs existentes.
* Los JWT activos continúan siendo válidos.
* Mantiene las contraseñas ya hasheadas.
* Respeta el orden de inserción según las claves foráneas.
* Se aborta automáticamente si la base de datos destino ya contiene usuarios.

---

## Docker

Levantar todo el entorno:

```bash
docker compose up --build
```

Servicios incluidos:

* MySQL 8.4
* Backend
* Frontend

Configuración adicional:

* Healthcheck configurado.
* Codificación UTF-8 (`utf8mb4`).
* Zona horaria UTC forzada.
* Persistencia mediante el volumen:

```text
mysql_data
```

---

## Pruebas con MySQL Real

Ejecutar las pruebas de compatibilidad:

```bash
TEST_DATABASE_URL="mysql+pymysql://portal:...@localhost:3306/portal_test?charset=utf8mb4" \
pytest tests/test_mysql_compatibility.py -v
```

### Consideraciones

* Los tests de negocio continúan ejecutándose sobre SQLite en memoria para máxima velocidad.
* Este conjunto de pruebas valida:

  * Migraciones.
  * Compatibilidad de tipos.
  * Soporte UTF-8.
  * Funcionamiento real sobre MySQL.

El pipeline de CI ejecuta ambos conjuntos de pruebas.

---

# Decisiones Técnicas de la Versión 0.5

## PyMySQL + Cryptography

Se eligió:

* `PyMySQL`
* `cryptography`

Motivos:

* Implementación 100% Python.
* No requiere dependencias nativas en Docker o Windows.
* Compatible con `caching_sha2_password`, método de autenticación predeterminado de MySQL 8.

Se descartó:

* `mysqlclient`

porque requiere compilación y dependencias nativas.

---

## UTCDateTime (TypeDecorator)

MySQL no almacena correctamente fechas con información de zona horaria (*aware datetimes*).

La solución implementada:

* Guarda fechas como UTC naive.
* Devuelve fechas como UTC aware.

Ventajas:

* Comportamiento uniforme entre:

  * SQLite
  * MySQL
  * PostgreSQL

---

## La Aplicación es Dueña del Tiempo

Los campos:

* `created_at`
* `updated_at`

utilizan valores por defecto generados por Python en UTC.

Además:

* El servidor MySQL en Docker se fuerza a UTC.
* No se depende de la configuración horaria del servidor de base de datos.

---

## UTF8MB4 en Toda la Cadena

Se utiliza `utf8mb4` en:

* URL de conexión.
* Servidor MySQL.
* Base de datos.

Motivo:

El charset `utf8` de MySQL solo soporta 3 bytes y puede fallar con:

* Emojis.
* Caracteres Unicode extendidos.
* Nombres internacionales.

---

## Configuración del Pool de Conexiones

Para MySQL se configura:

```python
pool_pre_ping=True
pool_recycle=3600
```

Beneficio:

Evita errores como:

```text
MySQL server has gone away
```

provocados por el `wait_timeout` del servidor.

---

## Migraciones Alembic

### SQLite

Utiliza:

```python
batch_alter_table(...)
```

porque SQLite tiene limitaciones para modificar tablas.

### MySQL

Utiliza:

```sql
ALTER TABLE
```

de forma nativa.

---

## Sin Nuevas Migraciones

No fue necesario crear una nueva migración.

Las migraciones existentes (`0001`, `0002` y `0003`) son agnósticas al motor de base de datos.

Por lo tanto:

```bash
alembic upgrade head
```

crea correctamente todo el esquema sobre MySQL.

---

## Requisitos de MySQL

Versiones soportadas:

* MySQL 5.7+
* MySQL 8.x (recomendado)

Motor recomendado:

```text
InnoDB DYNAMIC
```

Necesario para soportar correctamente el índice único sobre:

```sql
email VARCHAR(255)
```

utilizando codificación `utf8mb4`.
