#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <WiFi.h>

#include "main_esp32_talk_to_xiao_camera_over_uart.h"
#include "main_esp32_wifi_and_laptop_connection_settings.h"

HardwareSerial matrixLink(2);

Preferences saved_values;
long colour_dark_reference[COLOUR_CHANNELS] = {0, 0, 0};
long colour_white_reference[COLOUR_CHANNELS] = {0, 0, 0};
bool calibration_loaded = false;

String textile_id = "UNKNOWN";
int scan_area_number = 0;
int rescans_at_this_area = 0;
int failures_in_a_row = 0;
bool run_in_progress = false;

void setup() {
  Serial.begin(115200);
  delay(300);

  Serial.println();
  Serial.println("ASIL main ESP32 " FIRMWARE_VERSION);

  startXiaoLink();
  matrixLink.begin(MATRIX_SERIAL_BAUD_RATE, SERIAL_8N1,
                   MATRIX_SERIAL_RX_PIN, MATRIX_SERIAL_TX_PIN);

  loadCalibration();
  connectToWifi();

  Serial.println("waiting for the camera board");
  if (waitForCameraReady(10000)) {
    Serial.println("camera board is ready");
  } else {
    Serial.println("WARNING: no CAMERA_READY from the XIAO. Check the UART "
                   "wiring: XIAO D6/GPIO43 goes to this board's RX, XIAO "
                   "D7/GPIO44 comes from this board's TX, and the two boards "
                   "share a ground.");
  }

  printHelp();
}


void printHelp() {
  Serial.println();
  Serial.println("Type one of these and press enter:");
  Serial.println("  dark             capture the dark reference "
                 "(sensor covered, lamp off)");
  Serial.println("  white            capture the white reference "
                 "(white card under the sensor, lamp on)");
  Serial.println("  textile <id>     set which textile is being scanned");
  Serial.println("  start            begin scanning this textile");
  Serial.println("  stop             stop after the current scan area");
  Serial.println("  status           print what this board knows");
  Serial.println();
}

void loop() {
  checkUsbSerialForCommands();

  if (!run_in_progress) {
    delay(50);
    return;
  }

  if (scan_area_number >= SCAN_AREAS_PER_TEXTILE) {
    Serial.println("all planned scan areas done");
    run_in_progress = false;
    return;
  }

  scanOneArea();
}


void scanOneArea() {
  String region_id = String("R") + String(scan_area_number);
  String scan_id = makeScanId(region_id);

  Serial.println();
  Serial.print("scan area ");
  Serial.print(scan_area_number);
  Serial.print("  scan_id ");
  Serial.println(scan_id);

  sendTakeScan(scan_id, region_id, scan_area_number, 0);

  long red = 0;
  long green = 0;
  long blue = 0;
  bool colour_ok = readColourFromMatrix(&red, &green, &blue);
  if (!colour_ok) {
    Serial.println("colour sensor did not answer");
  }

  bool uploaded = uploadSensorValues(scan_id, region_id, red, green, blue,
                                     colour_ok);
  if (!uploaded) {
    Serial.println("could not upload the sensor values");
    handleFailedArea();
    return;
  }

  int photo_state = waitForPhotoSent(scan_id, XIAO_PHOTO_TIMEOUT_MS);
  if (photo_state != 1) {
    Serial.println(photo_state == -1
                       ? "the camera reported an error"
                       : "the camera did not confirm in time");
    handleFailedArea();
    return;
  }

  String command = askLaptopForResult(scan_id);
  Serial.print("laptop says: ");
  Serial.println(command);

  if (command == "rescan") {
    rescans_at_this_area++;
    if (rescans_at_this_area > MAXIMUM_RESCANS_PER_AREA) {
      Serial.println("too many rescans here, moving on");
      rescans_at_this_area = 0;
      moveToNextArea();
    }
    return;
  }

  if (command == "complete") {
    Serial.println("the laptop says this textile is finished");
    run_in_progress = false;
    return;
  }

  rescans_at_this_area = 0;
  failures_in_a_row = 0;
  moveToNextArea();
}


void handleFailedArea() {
  failures_in_a_row++;
  if (failures_in_a_row >= CONSECUTIVE_FAILURE_LIMIT) {
    Serial.println("too many failures in a row, stopping. Type start to "
                   "carry on once the problem is fixed.");
    run_in_progress = false;
    failures_in_a_row = 0;
  }
}


void moveToNextArea() {
  if (!sendToMatrixAndWaitForDone("MOVE_NEXT", MATRIX_MOVE_TIMEOUT_MS)) {
    Serial.println("the MATRIX board did not finish the move");
    handleFailedArea();
    return;
  }
  scan_area_number++;
}

String makeScanId(const String &region_id) {
  return textile_id + "_" + region_id + "_" + String(millis());
}

