#include <HTTPClient.h>
#include <WiFi.h>
#include <esp_camera.h>

#include "camera_pins.h"
#include "xiao_camera_receive_scan_id_from_main_esp32.h"
#include "xiao_camera_wifi_and_server_settings.h"

bool camera_started = false;
const char *UPLOAD_BOUNDARY = "----ASILScanBoundary8f31c2";
void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println();
  Serial.println("ASIL XIAO camera " FIRMWARE_VERSION);

  startMainEspLink();

  camera_started = startCamera();
  if (!camera_started) {
    Serial.println("the camera did not start. Check that the ribbon cable is "
                   "seated properly and that this really is the Sense version "
                   "of the board, which is the one with the camera.");
  }

  connectToWifi();

  if (camera_started && WiFi.status() == WL_CONNECTED) {
    tellMainEspCameraReady();
    Serial.println("ready, waiting for TAKE_SCAN");
  } else {
    Serial.println("NOT sending CAMERA_READY, because this board is not ready");
  }
}


bool startCamera() {
  camera_config_t config;
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
  config.xclk_freq_hz = 20000000;
  config.frame_size = FRAMESIZE_UXGA;
  config.pixel_format = PIXFORMAT_JPEG;
  config.grab_mode = CAMERA_GRAB_LATEST;
  config.fb_location = CAMERA_FB_IN_PSRAM;
  config.jpeg_quality = CAMERA_JPEG_QUALITY;
  config.fb_count = CAMERA_FRAME_BUFFERS;

  if (!psramFound()) {
    Serial.println("WARNING: no PSRAM found. Falling back to a small frame. "
                   "The laptop will probably reject these photos as too "
                   "small, and it is right to.");
    config.frame_size = FRAMESIZE_SVGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_DRAM;
  }

  esp_err_t problem = esp_camera_init(&config);
  if (problem != ESP_OK) {
    Serial.printf("camera init failed: 0x%x\n", problem);
    return false;
  }

  sensor_t *sensor = esp_camera_sensor_get();
  if (sensor != NULL) {
    sensor->set_whitebal(sensor, 0);
    sensor->set_awb_gain(sensor, 0);
    sensor->set_gain_ctrl(sensor, 0);
    sensor->set_aec2(sensor, 0);
  }

  for (int frame = 0; frame < FRAMES_TO_DISCARD_AT_STARTUP; frame++) {
    camera_fb_t *throwaway = esp_camera_fb_get();
    if (throwaway != NULL) {
      esp_camera_fb_return(throwaway);
    }
    delay(50);
  }

  Serial.println("camera ready");
  return true;
}

void loop() {
  ScanRequest request = waitForTakeScan(1000);
  if (!request.valid) {
    return;
  }

  Serial.print("TAKE_SCAN for ");
  Serial.println(request.scan_id);

  if (!camera_started) {
    tellMainEspCameraError(request.scan_id, "camera_not_started");
    return;
  }

  takePhotoAndSendIt(request);
}


void takePhotoAndSendIt(const ScanRequest &request) {
  camera_fb_t *frame = esp_camera_fb_get();
  if (frame == NULL) {
    tellMainEspCameraError(request.scan_id, "capture_failed");
    return;
  }

  tellMainEspPhotoCaptured(request.scan_id);
  Serial.printf("captured %ux%u, %u bytes\n", frame->width, frame->height,
                (unsigned)frame->len);

  bool sent = uploadPhoto(request, frame);

  esp_camera_fb_return(frame);

  if (sent) {
    tellMainEspPhotoSent(request.scan_id);
  } else {
    tellMainEspCameraError(request.scan_id, "upload_failed");
  }
}

void connectToWifi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.print("connecting to ");
  Serial.println(WIFI_NAME);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_NAME, WIFI_PASSWORD);

  unsigned long started_at = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - started_at > WIFI_CONNECT_TIMEOUT_MS) {
      Serial.println("could not connect to Wi-Fi");
      return;
    }
    delay(200);
  }

  Serial.print("connected, this board is ");
  Serial.println(WiFi.localIP().toString());
}


String buildMetadataJson(const ScanRequest &request, camera_fb_t *frame) {
  String json = "{";
  json += "\"scan_id\":\"" + request.scan_id + "\",";
  json += "\"region_id\":\"" + request.region_id + "\",";
  json += "\"x_position\":" + String(request.x_position) + ",";
  json += "\"y_position\":" + String(request.y_position) + ",";
  json += "\"timestamp\":\"" + String(millis()) + "\",";
  json += "\"camera_status\":\"ok\",";
  json += "\"image_capture_settings\":{";
  json += "\"width\":" + String(frame->width) + ",";
  json += "\"height\":" + String(frame->height) + ",";
  json += "\"format\":\"jpeg\",";
  json += "\"jpeg_quality\":" + String(CAMERA_JPEG_QUALITY);
  json += "}}";
  return json;
}


bool uploadPhoto(const ScanRequest &request, camera_fb_t *frame) {
  String metadata = buildMetadataJson(request, frame);

  String head = "--";
  head += UPLOAD_BOUNDARY;
  head += "\r\nContent-Disposition: form-data; name=\"metadata\"\r\n";
  head += "Content-Type: application/json\r\n\r\n";
  head += metadata;
  head += "\r\n--";
  head += UPLOAD_BOUNDARY;
  head += "\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"";
  head += request.scan_id;
  head += ".jpg\"\r\nContent-Type: image/jpeg\r\n\r\n";

  String tail = "\r\n--";
  tail += UPLOAD_BOUNDARY;
  tail += "--\r\n";

  size_t total = head.length() + frame->len + tail.length();

  unsigned long wait_ms = UPLOAD_BACKOFF_START_MS;
  for (int attempt = 1; attempt <= UPLOAD_MAX_ATTEMPTS; attempt++) {
    if (WiFi.status() != WL_CONNECTED) {
      connectToWifi();
    }
    uint8_t *body = (uint8_t *)malloc(total);
    if (body == NULL) {
      Serial.printf("not enough memory for a %u byte upload\n",
                    (unsigned)total);
      return false;
    }

    memcpy(body, head.c_str(), head.length());
    memcpy(body + head.length(), frame->buf, frame->len);
    memcpy(body + head.length() + frame->len, tail.c_str(), tail.length());

    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);

    bool accepted = false;
    if (http.begin(String(LAPTOP_ADDRESS) + PHOTO_UPLOAD_PATH)) {
      http.addHeader("Content-Type",
                     String("multipart/form-data; boundary=") + UPLOAD_BOUNDARY);
      if (strlen(ROBOT_SHARED_KEY) > 0) {
        http.addHeader("X-Robot-Key", ROBOT_SHARED_KEY);
      }

      int status = http.POST(body, total);
      accepted = (status == 202 || status == 200);
      if (!accepted) {
        Serial.printf("upload attempt %d got HTTP %d\n", attempt, status);
        Serial.println(http.getString());
      }
      http.end();
    }

    free(body);

    if (accepted) {
      Serial.println("photo sent");
      return true;
    }

    delay(wait_ms);
    wait_ms = wait_ms * 2;
  }

  return false;
}
