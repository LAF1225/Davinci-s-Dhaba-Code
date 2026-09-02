# XIAO ESP32-S3 Sense: wiring and the confirmed UART link

## What this board does

It takes the photo and puts it on the laptop. That is all.

It does not drive anything, does not read the colour sensor, and does not run
DINOv2 or the SVM. No microcontroller on this robot does. The AI runs on the
laptop.

## The UART link, which is confirmed

This is wired on the robot and must not be changed without changing the wiring.

```
XIAO D6 / GPIO43 (TX)  ---------->  main ESP32 RX
XIAO D7 / GPIO44 (RX)  <----------  main ESP32 TX
XIAO GND               -----------  main ESP32 GND
```

Rules for anyone editing this code:

- **TX goes to RX.** Crossed, not straight through. Two TX pins wired together
  is the usual reason a new serial link stays completely silent.
- **The common ground is required.** Without a shared ground the two boards
  have no agreed reference for what a 1 and a 0 look like, and the link either
  fails or works intermittently, which is harder to find.
- **No level shifter on this link.** Both boards are 3.3 V parts. (The link
  from the main ESP32 down to the MATRIX board is different: check that one.)
- **Do not reuse D6 or D7.** They are not free pins.
- **Do not move the link to D1 and D4** because there happen to be spare wires
  there.
- **No photo goes down this wire.** Short text lines only.

The pins are set in `xiao_camera_wifi_and_server_settings.h` as
`XIAO_UART_TX_PIN 43` and `XIAO_UART_RX_PIN 44`.

## Messages on that link

| Direction | Message |
| --- | --- |
| main ESP32 to XIAO | `TAKE_SCAN,<scan_id>,<region_id>,<x>,<y>` |
| XIAO to main ESP32 | `CAMERA_READY` once at start up |
| XIAO to main ESP32 | `PHOTO_CAPTURED,<scan_id>` |
| XIAO to main ESP32 | `PHOTO_SENT,<scan_id>` |
| XIAO to main ESP32 | `CAMERA_ERROR,<scan_id>,<reason>` |

This board never invents a scan id. It sends back exactly the one it was given,
because the laptop uses that id to pair this photo with the colour reading the
main ESP32 uploads separately. A photo labelled with the wrong id would be
paired with the wrong sensor reading, and nothing downstream could ever detect
that had happened.

`CAMERA_READY` is only sent when the camera started **and** Wi-Fi connected. A
board that says it is ready when it cannot upload anything would make the main
ESP32 wait for photos that are never coming.

## Which UART is which

| UART | Used for |
| --- | --- |
| UART0 | the USB serial monitor |
| UART1 | the main ESP32, on GPIO43 and GPIO44 |

## Before this compiles: camera_pins.h

The camera pin map is **not** typed into this repository. It comes from the
official board definition instead, so the numbers are the vendor's.

1. In the Arduino IDE, install the **esp32** board package by Espressif.
2. Open **File > Examples > ESP32 > Camera > CameraWebServer**.
3. Copy `camera_pins.h` out of that example into this folder, next to the
   `.ino` file.

The sketch defines `CAMERA_MODEL_XIAO_ESP32S3` before including it, which is
the block in that file holding this board's pin map.

If you would rather not copy the file, the same pin map is in the Seeed wiki
page for the XIAO ESP32S3 Sense camera. Take it from one of those two places.
Do not type in numbers from a forum post: a wrong data pin gives a camera that
initialises cleanly and returns corrupted images.

## Board settings in the Arduino IDE

| Setting | Value |
| --- | --- |
| Board | XIAO_ESP32S3 |
| PSRAM | **OPI PSRAM** |
| Partition scheme | Huge APP, or any scheme with a large program space |

PSRAM matters. Without it there is nowhere to hold a large frame, and the
sketch falls back to a small one and says so on the serial monitor. Small
photos of cloth have lost the thread detail this project is about, and the
laptop will reject them as too small, which is the right answer.

Make sure you have the **Sense** version of the board. That is the one with the
camera on it.

## Why the photo does not go over the UART

A macro JPEG from this camera is a few megabytes. At 115200 baud that is
several minutes per scan area. It would also mean the main ESP32 holding a
multi megabyte buffer it does not have room for, just to forward the bytes to a
laptop this board can already reach on its own Wi-Fi.

So the split is:

- the UART carries the scan id down and short status lines back,
- the photo goes straight to the laptop over Wi-Fi,
- the laptop puts the two halves back together using the scan id.

## Wi-Fi

Copy `wifi_credentials_example.h` to `wifi_credentials.h` and edit that.
`wifi_credentials.h` is in `.gitignore`, so the password is not committed.

Both ESP boards must join the same network as the laptop, usually the laptop's
own hotspot so the robot works in a hall with no usable Wi-Fi.

## When something is wrong

| What you see | Usually means |
| --- | --- |
| No `CAMERA_READY` on the main ESP32 | TX and RX not crossed, no common ground, or the baud rates do not match |
| A stream of `[uart] ignoring:` lines with rubbish in them | The two baud rates do not match |
| `camera init failed` | Ribbon cable not seated, or this is the non-Sense board |
| `WARNING: no PSRAM found` | PSRAM is not enabled in the board settings |
| Uploads return HTTP 413 | The photo is over the laptop's size limit; see `MAXIMUM_PHOTO_UPLOAD_MEGABYTES` |
| Uploads return HTTP 409 | The laptop already has a photo with that scan id, which means an id was reused |
| Photos upload but the laptop never produces a result | The main ESP32 half never arrived; check the sensor upload |
