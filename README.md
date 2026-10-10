# Versión B – ESP32-CAM + servidor local

```
ESP32-CAM ──POST JPEG──▶ /video_feed ─▶ YOLOv8 ─▶ stream web + PostgreSQL local
ESP32-CAM ◀──GET── /check_aggression   (si "true" → buzzer, y WhatsApp si lo activas)
```
Es la arquitectura original, pero con el servidor en tu laptop en lugar de Google Cloud.

> ⚠️ El `.ino` de esta versión fue reescrito sin poder compilarlo ni probarlo en hardware.
> El servidor Python sí se probó. Si el compilador marca algo, revisa la sección de problemas.

## Parte 1 – Servidor (laptop)

1. **Base de datos**: en pgAdmin crea la base `detecciones` (la tabla se crea sola).
2. Copia `.env.example` como `.env` y pon `DB_USER` / `DB_PASSWORD`.
3. Instala:
   ```bash
   python -m venv venv
   venv\Scripts\activate          # Linux/Mac: source venv/bin/activate
   pip install -r requirements.txt
   ```
4. Copia tu `deteccion.pt` junto a `app.py`.
5. Ejecuta `python app.py` y abre <http://localhost:8080>.
6. **Firewall de Windows**: la primera vez permite Python en redes **privadas**
   (si no, el ESP32 no podrá conectarse). Si no apareció el aviso, crea una regla de
   entrada para el puerto 8080.
7. Obtén la IP de tu laptop: `ipconfig` → *Dirección IPv4* (ej. `192.168.1.50`).

## Parte 2 – ESP32-CAM

**Cableado** (como en tu diagrama):

| Buzzer | ESP32-CAM |
|---|---|
| `S` (señal) | GPIO 14 |
| pin central | 5V (o 3V3 si tu módulo lo soporta) |
| `-` | GND |

**Arduino IDE**
1. Instala el paquete **esp32** de Espressif (Gestor de placas).
2. Abre `firmware/esp32_cam_local/esp32_cam_local.ino`.
3. Edita el bloque *CONFIGURA ESTO*: `WIFI_SSID`, `WIFI_PASS` (WiFi de **2.4 GHz**) y
   `SERVER_IP` (la IP de la laptop del paso 7). Laptop y ESP32 deben estar en la misma red.
4. Placa: **AI Thinker ESP32-CAM**. No necesita librerías externas.
5. Para subir el código: conecta GPIO 0 a GND (modo carga), sube, quita el puente y reinicia.
6. Abre el Monitor Serie a 115200: debe mostrar "Camara OK", "WiFi OK" y dar un pitido corto.

**Probar**: en <http://localhost:8080/estado> `frames_recibidos` debe ir subiendo.
El video aparece en <http://localhost:8080>.

## Probar el servidor sin ESP32
```bash
curl -X POST -H "Content-Type: image/jpeg" --data-binary @foto.jpg http://localhost:8080/video_feed
```

## WhatsApp (opcional)
En el `.ino`: `#define ENABLE_WHATSAPP 1` y completa `CALLMEBOT_PHONE` / `CALLMEBOT_APIKEY`.
El mensaje lleva la dirección local (`http://IP:8080`), que solo abre dentro de tu red.

## Problemas frecuentes
| Síntoma | Qué revisar |
|---|---|
| `POST frame -> -1` en el Serial | `SERVER_IP` incorrecta, firewall, o distinta red / WiFi con aislamiento de clientes. |
| `frames_recibidos` en 0 | Igual que arriba; prueba abrir `http://IP_LAPTOP:8080` desde el celular. |
| No suena el buzzer | Verifica GPIO 14 y alimentación. El código genera ~2 kHz a mano (sirve para buzzer pasivo y activo). |
| `pin_sscb_sda` no compila | Cambia a `pin_sccb_sda` / `pin_sccb_scl` (nombres nuevos del core). |
| Nunca detecta | Mira las clases al arrancar `app.py` y ajusta `VIOLENCE_CLASS_ID`; baja `CONF`. |
| `/detecciones` con aviso de error | Revisa `DB_*` en `.env` y que PostgreSQL esté encendido. |
|Si el compilador marca pin_sscb_sda, cambia a pin_sccb_sda y pin_sccb_scl|