String readLineFromMatrix(unsigned long timeout_ms) {
  unsigned long started_at = millis();
  String line = "";

  while (millis() - started_at < timeout_ms) {
    while (matrixLink.available()) {
      char character = (char)matrixLink.read();
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


bool sendToMatrixAndWaitForDone(const String &command, unsigned long timeout_ms) {
  matrixLink.println(command);

  unsigned long started_at = millis();
  while (millis() - started_at < timeout_ms) {
    String reply = readLineFromMatrix(500);
    if (reply.length() == 0) {
      continue;
    }
    if (reply == "DONE" || reply == "STEPPER_DONE") {
      return true;
    }
    if (reply == "MOVING") {
      continue;  // expected, keep waiting for DONE
    }
    if (reply.startsWith("ERROR")) {
      Serial.print("[matrix] ");
      Serial.println(reply);
      return false;
    }
  }
  return false;
}


bool readColourFromMatrix(long *red, long *green, long *blue) {
  matrixLink.println("READ_COLOUR");

  String reply = readLineFromMatrix(MATRIX_REPLY_TIMEOUT_MS);
  if (!reply.startsWith("COLOUR,")) {
    if (reply.length() > 0) {
      Serial.print("[matrix] ");
      Serial.println(reply);
    }
    return false;
  }

  // COLOUR,<red>,<green>,<blue>
  int first = reply.indexOf(',');
  int second = reply.indexOf(',', first + 1);
  int third = reply.indexOf(',', second + 1);
  if (second < 0 || third < 0) {
    return false;
  }

  *red = reply.substring(first + 1, second).toInt();
  *green = reply.substring(second + 1, third).toInt();
  *blue = reply.substring(third + 1).toInt();
  return true;
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


bool uploadSensorValues(const String &scan_id, const String &region_id,
                        long red, long green, long blue, bool colour_ok) {
  JsonDocument body;
  body["scan_id"] = scan_id;
  body["textile_id"] = textile_id;
  body["region_id"] = region_id;
  body["scan_index"] = scan_area_number;
  body["row_index"] = scan_area_number / 4;
  body["column_index"] = scan_area_number % 4;
  body["robot_status"] = colour_ok ? "ok" : "colour_sensor_failed";
  body["timestamp"] = String(millis());

  JsonArray channels = body["colour_sensor_values"].to<JsonArray>();
  if (colour_ok) {
    channels.add(red);
    channels.add(green);
    channels.add(blue);
  }
  if (calibration_loaded) {
    JsonArray dark = body["colour_dark_reference"].to<JsonArray>();
    JsonArray white = body["colour_white_reference"].to<JsonArray>();
    for (int channel = 0; channel < COLOUR_CHANNELS; channel++) {
      dark.add(colour_dark_reference[channel]);
      white.add(colour_white_reference[channel]);
    }
  }

  String json;
  serializeJson(body, json);

  unsigned long wait_ms = UPLOAD_BACKOFF_START_MS;
  for (int attempt = 1; attempt <= UPLOAD_MAX_ATTEMPTS; attempt++) {
    if (WiFi.status() != WL_CONNECTED) {
      connectToWifi();
    }

    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);
    if (http.begin(String(LAPTOP_ADDRESS) + SENSOR_UPLOAD_PATH)) {
      http.addHeader("Content-Type", "application/json");
      if (strlen(ROBOT_SHARED_KEY) > 0) {
        http.addHeader("X-Robot-Key", ROBOT_SHARED_KEY);
      }

      int status = http.POST(json);
      http.end();

      if (status == 200 || status == 202) {
        return true;
      }
      Serial.print("upload attempt ");
      Serial.print(attempt);
      Serial.print(" got HTTP ");
      Serial.println(status);
    }

    delay(wait_ms);
    wait_ms = min((unsigned long)UPLOAD_BACKOFF_MAX_MS, wait_ms + wait_ms / 2);
  }

  return false;
}

String askLaptopForResult(const String &scan_id) {
  unsigned long started_at = millis();
  unsigned long wait_ms = RESULT_POLL_START_DELAY_MS;

  while (millis() - started_at < RESULT_POLL_TIMEOUT_MS) {
    HTTPClient http;
    http.setTimeout(HTTP_TIMEOUT_MS);

    String url = String(LAPTOP_ADDRESS) + SCAN_RESULT_PATH + "/" + scan_id;
    if (http.begin(url)) {
      if (strlen(ROBOT_SHARED_KEY) > 0) {
        http.addHeader("X-Robot-Key", ROBOT_SHARED_KEY);
      }

      int status = http.GET();
      if (status == 200) {
        String reply = http.getString();
        http.end();

        JsonDocument parsed;
        if (deserializeJson(parsed, reply) == DeserializationError::Ok) {
          const char *state = parsed["status"] | "";
          if (String(state) == "processing"
              || String(state) == "waiting_for_the_other_half") {
            // Not ready yet. Keep waiting.
          } else {
            const char *command = parsed["command"] | "continue";
            const char *decision = parsed["decision"] | "";
            Serial.print("  decision: ");
            Serial.println(decision);
            return String(command);
          }
        }
      } else {
        http.end();
      }
    }

    delay(wait_ms);
    wait_ms = min((unsigned long)RESULT_POLL_MAX_DELAY_MS,
                  wait_ms + wait_ms / 3);
  }

  Serial.println("the laptop never answered, treating this area as a rescan");
  return "rescan";
}

void loadCalibration() {
  saved_values.begin("asil", true);
  calibration_loaded = saved_values.getBool("calibrated", false);
  if (calibration_loaded) {
    saved_values.getBytes("dark", colour_dark_reference,
                          sizeof(colour_dark_reference));
    saved_values.getBytes("white", colour_white_reference,
                          sizeof(colour_white_reference));
  }
  saved_values.end();

  if (!calibration_loaded) {
    Serial.println("NOTE: the colour sensor has never been calibrated on this "
                   "board. Run dark and white before scanning, or the laptop "
                   "will reject every reading as uncalibrated.");
  }
}


void saveCalibration() {
  saved_values.begin("asil", false);
  saved_values.putBytes("dark", colour_dark_reference,
                        sizeof(colour_dark_reference));
  saved_values.putBytes("white", colour_white_reference,
                        sizeof(colour_white_reference));
  saved_values.putBool("calibrated", true);
  saved_values.end();
  calibration_loaded = true;
}


void captureReference(bool is_dark) {
  long red = 0;
  long green = 0;
  long blue = 0;

  if (!readColourFromMatrix(&red, &green, &blue)) {
    Serial.println("the colour sensor did not answer, nothing was saved");
    return;
  }

  long *target = is_dark ? colour_dark_reference : colour_white_reference;
  target[0] = red;
  target[1] = green;
  target[2] = blue;

  if (!is_dark) {
    bool separated = true;
    for (int channel = 0; channel < COLOUR_CHANNELS; channel++) {
      if (colour_white_reference[channel] - colour_dark_reference[channel] < 100) {
        separated = false;
      }
    }
    if (!separated) {
      Serial.println("REJECTED: the white reading is not clearly brighter than "
                     "the dark one on every channel. Is the lamp on? Is the "
                     "white card actually under the sensor?");
      return;
    }
  }

  saveCalibration();
  Serial.print(is_dark ? "dark  " : "white ");
  Serial.print("reference saved: ");
  Serial.print(red);
  Serial.print(", ");
  Serial.print(green);
  Serial.print(", ");
  Serial.println(blue);
}

void checkUsbSerialForCommands() {
  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return;
  }

  if (line == "dark") {
    captureReference(true);
  } else if (line == "white") {
    captureReference(false);
  } else if (line.startsWith("textile ")) {
    textile_id = line.substring(8);
    textile_id.trim();
    Serial.print("now scanning textile ");
    Serial.println(textile_id);
  } else if (line == "start") {
    if (!calibration_loaded) {
      Serial.println("not calibrated yet. Run dark and white first.");
      return;
    }
    scan_area_number = 0;
    rescans_at_this_area = 0;
    failures_in_a_row = 0;
    run_in_progress = true;
    Serial.println("starting");
  } else if (line == "stop") {
    run_in_progress = false;
    matrixLink.println("STOP");
    Serial.println("stopping");
  } else if (line == "status") {
    printStatus();
  } else {
    printHelp();
  }
}


void printStatus() {
  Serial.println();
  Serial.print("  textile      : ");
  Serial.println(textile_id);
  Serial.print("  scan area    : ");
  Serial.print(scan_area_number);
  Serial.print(" of ");
  Serial.println(SCAN_AREAS_PER_TEXTILE);
  Serial.print("  running      : ");
  Serial.println(run_in_progress ? "yes" : "no");
  Serial.print("  Wi-Fi        : ");
  Serial.println(WiFi.status() == WL_CONNECTED
                     ? WiFi.localIP().toString()
                     : String("not connected"));
  Serial.print("  calibrated   : ");
  Serial.println(calibration_loaded ? "yes" : "no");
  if (calibration_loaded) {
    Serial.print("    dark  : ");
    for (int channel = 0; channel < COLOUR_CHANNELS; channel++) {
      Serial.print(colour_dark_reference[channel]);
      Serial.print(" ");
    }
    Serial.println();
    Serial.print("    white : ");
    for (int channel = 0; channel < COLOUR_CHANNELS; channel++) {
      Serial.print(colour_white_reference[channel]);
      Serial.print(" ");
    }
    Serial.println();
  }
  Serial.println();
}
