// Settings for the main ESP32: the network, the laptop, and both serial links.
//
// The Wi-Fi name and password are NOT in this file. They live in
// wifi_credentials.h, which is in .gitignore, so a password cannot be
// committed by accident. Copy wifi_credentials_example.h to
// wifi_credentials.h and edit that.

#ifndef MAIN_ESP32_WIFI_AND_LAPTOP_CONNECTION_SETTINGS_H
#define MAIN_ESP32_WIFI_AND_LAPTOP_CONNECTION_SETTINGS_H

#include "wifi_credentials.h"

#define ROBOT_NAME "ASIL_MAIN"
#define FIRMWARE_VERSION "1.0.0"

#define SENSOR_UPLOAD_PATH "/api/v1/scan_sensors"
#define SCAN_RESULT_PATH   "/api/v1/scan_result"

#define WIFI_CONNECT_TIMEOUT_MS 20000
#define WIFI_RETRY_DELAY_MS 3000

#define HTTP_TIMEOUT_MS 15000

#define UPLOAD_MAX_ATTEMPTS 5
#define UPLOAD_BACKOFF_START_MS 800
#define UPLOAD_BACKOFF_MAX_MS 12000

#define RESULT_POLL_START_DELAY_MS 400
#define RESULT_POLL_MAX_DELAY_MS 2000
#define RESULT_POLL_TIMEOUT_MS 180000

#define XIAO_UART_RX_PIN 0   
#define XIAO_UART_TX_PIN 0   
#define XIAO_UART_BAUD_RATE 115200
#define XIAO_PHOTO_TIMEOUT_MS 20000
#define MATRIX_SERIAL_RX_PIN 0
#define MATRIX_SERIAL_TX_PIN 0
#define MATRIX_SERIAL_BAUD_RATE 115200
#define MATRIX_MOVE_TIMEOUT_MS 15000
#define MATRIX_REPLY_TIMEOUT_MS 3000
#define COLOUR_CHANNELS 3
#define SCAN_AREAS_PER_TEXTILE 5
#define MAXIMUM_RESCANS_PER_AREA 2

#define CONSECUTIVE_FAILURE_LIMIT 3

#endif  
