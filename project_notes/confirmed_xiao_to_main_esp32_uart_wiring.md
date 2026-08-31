# The XIAO to main ESP32 UART link

Confirmed on the robot, 31 August 2026.

```
XIAO D6 / GPIO43 (TX)  ---------->  main ESP32 RX
XIAO D7 / GPIO44 (RX)  <----------  main ESP32 TX
XIAO GND               -----------  main ESP32 GND
```

Three wires. The third one is not optional.

## Rules

**TX goes to RX, crossed.** One board's transmit is the other board's receive.
Wiring TX to TX is the most common reason a new serial link stays completely
silent, and it looks exactly like a code problem.

**The common ground is required.** Without a shared ground the two boards have
no agreed reference for what a 1 and a 0 look like. The link then either does
not work at all, or works most of the time, which is worse.

**No level shifter here.** Both boards are 3.3 V parts. (The main ESP32 to
MATRIX link is a different question, and worth checking before you connect it.)

**D6 and D7 do not move.** They are not spare pins. Do not reuse them, and do
not move the link to D1 and D4 because there happen to be wires there.

**Neither board powers the other**, unless the power design says so in writing.
Two boards sharing a regulator sized for one shows up as random resets during a
demo, and looks like a software fault for a long time first.

**No photo goes down this wire.** Short text lines only.

## Where the pin numbers live in the code

XIAO side, in `xiao_esp32s3_camera_code/xiao_camera_wifi_and_server_settings.h`:

```c
#define XIAO_UART_TX_PIN 43   // D6
#define XIAO_UART_RX_PIN 44   // D7
```

Main ESP32 side, in
`main_esp32_sensor_and_scan_control_code/main_esp32_wifi_and_laptop_connection_settings.h`:

```c
#define XIAO_UART_RX_PIN 0   // NOT CONFIRMED YET
#define XIAO_UART_TX_PIN 0   // NOT CONFIRMED YET
```

The main ESP32 side is still zero because nobody has written down which pins
the wires are actually in. They are not recorded anywhere in the old
repository, because the previous robot had no separate camera board: one
ESP32-S3 was both the camera and the network gateway.

Read them off the robot and fill them in. Do not guess: a UART on the wrong
pins fails silently.

## What travels on it

| Direction | Message |
| --- | --- |
| main to XIAO | `TAKE_SCAN,<scan_id>,<region_id>,<x>,<y>` |
| XIAO to main | `CAMERA_READY`, once at start up |
| XIAO to main | `PHOTO_CAPTURED,<scan_id>` |
| XIAO to main | `PHOTO_SENT,<scan_id>` |
| XIAO to main | `CAMERA_ERROR,<scan_id>,<reason>` |

Each message is one line ending in a newline. The longest of them is well under
a hundred bytes.

## Baud rate

115200 in both files, as a starting point. It has **not** been confirmed on the
real hardware, which is why `main_esp32_to_xiao_uart_baud_rate` is `null` in
`settings_example.json`.

Both sides must match. A mismatch does not fail cleanly: the link comes up and
delivers scrambled characters, which reads like a wiring fault.

The XIAO sketch prints `[uart] ignoring: <line>` for anything it does not
recognise. A stream of those full of rubbish characters is a baud rate
mismatch, not a wiring problem.

## Checking it works

1. Flash both boards and open both serial monitors at 115200.
2. On start up the XIAO should print `camera ready`, then the main ESP32 should
   print `camera board is ready`.
3. If the main ESP32 prints the warning about no `CAMERA_READY`, work through:
   TX and RX crossed, common ground present, baud rates matching, and the main
   ESP32 pin numbers actually filled in.
