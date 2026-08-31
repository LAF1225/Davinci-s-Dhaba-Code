#include "motor_and_stepper_settings.h"
int scan_index = 0;
int row_index = 0;
int column_index = 0;
const int SCAN_AREAS_PER_ROW = 4;
bool stop_requested = false;
long stepper_position_from_parked = 0;
void setup() {
  Serial.begin(MATRIX_SERIAL_BAUD_RATE);
  Serial.setTimeout(SERIAL_READ_TIMEOUT_MS);

  setupMotors();
  setupStepper();
  setupColourSensor();

  Serial.println("READY");
}
void loop() {
  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return;
  }

  handleCommand(line);
}

void handleCommand(const String &line) {
  String command = line;
  String arguments = "";

  int comma = line.indexOf(',');
  if (comma >= 0) {
    command = line.substring(0, comma);
    arguments = line.substring(comma + 1);
  }

  if (command == "MOVE_NEXT") {
    moveToNextScanArea();
  } else if (command == "MOVE_FORWARD") {
    moveOneStep(1, 0);
  } else if (command == "MOVE_BACK") {
    moveOneStep(-1, 0);
  } else if (command == "MOVE_LEFT") {
    moveOneStep(0, -1);
  } else if (command == "MOVE_RIGHT") {
    moveOneStep(0, 1);
  } else if (command == "STOP") {
    stopAllMotors();
    Serial.println("DONE");
  } else if (command == "POSITION") {
    reportPosition();
  } else if (command == "READ_COLOUR") {
    reportColourReading();
  } else if (command == "ADJUST_STEPPER") {
    adjustScanAxis(arguments);
  } else {
    Serial.print("ERROR,unknown_command_");
    Serial.println(command);
  }
}

void moveToNextScanArea() {
  bool at_end_of_row = (column_index >= SCAN_AREAS_PER_ROW - 1);

  bool ok;
  if (at_end_of_row) {
    // Step down to the next row and turn around.
    ok = travelOneScanSpacing(1, 0);
    if (ok) {
      row_index = row_index + 1;
      column_index = 0;
    }
  } else {
    int sideways = (row_index % 2 == 0) ? 1 : -1;
    ok = travelOneScanSpacing(0, sideways);
    if (ok) {
      column_index = column_index + 1;
    }
  }

  if (!ok) {
    return;  
  }

  scan_index = scan_index + 1;
  Serial.println("DONE");
}


void moveOneStep(int forward, int sideways) {
  if (travelOneScanSpacing(forward, sideways)) {
    Serial.println("DONE");
  }
}

bool travelOneScanSpacing(int forward, int sideways) {
  if (ENCODER_COUNTS_PER_WHEEL_TURN <= 0 || WHEEL_DIAMETER_MM <= 0.0f
      || DISTANCE_BETWEEN_SCAN_AREAS_MM <= 0.0f) {
    Serial.println("ERROR,encoder_and_wheel_settings_not_measured_yet");
    return false;
  }

  Serial.println("MOVING");
  stop_requested = false;

  float wheel_circumference_mm = 3.14159265f * WHEEL_DIAMETER_MM;
  float turns_needed = DISTANCE_BETWEEN_SCAN_AREAS_MM / wheel_circumference_mm;
  long counts_needed = (long)(turns_needed * ENCODER_COUNTS_PER_WHEEL_TURN);

  resetEncoderCounts();
  driveMecanum(forward, sideways, TRAVEL_MOTOR_POWER_PERCENT);

  unsigned long started_at = millis();
  while (true) {
    long travelled = averageEncoderCount();

    if (labs(travelled) >= counts_needed - ENCODER_ARRIVAL_TOLERANCE_COUNTS) {
      break;
    }
    checkForStopCommand();
    if (stop_requested) {
      stopAllMotors();
      Serial.println("ERROR,stopped_during_move");
      return false;
    }
    if (millis() - started_at > MOVE_TIMEOUT_MS) {
      stopAllMotors();
      Serial.println("ERROR,move_timed_out");
      return false;
    }
    delay(2);
  }

  stopAllMotors();
  delay(SETTLE_AFTER_STOPPING_MS);
  return true;
}

void checkForStopCommand() {
  if (!Serial.available()) {
    return;
  }
  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line == "STOP") {
    stop_requested = true;
  }
}

void reportPosition() {
  Serial.print("POSITION,");
  Serial.print(scan_index);
  Serial.print(",");
  Serial.print(row_index);
  Serial.print(",");
  Serial.println(column_index);
}

