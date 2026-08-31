# The control chain, and why it is what it is

Locked on 31 August 2026.

```
Seeed XIAO ESP32-S3 Sense
        |
        |  UART, confirmed wiring, short text lines only
        |
   main ESP32
        |
        |  serial, small commands and replies
        |
  MATRIX Arduino
        |
        +---- four wheel motors, mecanum drive
        +---- HW-134A ----> NEMA 17 pancake stepper
        +---- MATRIX colour sensor
```

Alongside that, over Wi-Fi:

```
XIAO       -- photo -------------> laptop
main ESP32 -- colour readings ---> laptop
main ESP32 <-- what to do next --- laptop
```

## Who does what

**Seeed XIAO ESP32-S3 Sense**

- takes the textile photo
- talks to the main ESP32 about when to take it and whether it went up
- sends the photo straight to the laptop over Wi-Fi
- never runs DINOv2 or the SVM

**Main ESP32**

- is the coordinator
- makes the `scan_id` and passes it to the XIAO
- gets the colour reading from the MATRIX board and sends it to the laptop
- tells the MATRIX board what movement is needed
- waits for the MATRIX board to say it finished
- never drives a motor directly

**MATRIX Arduino**

- drives the four wheel motors
- drives the NEMA 17 through the HW-134A
- reads the colour sensor
- reports when it has finished moving
- never touches Wi-Fi and never sees a photo

**Laptop**

- receives the photo from the XIAO
- receives the colour reading from the main ESP32
- joins them by `scan_id`
- runs quality check, DINOv2, texture measurements, colour features, the
  combined vector, the scaler and SVM, the reference comparison, and the
  combination across scan areas
- sends back one command

## Rules that are not up for discussion

**The XIAO never commands the MATRIX board.** Everything goes through the main
ESP32. Two boards issuing motion commands to the same motors is a robot that
moves while the camera is exposing.

**The main ESP32 never drives the wheel motors or the stepper directly.** It
decides what movement is needed and sends a short command. Motor timing has to
happen on the board that is not also waiting on Wi-Fi.

**Photos never go over the UART.** A macro JPEG is a few megabytes. At 115200
baud that is minutes per scan area, and the main ESP32 would have to hold a
buffer it does not have room for, to forward bytes to a laptop the XIAO can
already reach itself.

The one exception worth writing down: if direct XIAO to laptop Wi-Fi is ever
proven not to work on the real hardware, that is a reason to revisit this. A
suspicion is not. Test it first.

**The XIAO UART pins do not move.** D6 / GPIO43 is TX, D7 / GPIO44 is RX. They
are confirmed on the robot.

**The colour sensor stays on the MATRIX board.** That is where it is wired and
where the old repository had it. Moving a sensor between controllers because a
diagram looks tidier invalidates every calibration taken before the move, and
nothing in the software would notice.

## Why the AI is on the laptop

The project report is not consistent about this. Some early wording implies a
CNN running on an ESP32; the detailed workflow sections put the pipeline on the
laptop. The laptop is right, for three reasons:

- DINOv2 with 21 million parameters does not fit on a microcontroller, and
  neither does torch;
- when a result looks wrong, you want to be able to load the photo, look at the
  features and step through the code, which you can do on a laptop;
- the microcontrollers have real time work to do, and inference on the same
  board would make the motion timing depend on how long the AI took.

So no microcontroller in this robot runs a neural network. They collect
evidence and move.
