
-- Opcional: la app ya crea esta tabla sola al arrancar.
-- Solo necesitas tener creada la BASE DE DATOS "detecciones" (o el nombre que pongas en .env).
-- Si tienes problemas de conexion prueba cambiando el user y password desde query tool y coincida con el .env
ALTER USER postgres WITH PASSWORD '123';

CREATE TABLE IF NOT EXISTS detecciones (
    id         SERIAL PRIMARY KEY,
    imagen     BYTEA NOT NULL,
    fecha_hora TIMESTAMP DEFAULT NOW()
);
