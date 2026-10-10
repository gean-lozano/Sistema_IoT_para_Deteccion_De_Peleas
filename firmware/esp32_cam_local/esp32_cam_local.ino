/*
 * ESP32-CAM (AI Thinker) -> servidor Flask LOCAL (app.py de la version B)
 *
 *  - Tarea de subida (nucleo 0): captura un frame JPEG y lo envia por POST a /video_feed
 *  - loop() (nucleo 1): pregunta a /check_aggression; si dice "true" -> buzzer (+ WhatsApp opcional)
 *
 * Placa en Arduino IDE: "AI Thinker ESP32-CAM"  (paquete "esp32" de Espressif)
 * No necesita librerias externas.
 *
 * Cableado del buzzer (como en tu diagrama):
 *     S (senal)      -> GPIO 14
 *     pin central    -> 5V   (o 3V3 si tu modulo lo soporta)
 *     -              -> GND
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "soc/soc.h"            // para desactivar el brownout
#include "soc/rtc_cntl_reg.h"

// =====================  CONFIGURA ESTO  =====================
const char* WIFI_SSID = "TU_WIFI";         // debe ser WiFi de 2.4 GHz
const char* WIFI_PASS = "TU_CLAVE_WIFI";
const char* SERVER_IP = "192.168.1.50";    // IP de tu laptop (cmd -> ipconfig -> "Direccion IPv4")
const int   SERVER_PORT = 8080;

#define ENABLE_WHATSAPP 0                  // 1 = enviar WhatsApp con CallMeBot
const char* CALLMEBOT_PHONE  = "51XXXXXXXXX";
const char* CALLMEBOT_APIKEY = "XXXXXXX";

const int BUZZER_PIN = 14;
// ============================================================

const unsigned long FRAME_INTERVAL_MS    = 100;    // max ~10 frames/s hacia la laptop
const unsigned long CHECK_INTERVAL_MS    = 300;    // cada cuanto pregunta si hay agresion
const unsigned long BEEP_MS              = 1500;   // duracion del pitido
const unsigned long BEEP_COOLDOWN_MS     = 5000;   // minimo entre pitidos
const unsigned long WHATSAPP_COOLDOWN_MS = 60000;  // minimo entre WhatsApp

// Pines de la camara: modelo AI Thinker
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

String urlFrame;
String urlCheck;

// ---------------------------------------------------------------- utilidades
void beep(unsigned long ms) {
  // Onda cuadrada de ~2 kHz hecha a mano: suena en buzzer PASIVO y tambien en uno activo.
  unsigned long fin = millis() + ms;
  while (millis() < fin) {
    digitalWrite(BUZZER_PIN, HIGH);
    delayMicroseconds(250);
    digitalWrite(BUZZER_PIN, LOW);
    delayMicroseconds(250);
  }
  digitalWrite(BUZZER_PIN, LOW);
}

String urlEncode(const String &s) {
  const char *hex = "0123456789ABCDEF";
  String out;
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (isalnum((unsigned char)c) || c == '-' || c == '_' || c == '.' || c == '~') {
      out += c;
    } else {
      out += '%';
      out += hex[((unsigned char)c) >> 4];
      out += hex[((unsigned char)c) & 0x0F];
    }
  }
  return out;
}

void enviarWhatsApp(const String &mensaje) {
  WiFiClientSecure client;
  client.setInsecure();   // CallMeBot: sin validar certificado (suficiente para este uso)
  HTTPClient http;
  String url = String("https://api.callmebot.com/whatsapp.php?phone=") + CALLMEBOT_PHONE +
               "&apikey=" + CALLMEBOT_APIKEY + "&text=" + urlEncode(mensaje);
  if (http.begin(client, url)) {
    int code = http.GET();
    Serial.printf("WhatsApp -> HTTP %d\n", code);
    http.end();
  }
}

bool agresionDetectada() {
  WiFiClient client;
  HTTPClient http;
  bool resultado = false;
  if (http.begin(client, urlCheck)) {
    http.setTimeout(1500);
    int code = http.GET();
    if (code == 200) {
      String cuerpo = http.getString();       // {"aggression":"true"}
      resultado = cuerpo.indexOf("true") >= 0;
    } else {
      Serial.printf("check_aggression -> HTTP %d\n", code);
    }
    http.end();
  }
  return resultado;
}

// ---------------------------------------------------------------- tarea: subir video
void uploadTask(void *pv) {
  WiFiClient client;
  HTTPClient http;
  for (;;) {
    if (WiFi.status() != WL_CONNECTED) {
      vTaskDelay(500 / portTICK_PERIOD_MS);
      continue;
    }
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Fallo la captura de camara");
      vTaskDelay(200 / portTICK_PERIOD_MS);
      continue;
    }
    if (http.begin(client, urlFrame)) {
      http.addHeader("Content-Type", "image/jpeg");
      http.setTimeout(2000);
      int code = http.POST(fb->buf, fb->len);
      if (code != 200) {
        Serial.printf("POST frame -> %d (%s)\n", code, http.errorToString(code).c_str());
        vTaskDelay(300 / portTICK_PERIOD_MS);
      }
      http.end();
    }
    esp_camera_fb_return(fb);
    vTaskDelay(FRAME_INTERVAL_MS / portTICK_PERIOD_MS);
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);   // desactiva el brownout detector
  Serial.begin(115200);
  Serial.println();

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk  = XCLK_GPIO_NUM;
  config.pin_pclk  = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href  = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn  = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = FRAMESIZE_VGA;          // 640x480

  if (psramFound()) {
    config.jpeg_quality = 10;
    config.fb_count     = 2;
    config.fb_location  = CAMERA_FB_IN_PSRAM;
    config.grab_mode    = CAMERA_GRAB_LATEST;   // siempre el frame mas nuevo
  } else {
    config.jpeg_quality = 12;
    config.fb_count     = 1;
    config.fb_location  = CAMERA_FB_IN_DRAM;
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Fallo al iniciar la camara: 0x%x. Reiniciando...\n", err);
    delay(1000);
    ESP.restart();
  }

  // Los ajustes del sensor van DESPUES de esp_camera_init()
  sensor_t *s = esp_camera_sensor_get();
  if (s) {
    s->set_brightness(s, 1);
    s->set_saturation(s, -1);
  }
  Serial.println("Camara OK");

  urlFrame = String("http://") + SERVER_IP + ":" + SERVER_PORT + "/video_feed";
  urlCheck = String("http://") + SERVER_IP + ":" + SERVER_PORT + "/check_aggression";

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Conectando a WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println();
  Serial.print("WiFi OK. IP del ESP32: ");
  Serial.println(WiFi.localIP());
  Serial.println("Enviando video a: " + urlFrame);

  beep(150);   // un pitido corto = "arranque correcto" (prueba tambien el buzzer)

  xTaskCreatePinnedToCore(uploadTask, "uploadTask", 12288, NULL, 1, NULL, 0);
}

void loop() {
  static unsigned long ultimaConsulta = 0;
  static unsigned long ultimoBeep = 0;
  static unsigned long ultimoWhatsApp = 0;
  static bool yaPito = false;
  static bool yaWhatsApp = false;

  unsigned long ahora = millis();

  if (WiFi.status() == WL_CONNECTED && ahora - ultimaConsulta >= CHECK_INTERVAL_MS) {
    ultimaConsulta = ahora;

    if (agresionDetectada()) {
      Serial.println("AGRESION detectada");

      if (!yaPito || millis() - ultimoBeep >= BEEP_COOLDOWN_MS) {
        beep(BEEP_MS);
        ultimoBeep = millis();
        yaPito = true;
      }

#if ENABLE_WHATSAPP
      if (!yaWhatsApp || millis() - ultimoWhatsApp >= WHATSAPP_COOLDOWN_MS) {
        enviarWhatsApp(String("AGRESION DETECTADA. Revisa: http://") + SERVER_IP + ":" + SERVER_PORT);
        ultimoWhatsApp = millis();
        yaWhatsApp = true;
      }
#endif
    }
  }
  delay(10);
}
