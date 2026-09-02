# ASIL - textile analyser robot

WRO 2026.

ASIL is a small robot that drives across a piece of cloth, stops at several
places, photographs the weave close up and measures its colour, and then says
whether what it saw looks more like handmade or machine production.

It says **looks like**. It does not certify anything, and the wording it uses
says so:

- Likely consistent with handmade production
- Likely consistent with machine production
- Inconclusive

If the evidence is weak, or the areas of the cloth disagree with each other, or
the textile looks like nothing the robot has references for, the answer is
Inconclusive. That is a real answer and the system is built to give it, because
the alternative is telling a weaver something about their work that the
evidence does not support.

## The hardware

| Part | What it does |
| --- | --- |
| MATRIX controller | drives four mecanum wheels and the NEMA 17 stepper, and reads the colour sensor |
| Four mecanum wheels with encoder motors | move the robot between scan areas without turning it |
| NEMA 17 pancake stepper with an HW-134A driver | adjusts the scanning mechanism |
| MATRIX colour sensor | three channels, red green blue, over I2C |
| Main ESP32 | coordinates the scan and talks to the laptop |
| Seeed XIAO ESP32-S3 Sense | takes the macro photo and uploads it |
| A laptop | runs all of the AI |

No microcontroller in this robot runs a neural network. They collect evidence
and move; the laptop does the thinking.

## How the pieces fit together

```
Seeed XIAO ESP32-S3 Sense
        |
        |  UART: D6/GPIO43 TX, D7/GPIO44 RX, common ground
        |  short text lines only, never a photo
        |
   main ESP32
        |
        |  serial: small commands, small replies
        |
  MATRIX Arduino
        |
        +---- four wheel motors
        +---- HW-134A ----> NEMA 17 stepper
        +---- colour sensor


over Wi-Fi, separately:

   XIAO       -- the photo ----------> laptop
   main ESP32 -- the colour reading -> laptop
   main ESP32 <- what to do next ---- laptop
```

The photo and the colour reading travel to the laptop by different routes and
carry the same `scan_id`. The laptop joins them by that id. It never pairs two
halves that arrived at a similar time.

## What runs where

**On the MATRIX Arduino**, `matrix_arduino_robot_motion_code/`

Drives the wheels one scan spacing at a time using the encoders, drives the
stepper, reads the colour sensor, and answers short commands from the main
ESP32. Waits for the chassis to stop rocking before reporting `DONE`, so the
camera never fires on a moving robot.

**On the main ESP32**, `main_esp32_sensor_and_scan_control_code/`

Makes the `scan_id`, tells the XIAO to take the photo, gets the colour reading
from the MATRIX board, uploads it to the laptop, asks the laptop what happened,
and tells the MATRIX board where to go next. Also holds the colour sensor
calibration.

**On the XIAO camera board**, `xiao_esp32s3_camera_code/`

Waits for `TAKE_SCAN`, takes one photo, uploads it straight to the laptop over
Wi-Fi, and reports back. Never invents a `scan_id`; it sends back the one it
was given.

**On the laptop**, `laptop_ai_code/` and `laptop_connection_code/`

Receives both halves, joins them, saves the raw evidence, then: photo quality
check, DINOv2 features, simple texture measurements, colour features, one
combined vector, comparison with the verified references, the saved
StandardScaler and SVM, a decision for that area, and finally one answer for
the whole textile.

## Getting set up

```bash
python -m venv .venv
```

```bash
.venv\Scripts\pip install -r requirements.txt
```

On macOS or Linux use `.venv/bin/pip` instead.

The `torch` line pulls a large package. For the CPU build:

```bash
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cpu
```

Then copy the settings file and edit it:

```bash
cp settings_example.json settings.json
```

Set `laptop_server_address` to your laptop's address on the robot's network,
and `number_of_regions_per_textile` to how many areas each textile gets.

## Adding the AI model files

The DINOv2 weights download themselves on the first run, which needs internet
once. After that everything works offline. If you have the previous repository
checked out you can copy its cache instead and skip the download:

```
E:\WRO Textile Analyser\data\weights\hub   ->   saved_ai_files\dinov2_weights\hub
```

**There is no trained classifier yet.** The only saved model in the old
repository was trained on synthetic data for the old gantry robot, and this
code refuses it on purpose. Until one is trained, every scan comes back
Inconclusive with `no_trained_model` in the reasons, which is correct rather
than broken.

`saved_ai_files/README_put_existing_model_files_here.md` has the details.

## Running one test scan

Start the laptop server:

```bash
python -m laptop_connection_code.start_laptop_server
```

It prints what it can and cannot do. Check that honestly before trusting
anything:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