void adjustScanAxis(const String &arguments) {
  int comma = arguments.indexOf(',');
  if (comma < 0) {
    Serial.println("ERROR,adjust_stepper_needs_steps_and_direction");
    return;
  }

  long steps = arguments.substring(0, comma).toInt();
  int direction = arguments.substring(comma + 1).toInt();

  if (steps <= 0) {
    Serial.println("ERROR,step_count_must_be_positive");
    return;
  }
  if (direction != 1 && direction != -1) {
    Serial.println("ERROR,direction_must_be_1_or_minus_1");
    return;
  }

  if (STEPPER_MAXIMUM_STEPS_FROM_PARKED <= 0) {
    Serial.println("ERROR,stepper_travel_limit_not_measured_yet");
    return;
  }

  long would_end_at = stepper_position_from_parked + (steps * direction);
  if (would_end_at < 0 || would_end_at > STEPPER_MAXIMUM_STEPS_FROM_PARKED) {
    Serial.println("ERROR,that_would_move_past_the_travel_limit");
    return;
  }

  enableStepper(true);
  digitalWrite(STEPPER_DIR_PIN, direction > 0 ? HIGH : LOW);
  delayMicroseconds(10);

  for (long step = 0; step < steps; step++) {
    digitalWrite(STEPPER_STEP_PIN, HIGH);
    delayMicroseconds(STEPPER_PULSE_WIDTH_US);
    digitalWrite(STEPPER_STEP_PIN, LOW);
    delayMicroseconds(STEPPER_STEP_INTERVAL_US);
  }

  stepper_position_from_parked = would_end_at;

  Serial.println("STEPPER_DONE");
}


void setupStepper() {
  pinMode(STEPPER_STEP_PIN, OUTPUT);
  pinMode(STEPPER_DIR_PIN, OUTPUT);
  pinMode(STEPPER_ENABLE_PIN, OUTPUT);

  digitalWrite(STEPPER_STEP_PIN, LOW);
  digitalWrite(STEPPER_DIR_PIN, LOW);
  enableStepper(true);

  stepper_position_from_parked = 0;
}


void enableStepper(bool on) {
#if STEPPER_ENABLE_IS_ACTIVE_LOW
  digitalWrite(STEPPER_ENABLE_PIN, on ? LOW : HIGH);
#else
  digitalWrite(STEPPER_ENABLE_PIN, on ? HIGH : LOW);
#endif
}

void reportColourReading() {
  long red_total = 0;
  long green_total = 0;
  long blue_total = 0;
  int good_readings = 0;

  for (int reading = 0; reading < COLOUR_SENSOR_READINGS_TO_AVERAGE; reading++) {
    long red = 0;
    long green = 0;
    long blue = 0;
    if (readColourSensorOnce(&red, &green, &blue)) {
      red_total += red;
      green_total += green;
      blue_total += blue;
      good_readings++;
    }
    delay(5);
  }

  if (good_readings == 0) {
    Serial.println("ERROR,colour_sensor_not_responding");
    return;
  }

  Serial.print("COLOUR,");
  Serial.print(red_total / good_readings);
  Serial.print(",");
  Serial.print(green_total / good_readings);
  Serial.print(",");
  Serial.println(blue_total / good_readings);
}

void setupMotors() {
}


void setupColourSensor() {
}

void driveMecanum(int forward, int sideways, int power) {
  int front_left  = (forward + sideways) * power;
  int front_right = (forward - sideways) * power;
  int rear_left   = (forward - sideways) * power;
  int rear_right  = (forward + sideways) * power;

  setMotorPower(MOTOR_PORT_FRONT_LEFT,  front_left  * MOTOR_DIRECTION_FRONT_LEFT);
  setMotorPower(MOTOR_PORT_FRONT_RIGHT, front_right * MOTOR_DIRECTION_FRONT_RIGHT);
  setMotorPower(MOTOR_PORT_REAR_LEFT,   rear_left   * MOTOR_DIRECTION_REAR_LEFT);
  setMotorPower(MOTOR_PORT_REAR_RIGHT,  rear_right  * MOTOR_DIRECTION_REAR_RIGHT);
}


void setMotorPower(int port, int power_percent) {
  (void)port;
  (void)power_percent;
}


void stopAllMotors() {
  setMotorPower(MOTOR_PORT_FRONT_LEFT, 0);
  setMotorPower(MOTOR_PORT_FRONT_RIGHT, 0);
  setMotorPower(MOTOR_PORT_REAR_LEFT, 0);
  setMotorPower(MOTOR_PORT_REAR_RIGHT, 0);
}


void resetEncoderCounts() {
}


long averageEncoderCount() {
  return 0;
}


bool readColourSensorOnce(long *red, long *green, long *blue) {
  (void)red;
  (void)green;
  (void)blue;
  return false;
}
