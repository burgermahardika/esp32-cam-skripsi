// C++ V2.1
#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

struct WiFiCredential {
  const char *ssid;
  const char *password;
};

WiFiCredential knownWiFi[] = {
  { "ESP32", "Dini0751" }
};
const size_t WIFI_COUNT = sizeof(knownWiFi) / sizeof(knownWiFi[0]);

bool connectToKnownWiFi(unsigned long totalTimeoutMs = 30000) {
  const unsigned long started = millis();
  while (millis() - started < totalTimeoutMs) {
    int found = WiFi.scanNetworks(false, true);
    if (found > 0) {
      for (size_t i = 0; i < WIFI_COUNT; i++) {
        bool available = false;
        for (int n = 0; n < found; n++) {
          if (WiFi.SSID(n) == knownWiFi[i].ssid) {
            available = true;
            break;
          }
        }
        if (!available)
          continue;
        WiFi.disconnect(false, false);
        delay(150);
        WiFi.begin(knownWiFi[i].ssid, knownWiFi[i].password);
        unsigned long attemptStart = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - attemptStart < 12000) {
          delay(300);
        }
        if (WiFi.status() == WL_CONNECTED) {
          WiFi.scanDelete();
          return true;
        }
      }
    }
    WiFi.scanDelete();
    delay(500);
  }
  return false;
}

#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27

#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5

#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

#define FLASH_GPIO_NUM 4

#define PART_BOUNDARY "123456789000000000000987654321"
static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;

httpd_handle_t ui_httpd = NULL;
httpd_handle_t stream_httpd = NULL;
sensor_t *cam_sensor_ptr = nullptr;

// DEFAULT SETTINGS: SVGA, Quality 14, Gain Ceiling 2x, Mirror Off, V-Flip On (1), Flash 0%
static char active_resolution[8] = "SVGA";
static int active_quality = 14;
static int active_gain_ceiling = 2;
static int active_flash = 0;
static int active_mirror = 0;
static int active_vflip = 1;

static esp_err_t stream_handler(httpd_req_t *req) {
  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK)
    return res;

  httpd_resp_set_hdr(req, "Cache-Control", "no-store, no-cache, must-revalidate, max-age=0");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");

  char part_buf[96];
  while (true) {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
      vTaskDelay(pdMS_TO_TICKS(10));
      continue;
    }
    if (fb->format != PIXFORMAT_JPEG || fb->len == 0) {
      esp_camera_fb_return(fb);
      continue;
    }

    int hlen = snprintf(part_buf, sizeof(part_buf),
                        "\r\n--" PART_BOUNDARY "\r\n"
                        "Content-Type: image/jpeg\r\n"
                        "Content-Length: %u\r\n\r\n",
                        (unsigned int)fb->len);

    res = httpd_resp_send_chunk(req, part_buf, hlen);
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)fb->buf, fb->len);
    }
    esp_camera_fb_return(fb);
    if (res != ESP_OK)
      break;
  }
  return res;
}

