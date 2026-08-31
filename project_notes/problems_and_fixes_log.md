# Problems and fixes

Add a line whenever something goes wrong and you work out why. Newest at the
top. This file is worth more than it looks: half of robotics is remembering
that you already solved this in March.

Format: what happened, what it turned out to be, what fixed it.

---

## 31 August 2026 - the repository was rebuilt

Not a problem, but the starting point for everything below.

The code was moved out of `LAF1225/textiles-ai-thingy` into this repository.
The AI came across almost unchanged. The embedded code was written fresh,
because the old firmware was for the gantry robot and said so in its own
README.

What was checked at the time:

- all 60 tests pass
- the laptop server accepts a photo and a colour reading, joins them by scan
  id, and runs the whole pipeline including DINOv2
- with no trained model it answers `inconclusive` with `no_trained_model` in
  the reasons, which is correct

What was **not** checked, because it needs the robot:

- anything on the MATRIX board
- both UART links
- the camera on real cloth
- any answer that is not inconclusive, because there is no trained model yet

---

## Things worth knowing before they bite you

These are not bugs that happened. They are the ones the code was written to
catch, and what they look like when they do.

**A UART link that stays completely silent.** Almost always TX wired to TX
instead of to RX, or no common ground. Check both before reading any code.

**A UART link delivering rubbish characters.** The two baud rates do not match.
The XIAO sketch prints `[uart] ignoring: <line>` for anything it does not
recognise, so a stream of those full of nonsense is the symptom.

**Every colour reading identical.** Usually a stuck I2C bus rather than a
genuinely grey textile. The laptop catches it as `colour_constant_vector`.

**Colour readings that look real and carry no information.** The white
reference was captured with the lamp off, or with the sensor still covered. The
bottom of the reflectance fraction collapses and every channel saturates to the
same number. The main ESP32 refuses to save a white reference that is not
clearly brighter than the dark one, and the laptop catches it again as
`colour_calibration_degenerate`.

**Every photo rejected as blurry.** The camera is firing before the chassis has
stopped rocking. Increase `SETTLE_AFTER_STOPPING_MS` on the MATRIX board.

**The robot travels the wrong distance.** `ENCODER_COUNTS_PER_WHEEL_TURN` or
`WHEEL_DIAMETER_MM` is wrong. While they are still zero the sketch refuses to
move at all and says `ERROR,encoder_and_wheel_settings_not_measured_yet`, which
is deliberate: a robot driving the wrong distance still looks like it is
working.

**The robot moves diagonally when told to go sideways.** The mecanum mixing is
fine, one of the `MOTOR_DIRECTION_*` values is wrong.

**The stepper skips steps silently.** `STEPPER_STEP_INTERVAL_US` is too short,
so the motor is being asked to go faster than it can. Nothing reports a fault;
the scanning axis just ends up somewhere else.

**A saved model refuses to load.** Read the message: it says which part does not
match. This is the schema check doing its job. The fix is to retrain, never to
turn the check off.

**Every scan comes back inconclusive.** With no trained model, that is the
correct behaviour, not a fault. Check `/api/v1/health` on the laptop, which
says exactly what is and is not loaded.

**The laptop never answers.** One half of the scan never arrived. After thirty
seconds the other half is dropped and logged. Check whether the XIAO reported
`PHOTO_SENT` and whether the main ESP32's upload got a 202.

---

## Template

```
## <date> - <one line about what happened>

**What we saw:**

**What it turned out to be:**

**What fixed it:**

**How to stop it happening again:**
```
