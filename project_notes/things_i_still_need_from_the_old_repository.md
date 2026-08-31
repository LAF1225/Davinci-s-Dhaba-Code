# What is missing, and what has to be measured

Everything in this file blocks something. None of it was guessed at.

## 1. There is no trained model for this robot

The old repository has exactly one saved model, `data/models/v0.1.0`. It cannot
be used here, and it should not be copied across. Its own `metadata.json` says
why:

```
"hardware_profiles": ["legacy_gantry_v0"],
"required_modalities": ["camera", "spectral", "ir"],
"feature_dimensions": 431,
"notes": "synthetic demo, overlapping sensor distributions",
"legacy_note": "Trained on the gantry robot with an 8-channel spectral sensor
                and IR. Not applicable to mobile_mecanum_v1.
                Preserved for provenance."
```

Three separate reasons:

- it was trained on **synthetic demo data**, not on real cloth, so it has never
  seen a textile;
- it expects an **eight channel spectrometer and an IR sensor**, and this robot
  has a three channel colour sensor and no IR;
- it was trained for the **gantry robot**, which no longer exists.

Its feature vector is 431 numbers. This code produces 415. The schema check
will refuse it, which is correct.

**So: the classifier has to be trained from scratch, on real textiles collected
with this robot.** Until that happens the laptop runs in reference comparison
mode, reports every scan as Inconclusive, and says so on startup. That is the
honest behaviour, not a bug.

There is also no reference bank, because a reference bank is built from
verified textiles scanned with this robot, and none exist yet.

## 2. The DINOv2 weights are not committed

They are large and they are not source code, so they are in `.gitignore`.

On the machine this repository was built on they have already been copied
across from the old repository, so DINOv2 loads and the tests pass. On a fresh
checkout they will not be there.

Two ways to get them:

- copy `E:\WRO Textile Analyser\data\weights\hub` to
  `saved_ai_files\dinov2_weights\hub`, which needs no internet, or
- let the first run download `dinov2_vits14` from torch hub, which needs
  internet once. After that it works offline.

## 3. Every hardware constant on the MATRIX board

The old repository has **no working values for this robot**. Its firmware was
written for the older gantry machine: stepper carriage, limit switches,
millimetre coordinates, an eight channel spectral sensor. Its own README opens
with "This firmware targets the previous gantry robot" and marks itself
deprecated.

So none of these could be copied, and none were invented. They are in
`matrix_arduino_robot_motion_code/motor_and_stepper_settings.h` marked
`MUST BE CONFIRMED`:

| Setting | How to get it |
| --- | --- |
| `MOTOR_PORT_*` for all four wheels | Look at the robot |
| `MOTOR_DIRECTION_*` for all four wheels | Drive it forward, see which wheels go backwards |
| `ENCODER_COUNTS_PER_WHEEL_TURN` | Turn a wheel ten times by hand while printing the count |
| `WHEEL_DIAMETER_MM` | Measure it with the robot standing on the wheel |
| `DISTANCE_BETWEEN_SCAN_AREAS_MM` | Work out from the camera field of view |
| `STEPPER_STEP_PIN`, `STEPPER_DIR_PIN`, `STEPPER_ENABLE_PIN` | Read off the HW-134A wiring |
| `STEPPER_ENABLE_IS_ACTIVE_LOW` | If the motor is stiff when it should be free, flip it |
| `STEPPER_MICROSTEPS` | Read the switches on the HW-134A module |
| `STEPPER_MAXIMUM_STEPS_FROM_PARKED` | Move the axis by hand and count |
| `COLOUR_SENSOR_PORT` | Look at the robot |

Until the first three of those are filled in, the sketch **refuses to move**
and answers `ERROR,encoder_and_wheel_settings_not_measured_yet`. That is
deliberate. A robot driving the wrong distance still looks like it is working.

## 4. Six functions on the MATRIX board are stubs

At the bottom of `matrix_move_robot_and_control_scan_axis.ino`, under the
`MATRIX LIBRARY` heading:

- `setupMotors`
- `setupColourSensor`
- `setMotorPower`
- `resetEncoderCounts`
- `averageEncoderCount`
- `readColourSensorOnce`

They are the only places that touch the MATRIX library. There is no working
MATRIX motor code anywhere in the old repository to copy from, and writing
plausible looking library calls from memory would produce a sketch that
compiles, looks finished and does not drive the robot. Fill them in from the
MATRIX library documentation for the controller you have.

Everything else in that sketch, including the mecanum wheel mixing and the
stepper pulse generation, is written out and does not depend on the library.

## 5. The main ESP32's pin numbers

The XIAO side of the camera UART is confirmed: D6 / GPIO43 is TX, D7 / GPIO44
is RX. The main ESP32 side is not, and neither is the link down to the MATRIX
board.

In `main_esp32_wifi_and_laptop_connection_settings.h`:

- `XIAO_UART_RX_PIN`, `XIAO_UART_TX_PIN`
- `MATRIX_SERIAL_RX_PIN`, `MATRIX_SERIAL_TX_PIN`

These are not in the old repository at all, because the previous robot had no
separate camera board: one ESP32-S3 was both the camera and the network
gateway.

Also confirm the board variant. The old hardware description records the
gateway as `esp32_s3_n16r8`. Whether that is still the board in the middle
changes which pins are usable.

## 6. Both baud rates

`XIAO_UART_BAUD_RATE` and `MATRIX_SERIAL_BAUD_RATE` are 115200 in the files as
a starting point. Neither has been confirmed on the real hardware, and
`settings_example.json` leaves both `null` for that reason.

A wrong baud rate does not fail cleanly: the link comes up and delivers
scrambled characters, which reads like a wiring fault and wastes an afternoon.

## 7. The logic level on the MATRIX serial link

The ESP32 is a 3.3 V part. If the MATRIX controller drives its serial line at
5 V, its TX needs a divider or a level shifter before it reaches the ESP32 RX
pin. Check this **before** connecting the two boards.

The XIAO link does not need one: both boards are 3.3 V.

## 8. The colour sensor part number

The old `config/hardware.yaml` records it as `model: unknown`, deliberately, so
that nobody would describe an RGB sensor as a spectrometer. That is still true
here. It affects two things:

- how `readColourSensorOnce` is written on the MATRIX board;
- whether three channels is right, which is what
  `COLOUR_SENSOR_CHANNEL_COUNT` assumes in three places.

## 9. `camera_pins.h` for the XIAO

Not committed on purpose. It comes from the vendor, through
**File > Examples > ESP32 > Camera > CameraWebServer** in the Arduino IDE.
Copy it next to the XIAO sketch. See the notes in that folder.

## What is NOT blocked

The laptop side runs today. You can:

- start the server,
- upload a photo and a sensor reading and watch them be joined by scan id,
- run the photo quality check and the colour calibration,
- run DINOv2 and get an embedding,
- run the whole test suite.

What you cannot do until there is a trained model is get a handmade or machine
answer. Every scan comes back Inconclusive with `no_trained_model` in the
reasons, which is the correct thing for it to say.