static esp_err_t settings_handler(httpd_req_t *req) {
  char query[180] = { 0 };
  char resolution[16] = { 0 };
  char quality_text[8] = { 0 };
  char gain_text[8] = { 0 };
  char flash_text[8] = { 0 };
  char mirror_text[8] = { 0 };
  char vflip_text[8] = { 0 };

  size_t query_len = httpd_req_get_url_query_len(req);
  if (query_len == 0) {
    int rssi = WiFi.RSSI();
    char response[210];
    snprintf(response, sizeof(response),
             "{\"ok\":true,\"resolution\":\"%s\",\"quality\":%d,\"gain_ceiling\":%d,\"flash\":%d,\"mirror\":%d,\"vflip\":%d,\"rssi\":%d}",
             active_resolution, active_quality, active_gain_ceiling, active_flash, active_mirror, active_vflip, rssi);
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, response, HTTPD_RESP_USE_STRLEN);
  }

  if (query_len >= sizeof(query) || httpd_req_get_url_query_str(req, query, sizeof(query)) != ESP_OK || httpd_query_key_value(query, "res", resolution, sizeof(resolution)) != ESP_OK || httpd_query_key_value(query, "q", quality_text, sizeof(quality_text)) != ESP_OK || httpd_query_key_value(query, "gc", gain_text, sizeof(gain_text)) != ESP_OK || httpd_query_key_value(query, "flash", flash_text, sizeof(flash_text)) != ESP_OK || httpd_query_key_value(query, "mirror", mirror_text, sizeof(mirror_text)) != ESP_OK || httpd_query_key_value(query, "vflip", vflip_text, sizeof(vflip_text)) != ESP_OK) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Parameter tidak valid");
    return ESP_FAIL;
  }

  int quality = atoi(quality_text);
  int gain = atoi(gain_text);
  int flash_percent = atoi(flash_text);
  int mirror_val = atoi(mirror_text);
  int vflip_val = atoi(vflip_text);

  if (quality < 4 || quality > 63 || cam_sensor_ptr == nullptr || flash_percent < 0 || flash_percent > 100) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Parameter di luar rentang");
    return ESP_FAIL;
  }

  int pwm_val = map(flash_percent, 0, 100, 0, 255);
  ledcWrite(FLASH_GPIO_NUM, pwm_val);
  active_flash = flash_percent;

  framesize_t size;
  if (strcmp(resolution, "HD") == 0)
    size = FRAMESIZE_HD;  // 1280x720
  else if (strcmp(resolution, "SVGA") == 0)
    size = FRAMESIZE_SVGA;  // 800x600
  else if (strcmp(resolution, "VGA") == 0)
    size = FRAMESIZE_VGA;  // 640x480
  else if (strcmp(resolution, "QVGA") == 0)
    size = FRAMESIZE_QVGA;  // 320x240
  else {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Resolusi tidak valid");
    return ESP_FAIL;
  }

  gainceiling_t gain_ceiling;
  switch (gain) {
    case 2: gain_ceiling = GAINCEILING_2X; break;
    case 4: gain_ceiling = GAINCEILING_4X; break;
    case 8: gain_ceiling = GAINCEILING_8X; break;
    case 16: gain_ceiling = GAINCEILING_16X; break;
    case 32: gain_ceiling = GAINCEILING_32X; break;
    case 64: gain_ceiling = GAINCEILING_64X; break;
    case 128: gain_ceiling = GAINCEILING_128X; break;
    default: gain_ceiling = GAINCEILING_2X; break;
  }

  int r1 = cam_sensor_ptr->set_framesize(cam_sensor_ptr, size);
  int r2 = cam_sensor_ptr->set_quality(cam_sensor_ptr, quality);
  cam_sensor_ptr->set_gainceiling(cam_sensor_ptr, gain_ceiling);
  cam_sensor_ptr->set_hmirror(cam_sensor_ptr, mirror_val);
  cam_sensor_ptr->set_vflip(cam_sensor_ptr, vflip_val);

  if (r1 != 0 || r2 != 0) {
    httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Gagal set kamera");
    return ESP_FAIL;
  }

  strlcpy(active_resolution, resolution, sizeof(active_resolution));
  active_quality = quality;
  active_gain_ceiling = gain;
  active_mirror = mirror_val;
  active_vflip = vflip_val;

  int rssi = WiFi.RSSI();
  char response[210];
  snprintf(response, sizeof(response),
           "{\"ok\":true,\"resolution\":\"%s\",\"quality\":%d,\"gain_ceiling\":%d,\"flash\":%d,\"mirror\":%d,\"vflip\":%d,\"rssi\":%d}",
           active_resolution, active_quality, active_gain_ceiling, active_flash, active_mirror, active_vflip, rssi);
  httpd_resp_set_type(req, "application/json");
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  return httpd_resp_send(req, response, HTTPD_RESP_USE_STRLEN);
}

void startCameraServer() {
  httpd_config_t ui_config = HTTPD_DEFAULT_CONFIG();
  ui_config.server_port = 80;
  ui_config.ctrl_port = 32768;

  httpd_uri_t settings_uri = {
    .uri = "/settings",
    .method = HTTP_GET,
    .handler = settings_handler,
    .user_ctx = NULL
  };

  if (httpd_start(&ui_httpd, &ui_config) == ESP_OK) {
    httpd_register_uri_handler(ui_httpd, &settings_uri);
    Serial.println("Settings server started on port 80");
  }

  httpd_config_t stream_config = HTTPD_DEFAULT_CONFIG();
  stream_config.server_port = 82;
  stream_config.ctrl_port = 32770;
  stream_config.max_open_sockets = 1;

  httpd_uri_t stream_uri = {
    .uri = "/stream",
    .method = HTTP_GET,
    .handler = stream_handler,
    .user_ctx = NULL
  };

  if (httpd_start(&stream_httpd, &stream_config) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.println("Stream server started on port 82");
  }
}

void setup() {
  Serial.begin(115200);

  ledcAttach(FLASH_GPIO_NUM, 5000, 8);
  ledcWrite(FLASH_GPIO_NUM, 0);

  camera_config_t config = {};
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;

  config.xclk_freq_hz = 16000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_SVGA;  // Default SVGA
  config.jpeg_quality = 14;

  config.fb_count = 2;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.grab_mode = CAMERA_GRAB_LATEST;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Kamera gagal diinisialisasi!");
    return;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  cam_sensor_ptr = sensor;
  if (sensor != NULL) {
    sensor->set_quality(sensor, 14);
    sensor->set_gainceiling(sensor, GAINCEILING_2X);
    sensor->set_vflip(sensor, 0);    // 0 = OV2640, 1 = OV3660
    sensor->set_hmirror(sensor, 0);  // Default Mirror OFF
  }

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  if (!connectToKnownWiFi(30000)) {
    Serial.println("Gagal terhubung ke WiFi!");
    return;
  }

  Serial.print("Alamat IP ESP32-CAM: ");
  Serial.println(WiFi.localIP());

  startCameraServer();
}

void loop() {
  delay(1000);
}