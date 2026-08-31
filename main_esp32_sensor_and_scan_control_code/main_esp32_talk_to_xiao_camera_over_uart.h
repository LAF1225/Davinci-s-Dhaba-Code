#ifndef MAIN_ESP32_TALK_TO_XIAO_CAMERA_OVER_UART_H
#define MAIN_ESP32_TALK_TO_XIAO_CAMERA_OVER_UART_H

#include <Arduino.h>

#include "main_esp32_wifi_and_laptop_connection_settings.h"
inline HardwareSerial &xiaoLink() {
  static HardwareSerial link(1);
  return link;
}


inline void startXiaoLink() {
  xiaoLink().begin(
      XIAO_UART_BAUD_RATE, SERIAL_8N1, XIAO_UART_RX_PIN, XIAO_UART_TX_PIN);
}


inline String readLineFromXiao(unsigned long timeout_ms) {
  unsigned long started_at = millis();
  String line = "";

  while (millis() - started_at < timeout_ms) {
    while (xiaoLink().available()) {
      char character = (char)xiaoLink().read();
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


inline bool waitForCameraReady(unsigned long timeout_ms) {
  unsigned long started_at = millis();
  while (millis() - started_at < timeout_ms) {
    String line = readLineFromXiao(500);
    if (line == "CAMERA_READY") {
      return true;
    }
  }
  return false;
}

inline void sendTakeScan(const String &scan_id, const String &region_id,
                         int x_position, int y_position) {
  xiaoLink().print("TAKE_SCAN,");
  xiaoLink().print(scan_id);
  xiaoLink().print(",");
  xiaoLink().print(region_id);
  xiaoLink().print(",");
  xiaoLink().print(x_position);
  xiaoLink().print(",");
  xiaoLink().println(y_position);
}

inline int waitForPhotoSent(const String &scan_id, unsigned long timeout_ms) {
  unsigned long started_at = millis();

  while (millis() - started_at < timeout_ms) {
    String line = readLineFromXiao(500);
    if (line.length() == 0) {
      continue;
    }

    if (line.startsWith("PHOTO_SENT,")) {
      String reported_id = line.substring(strlen("PHOTO_SENT,"));
      reported_id.trim();
      if (reported_id == scan_id) {
        return 1;
      }
      Serial.print("[xiao] ignoring PHOTO_SENT for a different scan: ");
      Serial.println(reported_id);
      continue;
    }

    if (line.startsWith("CAMERA_ERROR")) {
      Serial.print("[xiao] camera error: ");
      Serial.println(line);
      return -1;
    }

    if (line.startsWith("PHOTO_CAPTURED")) {
      // Useful to see, but the photo is not on the laptop yet, so keep waiting.
      Serial.println("[xiao] photo captured, uploading");
      continue;
    }
  }

  return 0;
}

#endif  
