# -*- coding: utf-8 -*-
"""
Detección de agresiones con YOLOv8 - VERSIÓN B: servidor LOCAL para el ESP32-CAM.

    ESP32-CAM --(POST image/jpeg)--> /video_feed --> YOLOv8 --> stream web + PostgreSQL local
    ESP32-CAM <--(GET)-- /check_aggression   (si dice "true", el ESP32 hace sonar el buzzer)

Uso:   python app.py      y abrir   http://localhost:8080
"""
import logging
import os
import sys
import threading
import time

import cv2
import numpy as np
import psycopg2
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request
from ultralytics import YOLO

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

# ------------------------------------------------------------------ configuración
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "detecciones"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
    "connect_timeout": 3,
}
MODEL_PATH = os.getenv("MODEL_PATH", os.path.join(BASE_DIR, "deteccion.pt"))
CONF = float(os.getenv("CONF", "0.7"))
VIOLENCE_CLASS_ID = int(os.getenv("VIOLENCE_CLASS_ID", "1"))
PORT = int(os.getenv("PORT", "8080"))
HOLD_S = float(os.getenv("ALERT_HOLD_S", "3"))              # /check_aggression sigue en "true" este tiempo
SAVE_COOLDOWN_S = float(os.getenv("SAVE_COOLDOWN_S", "3"))  # máx. 1 captura en BD cada X s

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS detecciones (
    id         SERIAL PRIMARY KEY,
    imagen     BYTEA NOT NULL,
    fecha_hora TIMESTAMP DEFAULT NOW()
)
"""

app = Flask(__name__)
logging.getLogger("werkzeug").setLevel(logging.WARNING)  # el ESP32 consulta muy seguido; evita ruido

model = None
_estado = {"ultima_agresion": 0.0, "ultimo_guardado": 0.0, "bd_ok": False,
           "frames_recibidos": 0, "frames_procesados": 0, "ultimo_frame": 0.0}


# ------------------------------------------------------------------ base de datos
def conectar():
    return psycopg2.connect(**DB_CONFIG)


def inicializar_bd():
    """Crea la tabla si no existe. Si la BD no responde, la app sigue funcionando (sin guardar)."""
    conn = None
    try:
        conn = conectar()
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        _estado["bd_ok"] = True
        print(f"[BD] Conectado a PostgreSQL ({DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']})")
    except Exception as e:
        print("[BD] AVISO: no se pudo conectar a PostgreSQL. La detección funcionará, pero no se guardarán capturas.")
        print(f"[BD] Detalle: {e}")
    finally:
        if conn:
            conn.close()


def guardar_en_bd(jpeg_bytes):
    conn = None
    try:
        conn = conectar()
        with conn.cursor() as cur:
            cur.execute("INSERT INTO detecciones (imagen) VALUES (%s)", (psycopg2.Binary(jpeg_bytes),))
        conn.commit()
        _estado["bd_ok"] = True
    except Exception as e:
        _estado["bd_ok"] = False
        print(f"[BD] Error al guardar la detección: {e}")
    finally:
        if conn:
            conn.close()


# ------------------------------------------------------------------ detección
def analizar(frame):
    """Devuelve (frame_anotado, hay_agresion)."""
    resultados = model(frame, conf=CONF, verbose=False)
    cajas = resultados[0].boxes
    anotado = frame.copy()
    hay = False

    if cajas is not None and len(cajas):
        xyxy = cajas.xyxy.cpu().numpy().astype(int)
        clases = cajas.cls.cpu().numpy().astype(int)
        confs = cajas.conf.cpu().numpy()
        for (x1, y1, x2, y2), clase, p in zip(xyxy, clases, confs):
            if clase == VIOLENCE_CLASS_ID:
                hay = True
                cv2.rectangle(anotado, (x1, y1), (x2, y2), (0, 0, 255), 2)
                cv2.putText(anotado, f"{p:.2f}", (x1, max(y1 - 6, 14)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    if hay:
        cv2.putText(anotado, "AGRESION", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
    return anotado, hay


def registrar_agresion(frame_anotado):
    ahora = time.time()
    _estado["ultima_agresion"] = ahora
    if ahora - _estado["ultimo_guardado"] >= SAVE_COOLDOWN_S:
        _estado["ultimo_guardado"] = ahora
        ok, buf = cv2.imencode(".jpg", frame_anotado)
        if ok:
            threading.Thread(target=guardar_en_bd, args=(buf.tobytes(),), daemon=True).start()


def agresion_activa():
    return (time.time() - _estado["ultima_agresion"]) <= HOLD_S


# ------------------------------------------------------------------ cola de 1 frame + stream
# El ESP32 puede mandar más frames de los que la laptop alcanza a procesar.
# Solo se guarda el MÁS RECIENTE; los viejos se descartan (así no hay retraso acumulado).
_pendiente = {"datos": None}
_pend_lock = threading.Lock()
_pend_evento = threading.Event()

_cond = threading.Condition()
_ultimo = {"jpeg": None, "id": 0}


def publicar(frame):
    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return
    with _cond:
        _ultimo["jpeg"] = buf.tobytes()
        _ultimo["id"] += 1
        _cond.notify_all()


def bucle_deteccion():
    while True:
        _pend_evento.wait()
        with _pend_lock:
            datos = _pendiente["datos"]
            _pendiente["datos"] = None
            _pend_evento.clear()
        if datos is None:
            continue
        try:
            frame = cv2.imdecode(np.frombuffer(datos, np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                continue
            anotado, hay = analizar(frame)
            if hay:
                registrar_agresion(anotado)
            publicar(anotado)
            _estado["frames_procesados"] += 1
        except Exception as e:
            print(f"[Detección] Error procesando frame: {e}")
            time.sleep(0.2)


# ------------------------------------------------------------------ rutas web
@app.route("/video_feed", methods=["POST"])
def video_feed():
    """Aquí el ESP32-CAM sube cada frame JPEG."""
    if not (request.content_type or "").startswith("image/jpeg"):
        return "Unsupported Media Type", 415
    with _pend_lock:
        _pendiente["datos"] = request.get_data()
        _pend_evento.set()
    _estado["frames_recibidos"] += 1
    _estado["ultimo_frame"] = time.time()
    return "OK", 200


@app.route("/check_aggression")
def check_aggression():
    # Mismo formato que el original (el ESP32 busca la palabra "true")
    return jsonify({"aggression": "true" if agresion_activa() else "false"})


@app.route("/estado")
def estado():
    """Diagnóstico rápido: ¿está llegando video del ESP32? ¿responde la BD?"""
    edad = time.time() - _estado["ultimo_frame"] if _estado["ultimo_frame"] else None
    return jsonify({
        "frames_recibidos": _estado["frames_recibidos"],
        "frames_procesados": _estado["frames_procesados"],
        "segundos_desde_ultimo_frame": None if edad is None else round(edad, 1),
        "agresion": agresion_activa(),
        "bd_ok": _estado["bd_ok"],
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/stream")
def stream():
    def generar():
        ultimo_visto = -1
        while True:
            with _cond:
                cambio = _cond.wait_for(lambda: _ultimo["id"] != ultimo_visto, timeout=1.0)
                datos, ultimo_visto = _ultimo["jpeg"], _ultimo["id"]
            if not cambio or datos is None:
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + datos + b"\r\n"

    return Response(generar(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/detecciones")
def detecciones():
    filas, error = [], None
    conn = None
    try:
        conn = conectar()
        with conn.cursor() as cur:
            cur.execute("SELECT id, fecha_hora FROM detecciones ORDER BY fecha_hora DESC LIMIT 60")
            filas = cur.fetchall()
    except Exception as e:
        error = str(e)
    finally:
        if conn:
            conn.close()
    return render_template("detecciones.html", detecciones=filas, error=error)


@app.route("/imagen/<int:id>")
def imagen(id):
    conn = None
    try:
        conn = conectar()
        with conn.cursor() as cur:
            cur.execute("SELECT imagen FROM detecciones WHERE id = %s", (id,))
            fila = cur.fetchone()
        if fila:
            return Response(bytes(fila[0]), mimetype="image/jpeg")
        return "Imagen no encontrada", 404
    except Exception as e:
        return f"Error: {e}", 500
    finally:
        if conn:
            conn.close()


# ------------------------------------------------------------------ main
if __name__ == "__main__":
    if not os.path.exists(MODEL_PATH):
        sys.exit(f"[ERROR] No encuentro el modelo en: {MODEL_PATH}\n"
                 "Copia tu archivo deteccion.pt a esta carpeta (o define MODEL_PATH en .env).")

    print("[Modelo] Cargando", MODEL_PATH)
    model = YOLO(MODEL_PATH)
    print("[Modelo] Clases:", model.names, f"-> se alerta con la clase {VIOLENCE_CLASS_ID}")

    inicializar_bd()

    espera = np.zeros((480, 640, 3), np.uint8)
    cv2.putText(espera, "Esperando al ESP32-CAM...", (110, 245), cv2.FONT_HERSHEY_SIMPLEX, 1, (200, 200, 200), 2)
    publicar(espera)

    threading.Thread(target=bucle_deteccion, daemon=True).start()

    print(f"[Web] Abre http://localhost:{PORT}  |  El ESP32 debe apuntar a la IP de esta PC, puerto {PORT}")
    app.run(host="0.0.0.0", port=PORT, threaded=True)
