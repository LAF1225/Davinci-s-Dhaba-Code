// Settings for the main ESP32: the network, the laptop, and both serial links.
//
// The Wi-Fi name and password are NOT in this file. They live in
// wifi_credentials.h, which is in .gitignore, so a password cannot be
// committed by accident. Copy wifi_credentials_example.h to
// wifi_credentials.h and edit that.

#ifndef MAIN_ESP32_WIFI_AND_LAPTOP_CONNECTION_SETTINGS_H
#define MAIN_ESP32_WIFI_AND_LAPTOP_CONNECTION_SETTINGS_H

#include "wifi_credentials.h"

// ---------------------------------------------------------------------------
// This board
// ---------------------------------------------------------------------------

#define ROBOT_NAME "ASIL_MAIN"
#define FIRMWARE_VERSION "1.0.0"


// ---------------------------------------------------------------------------
// Talking to the laptop
// ---------------------------------------------------------------------------

// Paths on the laptop server. They match scan_command_words.py; change them in
// both places or not at all.
#define SENSOR_UPLOAD_PATH "/api/v1/scan_sensors"
#define SCAN_RESULT_PATH   "/api/v1/scan_result"

#define WIFI_CONNECT_TIMEOUT_MS 20000
#define WIFI_RETRY_DELAY_MS 3000

#define HTTP_TIMEOUT_MS 15000

// Uploading the sensor values is retried before the robot gives up on a scan
// area, with a growing wait between tries so a busy laptop is not hammered.
#define UPLOAD_MAX_ATTEMPTS 5
#define UPLOAD_BACKOFF_START_MS 800
#define UPLOAD_BACKOFF_MAX_MS 12000

// How long to keep asking the laptop for the result of one scan area. DINOv2
// on a laptop CPU takes a few seconds, and the first scan after start up takes
// longer because the model is still loading.
#define RESULT_POLL_START_DELAY_MS 400
#define RESULT_POLL_MAX_DELAY_MS 2000
#define RESULT_POLL_TIMEOUT_MS 180000


// ---------------------------------------------------------------------------
// The UART link down to the XIAO camera board
// ---------------------------------------------------------------------------
// The XIAO side of this link is confirmed and must not be changed:
//     XIAO D6 / GPIO43 is its TX  ->  arrives at this board's RX
//     XIAO D7 / GPIO44 is its RX  <-  driven by this board's TX
//     GND to GND
//
// MUST BE CONFIRMED: which pins on THIS board those two wires are in. Read
// them off the robot. They are not recorded anywhere in the previous
// repository, because the previous robot had no separate camera board.
#define XIAO_UART_RX_PIN 0   // this board receives here, from XIAO GPIO43
#define XIAO_UART_TX_PIN 0   // this board sends from here, to XIAO GPIO44

// MUST BE CONFIRMED. Has to match XIAO_UART_BAUD_RATE in the XIAO sketch and
// main_esp32_to_xiao_uart_baud_rate in settings.json. 115200 is a sensible
// starting point for short coordination messages.
#define XIAO_UART_BAUD_RATE 115200

// How long to wait for the XIAO to say it has sent its photo before giving up
// on this scan area and asking for a rescan.
#define XIAO_PHOTO_TIMEOUT_MS 20000


// ---------------------------------------------------------------------------
// The serial link down to the MATRIX Arduino
// ---------------------------------------------------------------------------
// MUST BE CONFIRMED: which pins on this board, and check the logic levels.
// If the MATRIX board drives its serial line at 5 V, its TX must go through a
// divider or a level shifter before reaching this board's RX pin.
#define MATRIX_SERIAL_RX_PIN 0
#define MATRIX_SERIAL_TX_PIN 0

// MUST match MATRIX_SERIAL_BAUD_RATE in motor_and_stepper_settings.h.
#define MATRIX_SERIAL_BAUD_RATE 115200

// Moving between two scan areas should take well under this. Longer means
// something is stuck.
#define MATRIX_MOVE_TIMEOUT_MS 15000
#define MATRIX_REPLY_TIMEOUT_MS 3000


// ---------------------------------------------------------------------------
// The colour sensor reading that comes up from the MATRIX board
// ---------------------------------------------------------------------------

// Red, green, blue. Must match COLOUR_SENSOR_CHANNEL_COUNT on the MATRIX side
// and COLOUR_SENSOR_CHANNEL_COUNT in ai_settings_and_thresholds.py, and the
// order must be the same in all three places.
#define COLOUR_CHANNELS 3


// ---------------------------------------------------------------------------
// The scan plan
// ---------------------------------------------------------------------------

// How many scan areas make up one textile. Must match
// number_of_regions_per_textile in settings.json, or the laptop and the robot
// will disagree about when the textile is finished.
#define SCAN_AREAS_PER_TEXTILE 5

// A single area is never rescanned more than this many times, so one
// permanently damaged patch cannot stall the whole run.
#define MAXIMUM_RESCANS_PER_AREA 2

// After this many scan areas fail in a row, stop and wait for a person.
#define CONSECUTIVE_FAILURE_LIMIT 3

#endif  // MAIN_ESP32_WIFI_AND_LAPTOP_CONNECTION_SETTINGS_H
