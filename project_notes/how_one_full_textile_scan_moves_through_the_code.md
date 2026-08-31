# One scan, from the robot stopping to the answer

Follow one scan area all the way through. Every file it touches is named, in
the order it touches them.

## 1. The robot stops

The main ESP32 sends `MOVE_NEXT` to the MATRIX board.

`matrix_move_robot_and_control_scan_axis.ino` drives the mecanum wheels one
scan spacing, watching the encoders, then stops the motors and waits
`SETTLE_AFTER_STOPPING_MS` for the chassis to stop rocking. Only then does it
answer `DONE`.

That settle matters. The camera must not fire while the robot is still moving,
or every photo comes back blurred and the laptop rejects all of them.

## 2. The main ESP32 makes a scan id

`main_esp32_read_colour_sensor_make_scan_id_and_send_to_laptop.ino` builds one
id, like `H001_R2_48213`, and one region id, like `R2`.

One board owns the id. See `how_the_two_esp_boards_share_one_scan_id.md`.

## 3. The camera is told to fire

`TAKE_SCAN,H001_R2_48213,R2,2,0` goes down the UART.

`xiao_camera_receive_scan_id_from_main_esp32.h` parses it, then
`xiao_camera_wait_for_scan_take_photo_and_send_to_laptop.ino` captures one
frame and answers `PHOTO_CAPTURED,H001_R2_48213`.

## 4. The colour sensor is read

While the photo uploads, the main ESP32 sends `READ_COLOUR` to the MATRIX
board, which averages five readings and answers `COLOUR,9120,8340,7015`.

Raw counts, not percentages. The laptop does the calibration and needs the raw
numbers to do it.

## 5. Both halves go to the laptop, separately

The XIAO posts the JPEG to `/api/v1/scan_photo` and then reports
`PHOTO_SENT,H001_R2_48213`.

The main ESP32 posts the colour reading, the calibration references and the
metadata to `/api/v1/scan_sensors`.

Two uploads, two routes, same id.

## 6. The laptop joins them

`laptop_connection_code/receive_camera_photo_from_xiao.py` and
`receive_sensor_values_from_main_esp32.py` each hand their half to
`match_photo_and_sensor_data_using_scan_id.py`.

Whichever arrives first waits. When both are there they become one record.

## 7. The raw evidence is saved before anything else happens

`start_laptop_server.py` writes the photo to disk and the row to SQLite
through `save_scan_information_to_existing_database.py`, on the request
thread, before queueing any AI work.

If the laptop crashes during inference, the prediction is lost and the evidence
is not.

## 8. The AI, in order

`laptop_ai_code/run_one_complete_scan_through_the_ai.py` runs the stages. One
scan at a time, on a background worker, because DINOv2 on a laptop CPU takes a
few seconds and running several at once makes all of them slower.

**Photo quality**, `check_photo_quality_before_using_ai.py`. Decodable, big
enough, sharp enough, not too dark or too bright, not clipped, not flat.

**Colour calibration**, `clean_and_prepare_colour_sensor_readings.py`. Checks
the reading, then turns raw counts into reflectance using the dark and white
references that came with it.

**Stop here if either failed.** The result is `unusable`, the command back is
`rescan`, and DINOv2 never runs. Classifying a blurry photo would produce a
number that looks exactly like a real one.

**DINOv2**, `get_dinov2_features_from_textile_photo.py`. The photo is cut into
overlapping tiles, background tiles are dropped, the most textured ones are
kept, each goes through the frozen network, and the average becomes the
embedding. Five numbers describing how much the tiles disagreed are added.

**Texture measurements**, `measure_simple_texture_numbers_from_photo.py`. Ten
readable numbers: contrast, local binary patterns, edge density, thread
direction, the strongest repeated spacing.

**Colour features**, back in the colour file. Three reflectances become sixteen
numbers: the bands, differences between them, ratios, and summary statistics.

**Combine**, `combine_photo_and_sensor_features.py`. 384 + 5 + 10 + 16 = 415
numbers, always in that order, with a record of what every column means.

**Compare with the references**,
`compare_scan_with_verified_reference_textiles.py`. Cosine similarity against
the verified handmade and machine banks. Far from both means we have never seen
anything like this cloth.

**The classifier**, `run_saved_svm_textile_prediction.py`. The saved
StandardScaler and SVM run as one pipeline. It only runs if the feature layout
matches what the model was trained on.

**Decide**, in the same file. Quality, then out of domain, then weak
similarity, then the uncertainty band, then a confident call. A score inside
the band is inconclusive no matter how the two probabilities compare.

## 9. One command goes back

`continue`, `rescan`, `complete`, or `inspect_neighbours`.

The main ESP32 has been polling `/api/v1/scan_result/H001_R2_48213` since it
uploaded, backing off as it waits. It acts on whatever comes back:

- `rescan`: stay exactly where you are and scan again. Moving would photograph
  a different piece of cloth.
- `complete`: the textile is done.
- anything else: move to the next area.

## 10. When the textile is finished

`combine_results_from_different_scan_areas.py` takes every scan area and
produces one answer.

The median score, not the mean. The fraction of areas that agree. Whether the
areas disagree too much. Whether one quadrant of the cloth looks different from
the rest. Whether too many areas were inconclusive.

If any of those say the evidence is weak, the answer is Inconclusive.

The wording is fixed, in `run_saved_svm_textile_prediction.py`:

- Likely consistent with handmade production
- Likely consistent with machine production
- Inconclusive

Never authentic, never certified, never definitely.

## What happens when things are missing

| Missing | What happens |
| --- | --- |
| DINOv2 will not load | Scans are still collected and stored. Every result is inconclusive, with `dinov2_unavailable` in the reasons |
| No trained model | Same, with `no_trained_model`. The reference comparison still runs and is reported separately |
| No reference textiles | Every scan is out of domain, so every answer is inconclusive |
| The model does not match the code | It is refused at load time with a readable reason, rather than being fed columns that mean something else |
| One half of a scan never arrives | Times out after thirty seconds, logged, that area gets rescanned |

None of these produce a guess. That is the point.
