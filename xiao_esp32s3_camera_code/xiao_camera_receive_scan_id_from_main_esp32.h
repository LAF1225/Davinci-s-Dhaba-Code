#ifndef XIAO_CAMERA_RECEIVE_SCAN_ID_FROM_MAIN_ESP32_H
#define XIAO_CAMERA_RECEIVE_SCAN_ID_FROM_MAIN_ESP32_H

#include <Arduino.h>

#include "xiao_camera_wifi_and_server_settings.h"

struct ScanRequest {
  bool valid;
  String scan_id;
  String region_id;
  int x_position;
  int y_position;
};


inline HardwareSerial &mainEspLink() {
  static HardwareSerial link(1);
  return link;
}


inline void startMainEspLink() {
  mainEspLink().begin(
      XIAO_UART_BAUD_RATE, SERIAL_8N1, XIAO_UART_RX_PIN, XIAO_UART_TX_PIN);
}


inline void tellMainEsp(const String &message) {
  mainEspLink().println(message);
}


inline void tellMainEspCameraReady() {
  tellMainEsp("CAMERA_READY");
}


inline void tellMainEspPhotoCaptured(const String &scan_id) {
  tellMainEsp("PHOTO_CAPTURED," + scan_id);
}


inline void tellMainEspPhotoSent(const String &scan_id) {
  tellMainEsp("PHOTO_SENT," + scan_id);
}


inline void tellMainEspCameraError(const String &scan_id, const String &reason) {
  tellMainEsp("CAMERA_ERROR," + scan_id + "," + reason);
}


inline String readLineFromMainEsp(unsigned long timeout_ms) {
  unsigned long started_at = millis();
  String line = "";

  while (millis() - started_at < timeout_ms) {
    while (mainEspLink().available()) {
      char character = (char)mainEspLink().read();
      if (character == '\n') {
        line.trim();
        if (line.length() > 0) {
          return line;
        }
        line = "";
      } else if (character != '\r') {
        line += character;
      }
    }
    delay(2);
  }
  return "";
}


inline ScanRequest parseTakeScan(const String &line) {
  ScanRequest request;
  request.valid = false;
  request.scan_id = "";
  request.region_id = "";
  request.x_position = 0;
  request.y_position = 0;

  if (!line.startsWith("TAKE_SCAN,")) {
    return request;
  }

  String fields[4];
  int field_number = 0;
  int start = strlen("TAKE_SCAN,");

  while (field_number < 4 && start <= line.length()) {
    int comma = line.indexOf(',', start);
    if (comma < 0) {
      fields[field_number] = line.substring(start);
      field_number++;
      break;
    }
    fields[field_number] = line.substring(start, comma);
    field_number++;
    start = comma + 1;
  }

  if (field_number < 1 || fields[0].length() == 0) {
    return request;
  }

  request.valid = true;
  request.scan_id = fields[0];
  request.region_id = fields[1];
  request.x_position = fields[2].toInt();
  request.y_position = fields[3].toInt();
  return request;
}

inline ScanRequest waitForTakeScan(unsigned long timeout_ms) {
  unsigned long started_at = millis();

  while (millis() - started_at < timeout_ms) {
    String line = readLineFromMainEsp(200);
    if (line.length() == 0) {
      continue;
    }
    if (line.startsWith("TAKE_SCAN,")) {
      return parseTakeScan(line);
    }
    Serial.print("[uart] ignoring: ");
    Serial.println(line);
  }

  ScanRequest nothing;
  nothing.valid = false;
  return nothing;
}

#endif 
