
## Tecnologías utilizadas

- **Hardware:** ESP32-CAM, buzzer.
- **Backend:** Python, Flask.
- **Inteligencia artificial:** YOLOv8, OpenCV.
- **Base de datos:** PostgreSQL.
- **Infraestructura:** Google Cloud Platform.
- **Comunicación:** HTTP, WebSocket.
- **Notificaciones:** API de WhatsApp.

## Arquitectura del sistema

![Arquitectura del sistema](docs/arquitectura-sistema.png)

## Circuito IoT

![Conexiones del ESP32-CAM y buzzer](docs/circuito-iot.png)

## Capturas del sistema

### Detección de agresiones

![Interfaz de detección](docs/deteccion-en-vivo.png)

### Historial de detecciones

![Registros de detecciones](docs/historial-detecciones.png)

## Instalación

### Requisitos previos

- Python compatible con las dependencias del proyecto.
- PostgreSQL, si no utilizas una instancia remota.
- Git.

### Pasos

1. Clona el repositorio:

   ```bash
   git clone URL_DE_TU_REPOSITORIO
   cd NOMBRE_DEL_REPOSITORIO
   ```

2. Crea un entorno virtual:

   ```bash
   python -m venv .venv
   ```

3. Activa el entorno virtual.

   **Windows:**

   ```powershell
   .venv\Scripts\Activate.ps1
   ```

   **Linux:**

   ```bash
   source .venv/bin/activate
   ```

4. Instala las dependencias, si el proyecto dispone de un `requirements.txt`:

   ```bash
   pip install -r requirements.txt
   ```

5. Configura las variables de entorno y la conexión a PostgreSQL según la configuración del proyecto.

6. Ejecuta la aplicación siguiendo las instrucciones de inicio de cada componente.

> Los comandos de ejecución y la configuración de la base de datos deben ajustarse a la estructura real del proyecto.