Then flash both ESP boards, open the main ESP32's serial monitor at 115200, and
type:

```
dark
white
textile TEST001
start
```

`dark` is captured with the sensor covered and the lamp off. `white` with a
white card under the sensor and the lamp on. Both only need doing once; they
are kept in the board's flash.

Watch the laptop. You should see each scan area arrive, be joined, and get a
result.

## Collecting the dataset

```bash
python -m dataset_collection_tools.scan_textiles_and_save_them_for_dataset
```

It asks about the textile once, tells you what to type at the robot, and then
files each scan area under the right folder with the right label. Nothing has
to be renamed by hand.

Only textiles marked `verified` become training ground truth. Everything else
is saved and clearly marked so it is never trained on by accident.

Before training, check the folders:

```bash
python -m dataset_collection_tools.check_dataset_folders_and_scan_information
```

And for a spreadsheet of everything collected:

```bash
python -m dataset_collection_tools.make_dataset_summary_csv
```

## Training and testing

```bash
python -m model_training_and_testing.train_svm_using_saved_textile_scans
```

This splits the dataset **by physical textile, never by photo**, tries a few
SVM settings, picks one on the validation textiles, chooses the two decision
thresholds from that same held out data, and measures the result on textiles it
has never seen.

It writes the model to `saved_ai_files/<version>/` and does **not** switch it
on. To use it, copy that folder to `saved_ai_files/active_model/` and restart
the server. Switching models is always a decision somebody made on purpose.

To check a saved model again later:

```bash
python -m model_training_and_testing.test_saved_svm_on_held_out_textiles
```

Training does not happen automatically when the robot starts.

## The tests

```bash
python -m pytest simple_tests -q
```

Sixty small tests. The ones worth knowing about:

- a sharp photo passes the quality check and a blurred one does not
- the colour features come out in the right order and the right number
- two uploads with the same `scan_id` are joined, two with different ids are
  not
- a half whose partner never arrives times out cleanly
- no physical textile ever lands in more than one split
- a missing model file gives a readable error rather than a stack trace

## Common problems

| What you see | Usually |
| --- | --- |
| No `CAMERA_READY` on the main ESP32 | TX and RX not crossed, no common ground, or the baud rates differ |
| `[uart] ignoring:` lines full of nonsense | The two baud rates do not match |
| `ERROR,encoder_and_wheel_settings_not_measured_yet` | The wheel and encoder numbers are still zero. That refusal is deliberate |
| Every photo rejected as blurry | The camera fires before the chassis stops rocking. Raise `SETTLE_AFTER_STOPPING_MS` |
| `colour_calibration_degenerate` | The white reference was captured with the lamp off or the sensor covered |
| `colour_constant_vector` | The I2C bus is stuck. Every channel came back identical |
| Every result is inconclusive | Normal with no trained model. Check `/api/v1/health` |
| A model refuses to load | The feature layout changed since it was trained. Retrain. Do not turn the check off |
| The laptop never answers | One half of the scan never arrived. Check `PHOTO_SENT` and the sensor upload |

More in `project_notes/problems_and_fixes_log.md`.

## What is finished and what is not

**Works, and has been run:**

- the whole laptop pipeline, end to end, including DINOv2
- joining the two uploads by `scan_id`, including the refusals and the timeout
- the photo quality check and the colour calibration
- combining several scan areas into one answer
- the dataset tools and the training code
- all sixty tests

**Written, not yet run on the robot:**

- everything on the MATRIX board
- both UART links
- the camera on real cloth

**Not done at all:**

- no classifier has been trained on real textiles, so the robot cannot yet give
  a handmade or machine answer
- six functions on the MATRIX board are stubs waiting for the MATRIX library
- the wheel, encoder, stepper and pin values still have to be measured

`project_notes/things_i_still_need_from_the_old_repository.md` lists every one
of those with how to get it.

## Where things are

```
matrix_arduino_robot_motion_code/     the MATRIX board
main_esp32_sensor_and_scan_control_code/   the coordinator
xiao_esp32s3_camera_code/             the camera board
laptop_ai_code/                       the AI, stage by stage
laptop_connection_code/               the server the boards talk to
dataset_collection_tools/             collecting and checking scans
model_training_and_testing/           training and measuring
saved_ai_files/                       weights and trained models
collected_textile_dataset/            the scans
verified_reference_textiles/          how the reference bank works
simple_tests/                         the tests
project_notes/                        wiring, decisions, and what is missing
```

Start with `project_notes/how_one_full_textile_scan_moves_through_the_code.md`.
It follows one scan from the robot stopping to the answer, naming every file it
touches on the way.
