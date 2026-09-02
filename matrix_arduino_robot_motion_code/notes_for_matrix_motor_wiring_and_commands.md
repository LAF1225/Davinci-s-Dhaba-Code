# MATRIX controller: wiring and commands

## What this board does

The MATRIX controller owns everything that has to happen at an exact moment:

- the four mecanum wheel motors and their encoders,
- the NEMA 17 pancake stepper, through the HW-134A driver,
- the MATRIX colour sensor.

It does not connect to Wi-Fi, does not know the scan id, and does not run any
part of the AI. It takes short commands from the main ESP32 and answers them.

## Why the colour sensor is here and not on an ESP32

Because that is where it is wired, and where the previous repository had it.
Its hardware description recorded the optical sensor as attached to the MATRIX
board over I2C.

The camera moving to the XIAO does not change anything about the colour sensor.
Moving a sensor from one controller to another because a block diagram looks
tidier would invalidate every dark and white calibration taken before the move,
and nothing in the software would notice.

## The link up to the main ESP32

| | |
| --- | --- |
| MATRIX serial TX | main ESP32 RX |
| MATRIX serial RX | main ESP32 TX |
| MATRIX GND | main ESP32 GND |

**Not filled in yet:** which MATRIX serial port and which main ESP32 pins.
Copy them from the actual wiring, not from a diagram, and write them here and
in `main_esp32_sensor_and_scan_control_code/notes_for_main_esp32_connections.md`.

**Check the logic levels before connecting these two boards.** The ESP32 side
is 3.3 V. If the MATRIX controller drives its serial line at 5 V, its TX needs
a divider or a level shifter before it reaches the ESP32 RX pin, or the ESP32
input will be damaged. This is different from the XIAO to main ESP32 link,
where both boards are 3.3 V and no shifter is needed.

Baud rate: `MATRIX_SERIAL_BAUD_RATE` in `motor_and_stepper_settings.h`. It must
match the main ESP32 sketch and `matrix_to_main_esp32_serial_baud_rate` in
`settings.json`. It is 115200 in the file as a starting point. Confirm the link
runs cleanly at it before treating that as final.

## Commands

The main ESP32 sends one line, the MATRIX board answers with one or two lines.

| Sent to MATRIX | Answer |
| --- | --- |
| `MOVE_NEXT` | `MOVING` then `DONE`, or `ERROR,<reason>` |
| `MOVE_FORWARD` / `MOVE_BACK` / `MOVE_LEFT` / `MOVE_RIGHT` | `MOVING` then `DONE`, or `ERROR,<reason>` |
| `STOP` | `DONE` |
| `POSITION` | `POSITION,<scan_index>,<row>,<column>` |
| `READ_COLOUR` | `COLOUR,<red>,<green>,<blue>`, or `ERROR,<reason>` |
| `ADJUST_STEPPER,<steps>,<direction>` | `STEPPER_DONE`, or `ERROR,<reason>` |

On start up the board sends `READY` once.

`READ_COLOUR` returns **raw counts**, not percentages and not a colour name.
The laptop does the dark and white calibration, and it needs the raw numbers.

## Values that still have to be measured

None of these were copied from working code, because the previous repository
had none for this robot. Its firmware was written for the older gantry machine
with an X and Y sensor carriage and limit switches, and its own README marks it
deprecated. Each of these has to be measured on the actual robot.

| Setting | How to get it |
| --- | --- |
| `MOTOR_PORT_*` | Look at the robot and write down which motor is in which port |
| `MOTOR_DIRECTION_*` | Drive the robot forward, see which wheels turn backwards, set those to -1 |
| `ENCODER_COUNTS_PER_WHEEL_TURN` | Lift the robot, mark a wheel, turn it by hand ten times while printing the count, divide by ten |
| `WHEEL_DIAMETER_MM` | Measure across the widest point with the robot standing on the wheel, so the rollers are squashed the way they will be when driving |
| `DISTANCE_BETWEEN_SCAN_AREAS_MM` | Work out from the camera field of view. Two neighbouring areas must not overlap, and must be genuinely different parts of the cloth |
| `STEPPER_STEP_PIN`, `STEPPER_DIR_PIN`, `STEPPER_ENABLE_PIN` | Which pins the three HW-134A wires are in |
| `STEPPER_ENABLE_IS_ACTIVE_LOW` | If the motor is stiff when it should be free, flip it |
| `STEPPER_MICROSTEPS` | Read the small switches on the HW-134A module |
| `STEPPER_MAXIMUM_STEPS_FROM_PARKED` | Move the axis by hand from parked to its limit and count |
| `COLOUR_SENSOR_PORT` | Which sensor port the colour sensor is in |
| `MATRIX_SERIAL_BAUD_RATE` | Confirm the link is clean at 115200, or pick one that is |

Until `ENCODER_COUNTS_PER_WHEEL_TURN`, `WHEEL_DIAMETER_MM` and
`DISTANCE_BETWEEN_SCAN_AREAS_MM` are filled in, `travelOneScanSpacing` refuses
to move and answers `ERROR,encoder_and_wheel_settings_not_measured_yet`. That
is on purpose. A robot that drives the wrong distance looks like it is working.

## Functions still to write

The functions under the `MATRIX LIBRARY` heading at the bottom of the sketch
are stubs:

- `setupMotors`
- `setupColourSensor`
- `setMotorPower`
- `resetEncoderCounts`
- `averageEncoderCount`
- `readColourSensorOnce`

They are the only places that touch the MATRIX library, so they are the only
things that change if the controller is ever swapped. Fill them in from the
MATRIX library documentation for the controller you actually have.

The mecanum mixing in `driveMecanum` is already written out, because it is the
same on every mecanum robot and does not depend on the library: each wheel gets
the forward part plus or minus the sideways part, depending on which way its
rollers face. If the robot moves diagonally when told to go sideways, the
mixing is right and one of the `MOTOR_DIRECTION_*` values is wrong.
