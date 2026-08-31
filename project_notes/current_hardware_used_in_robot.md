# The hardware ASIL is built from

As of 31 August 2026.

## Boards

| Part | What it does |
| --- | --- |
| MATRIX controller | four wheel motors, the NEMA 17 stepper, the colour sensor |
| Main ESP32 | coordinates the scan, uploads sensor values, talks to both other boards |
| Seeed XIAO ESP32-S3 Sense | takes the photo and uploads it |
| A laptop | runs everything to do with the AI |

The exact main ESP32 variant still has to be confirmed. The old repository
recorded the gateway board as `esp32_s3_n16r8`, and whether that is still the
board in the middle changes which pins are usable.

## Motion

| Part | Notes |
| --- | --- |
| Four mecanum wheels | can move sideways without turning, so the camera stays square to the cloth |
| MATRIX gear motors with encoders | encoder counts are how the robot knows it has travelled one scan spacing |
| NEMA 17 pancake stepper | adjusts the scanning and wheel base mechanism |
| HW-134A stepper driver | takes step, direction and enable from the MATRIX board |

Wheel diameter, encoder counts per turn, and the distance between scan areas
have all still to be measured. See `things_i_still_need_from_the_old_repository.md`.

## Sensing

| Part | Notes |
| --- | --- |
| XIAO ESP32-S3 Sense camera | macro photos of the weave. Fixed white balance and gain, so it does not retune itself between scan areas |
| MATRIX colour sensor | three channels, red green blue, on the MATRIX board over I2C |

The colour sensor's part number is not confirmed. The old repository recorded
it as `model: unknown` on purpose, so that nobody would end up describing an
RGB sensor as a spectrometer. That is still the honest description: it measures
colour, and three numbers is what it gives.

There is **no infrared sensor** on this robot. The old repository's hardware
description already had `ir: false` for the mobile chassis, so the IR feature
branch was switched off before this migration and has not been carried across.

## Links between the boards

| Link | Wires | Confirmed? |
| --- | --- | --- |
| XIAO to main ESP32 | UART, D6 / GPIO43 TX and D7 / GPIO44 RX, common ground | The XIAO side yes, the main ESP32 side no |
| Main ESP32 to MATRIX | serial, plus common ground | No |
| XIAO to laptop | Wi-Fi, HTTP, the photo | Works in code |
| Main ESP32 to laptop | Wi-Fi, HTTP, the colour readings and the result polling | Works in code |

Check the logic level on the main ESP32 to MATRIX link before connecting it.
The ESP32 is a 3.3 V part, and if the MATRIX board drives its line at 5 V its
TX needs a divider or a level shifter. The XIAO link does not need one, because
both ends are 3.3 V.

## What changed from the previous robot

The old repository was built for two robots before this one.

**A gantry**, `legacy_gantry_v0`: a stepper driven X and Y sensor carriage with
limit switches and real millimetre coordinates, an eight channel spectral
sensor and an IR sensor. The firmware in `firmware/esp32` is for this machine
and its README says so.

**A mobile mecanum chassis**, `mobile_mecanum_v1`: four mecanum wheels, a
MATRIX board for motion and the colour sensor, and one ESP32-S3 doing both the
camera and the network.

ASIL now is that mobile chassis with the camera split onto its own XIAO board
and a main ESP32 added in the middle as coordinator.

That split is what makes the old firmware unusable, and it is why the embedded
code in this repository was written fresh while the AI code was carried across
almost unchanged.

## What this means for old data and old models

The sensing stack decides what the numbers mean. Three RGB channels and eight
spectral bands are not the same measurement, so:

- scans collected on the gantry cannot be mixed with scans collected now,
- the one saved model in the old repository cannot be used here, and would be
  refused by the schema check even if someone copied it in,
- the feature vector carries a fingerprint that includes the hardware profile
  name, so a mismatch is caught rather than quietly tolerated.

The profile this code produces is `mobile_mecanum_xiao_v1`, in
`ai_settings_and_thresholds.py`. Change it whenever the sensing hardware
changes in a way that changes what a number means. Changing a cable does not
need a new profile. Changing the colour sensor does.
