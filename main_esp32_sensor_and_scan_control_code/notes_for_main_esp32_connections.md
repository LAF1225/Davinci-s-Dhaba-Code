# Main ESP32: connections and settings

## What this board does

It is the coordinator. It decides when a scan happens, owns the scan id, and
keeps the other three parts of the system agreeing with each other.

It does **not** drive a motor, and it does **not** touch a photo.

```
XIAO ESP32-S3 Sense        camera, uploads its own photo over Wi-Fi
      |  UART
main ESP32   <- this board, coordinates and uploads sensor values
      |  serial
MATRIX Arduino             four wheel motors, NEMA 17, colour sensor
```

## Two serial links, and they are different

### Down to the XIAO camera board

This one is **confirmed** on the XIAO side and must not be changed:

```
XIAO D6 / GPIO43 (TX)  ---------->  main ESP32 RX
XIAO D7 / GPIO44 (RX)  <----------  main ESP32 TX
XIAO GND               -----------  main ESP32 GND
```

- The common ground is not optional. Without it the two boards have no shared
  reference and the link either does not work or works intermittently, which is
  worse.
- Both boards are 3.3 V, so **no level shifter is needed here**.
- Keep TX crossed to RX. Two TX pins wired together is the most common reason a
  new UART link stays silent.
- Do not reuse D6 or D7 for anything else, and do not move the link to D1 and
  D4 because there happen to be wires there.

Only short text lines travel here. The photo does not.

**Still to fill in:** which pins on the main ESP32 the two wires are in.
Set `XIAO_UART_RX_PIN` and `XIAO_UART_TX_PIN` in
`main_esp32_wifi_and_laptop_connection_settings.h` and write them in the table
below. They are not recorded anywhere in the previous repository, because the
previous robot had no separate camera board at all: one ESP32-S3 was both the
camera and the network gateway.

### Down to the MATRIX Arduino

```
main ESP32 TX  ---------->  MATRIX serial RX
main ESP32 RX  <----------  MATRIX serial TX
GND            -----------  GND
```

**Check the logic levels on this one.** The ESP32 is a 3.3 V part. If the
MATRIX controller drives its serial line at 5 V, its TX must go through a
divider or a level shifter before it reaches the ESP32 RX pin, or the input
will be damaged. This is the difference between the two links: the XIAO one is
3.3 V on both ends, this one might not be.

**Still to fill in:** `MATRIX_SERIAL_RX_PIN` and `MATRIX_SERIAL_TX_PIN`.

### Which hardware UART is which

| UART | Used for |
| --- | --- |
| UART0 | the USB serial monitor, for the person standing next to the robot |
| UART1 | the XIAO camera board |
| UART2 | the MATRIX Arduino |

## The wiring table to fill in

| Wire | XIAO / MATRIX pin | Main ESP32 pin | Confirmed by | Date |
| --- | --- | --- | --- | --- |
| XIAO TX to main RX | D6 / GPIO43 | | | |
| XIAO RX from main TX | D7 / GPIO44 | | | |
| XIAO GND | GND | GND | | |
| MATRIX TX to main RX | | | | |
| MATRIX RX from main TX | | | | |
| MATRIX GND | GND | GND | | |

Also record the exact board variant. The previous repository's hardware
description says the gateway was an `esp32_s3_n16r8`. Confirm whether that is
still the board in the middle, because the pin numbers depend on it.

## Power

Do not let one ESP32 power the other unless the power design says so in
writing. Two boards sharing a regulator that was sized for one is a fault that
shows up as random resets during a demo, and it looks like a software problem
for a long time before anyone suspects the power.

## Baud rates

Both are 115200 in the files as a starting point. Neither has been confirmed on
the real hardware.

| Link | Setting | Must also match |
| --- | --- | --- |
| main ESP32 to XIAO | `XIAO_UART_BAUD_RATE` | `XIAO_UART_BAUD_RATE` in the XIAO sketch, `main_esp32_to_xiao_uart_baud_rate` in `settings.json` |
| main ESP32 to MATRIX | `MATRIX_SERIAL_BAUD_RATE` | `MATRIX_SERIAL_BAUD_RATE` in `motor_and_stepper_settings.h`, `matrix_to_main_esp32_serial_baud_rate` in `settings.json` |

A wrong baud rate does not fail cleanly. The link comes up and delivers
scrambled characters, which reads as a wiring fault.

## Colour sensor calibration

The dark and white references live on this board, in flash, and are sent to the
laptop with every scan. Sending them with the reading keeps a measurement and
the calibration it was taken under together, so recalibrating later cannot
quietly change what an old reading meant.

Open the serial monitor at 115200 and type:

```
dark      cover the sensor, lamp off, then send this
white     white card under the sensor, lamp on, then send this
```

The board refuses a white reference that is not clearly brighter than the dark
one on every channel. That is the common mistake, and it produces readings that
look real and carry no information at all.

## Using the board

| Type this | What happens |
| --- | --- |
| `dark` | capture the dark reference |
| `white` | capture the white reference |
| `textile H001` | say which textile is under the robot |
| `start` | begin scanning |
| `stop` | stop after the current scan area |
| `status` | print what the board knows |

## What has to agree with what

| This | Must match this |
| --- | --- |
| `SCAN_AREAS_PER_TEXTILE` | `number_of_regions_per_textile` in `settings.json` |
| `SENSOR_UPLOAD_PATH`, `SCAN_RESULT_PATH` | the paths in `laptop_connection_code/scan_command_words.py` |
| `COLOUR_CHANNELS` | `COLOUR_SENSOR_CHANNEL_COUNT` on the MATRIX board and in `ai_settings_and_thresholds.py` |
| `ROBOT_SHARED_KEY` | `robot_shared_key` in `settings.json` |
