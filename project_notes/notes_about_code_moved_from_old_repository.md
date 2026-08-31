# What came across from the old repository

The old repository is `LAF1225/textiles-ai-thingy`, checked out locally at
`E:\WRO Textile Analyser`. It was read at commit `a9e2e5d`, with the
HandloomGCN work still uncommitted in the working tree.

The rule for this migration was: reuse the AI, replace the hardware code. The
AI in that repository works and has been thought about carefully. The firmware
in it was written for a different robot and says so in its own README.

## The AI, moved with the maths unchanged

| Old file | New file | What was reused | What changed, and why |
| --- | --- | --- | --- |
| `server/ai/image_quality.py` | `laptop_ai_code/check_photo_quality_before_using_ai.py` | Every check and every threshold: decode, size, variance of Laplacian, mean brightness, clipped pixel fractions, brightness spread, local contrast over an 8 by 8 grid | Returns `{"passed", "reason", "all_reasons", ...}` instead of a dataclass, because the PRD asks for that shape. The reason codes are unchanged. Thresholds moved from `config/app.yaml` into `ai_settings_and_thresholds.py` |
| `server/ai/dinov2_extractor.py` | `laptop_ai_code/get_dinov2_features_from_textile_photo.py` | Tiling, background tile dropping, most-textured-first selection, ImageNet normalisation, the multiple-of-14 input size, mean tile embedding, the five summary statistics, frozen eval mode with grads off, local weight cache | The class became module level functions with a lock, which is the same behaviour with less structure. The `image_cache_key` embedding cache was dropped: it belonged to the old repository's queue and database |
| `server/ai/spectral_preprocessor.py` | `laptop_ai_code/clean_and_prepare_colour_sensor_readings.py` | The calibration formula, the epsilon, the clamp range, the validation rules, the degenerate calibration check, and every derived feature group in the same order | Feature names changed from `spec_*` to `colour_*`. See "Things that were deliberately changed" below |
| `server/ai/image_features.py` | `laptop_ai_code/measure_simple_texture_numbers_from_photo.py` | All ten measurements, unchanged: grey contrast, RMS contrast, LBP uniformity and entropy, Canny edge density with Otsu thresholds, doubled-angle edge orientation, radial FFT peak, local contrast variability | Only names and comments |
| `server/ai/feature_fusion.py` | `laptop_ai_code/combine_photo_and_sensor_features.py` | The fixed group order, the schema record, the fingerprint hash, the compatibility check and its readable failure messages | Dataclasses became dictionaries, which is what the schema is saved as anyway. Two feature groups were dropped, see below |
| `server/ai/classifier.py` | `laptop_ai_code/load_saved_ai_files.py` and `laptop_ai_code/run_saved_svm_textile_prediction.py` | The artifact file names, saving and loading, the scaler living inside the sklearn Pipeline, refusing a model whose schema does not match | The production versus benchmark check was dropped, because there is no benchmark model in this repository and nothing to confuse a production model with |
| `server/ai/reference_matcher.py` | `laptop_ai_code/compare_scan_with_verified_reference_textiles.py` | Cosine similarity, the two separate banks, top k matches, the out of domain rule at 0.35, the npz save format | Names only |
| `server/ai/decision_engine.py` | the second half of `laptop_ai_code/run_saved_svm_textile_prediction.py` | The whole decision order: quality gate, no classifier, out of domain, weak reference similarity, uncertainty band, confident call. The rescan limit. Comparing against the threshold rather than against the other probability. The reason priority list | Action names became the PRD's command words |
| `server/ai/aggregation.py` | `laptop_ai_code/combine_results_from_different_scan_areas.py` | Median rather than mean, the supporting fraction rule, the three disqualifiers, quadrant based regional disagreement, and the exact user facing wording | Coverage of the planned grid was simplified to a count of scan areas. The old version needed the session and grid tables from the database |
| `training/create_splits.py` | `model_training_and_testing/split_dataset_without_mixing_same_textile.py` | Grouping by physical textile, the per class split, the small dataset special cases, the leakage check that aborts training, the separate message for a textile labelled two ways, grouped cross validation folds | Names only |
| `training/thresholds.py` | `model_training_and_testing/choose_decision_thresholds_from_validation.py` | The whole grid search, the false machine rate as a hard limit, the margin tie break, the check that a pair actually predicts both classes, the fallback that reports itself as not good enough | Names only |
| `training/evaluate.py` | `model_training_and_testing/print_simple_model_results.py` | Balanced accuracy, macro F1, per class precision and recall, the confusion matrix, textile level results from median scores, and the two error directions named separately | Names only |
| `training/train_svm.py` | `model_training_and_testing/train_svm_using_saved_textile_scans.py` | The candidate search, `class_weight="balanced"`, calibration wrapping the whole scaler and SVM pipeline, the safe fold count, building the reference bank from training textiles only, and never activating a new model automatically | Reads the dataset folders instead of the SQLite reference library, because that is where the new dataset collection tool puts things |
| `training/build_features.py` | `model_training_and_testing/build_feature_table_from_dataset.py` | Building features with the same code the robot uses, and refusing a row whose feature layout differs from the rest | Same reason as above |
| `firmware/esp32/src/api_client.cpp` | `xiao_camera_wait_for_scan_take_photo_and_send_to_laptop.ino` and `main_esp32_read_colour_sensor_make_scan_id_and_send_to_laptop.ino` | The hand assembled multipart upload with one buffer, the retry with growing backoff, treating HTTP 202 as success, and the result polling with backoff | Split across two boards. The XIAO does the multipart photo upload, the main ESP32 does the JSON sensor upload and the polling |
| `firmware/esp32/src/camera_adapter.cpp` | `xiao_camera_wait_for_scan_take_photo_and_send_to_laptop.ino` | Fixing white balance and gain so the camera does not retune itself between scan areas, PSRAM handling, returning the frame buffer whatever happens | The pin map is not reused. The old one was for "a common ESP32-S3 camera module", not for the XIAO. The new sketch takes the vendor pin map from `camera_pins.h` instead |
| `firmware/esp32/src/wifi_manager.cpp` | both `.ino` files | Station mode, sleep off, the connect timeout, the rate limited reconnect | Inlined, because it is about fifteen lines |

## Things that were deliberately changed

Each of these changes the feature vector, which changes its fingerprint, which
means a model trained before the change will refuse to load rather than
silently producing worse answers. That refusal is the whole point of the
fingerprint.

None of them break an existing model in practice, because there is no existing
model for this robot. See `things_i_still_need_from_the_old_repository.md`.

**The IR branch was not migrated.** The old `config/hardware.yaml` describes
the current robot as `mobile_mecanum_v1` with `ir: false`, so the IR feature
group was already switched off for this hardware. Carrying `ir_preprocessor.py`
across would have been code for a sensor the robot does not have.

**The external HandloomGCN reference branch was not migrated.** In the old
repository `external_reference.enabled` is `false` and `use_as_features` is
`false`, so it contributed nothing to the classifier. The dataset it needs has
not been obtained yet. If that work continues, the branch is still in the old
repository at `server/ai/external_reference.py` and
`training/import_handloomgcn.py`.

**The colour features were renamed from `spec_*` to `colour_*`.** The maths is
identical. The old repository was careful to record the sensor as `type: color`
rather than `multispectral`, on the grounds that calling an RGB reading
spectral reflectance would be a false claim, but its feature branch was still
named `spectral`. The new names match what the sensor actually is.

**`BAND_RATIO_PAIRS` changed from `[[0,7],[1,4],[2,6]]` to
`[[0,2],[0,1],[1,2]]`.** The old pairs were chosen for an eight channel
spectrometer. With three channels, indexes 4, 6 and 7 do not exist, and the old
code would have written a zero into each of those columns. The new pairs are
red over blue, red over green and green over blue.

**The scan record database is plain `sqlite3` instead of SQLAlchemy.** The old
repository had an ORM, a migration system and a repository layer. That is a lot
of machinery for a table the robot writes a few hundred rows a day into, and
the PRD asks for code without repository and service layers. The column names
were kept the same, so anyone who has read the old database can read this one.

**The web dashboard, the session and device APIs, the calibration API, the
model registry API and the queue service were not migrated.** They are not
needed to run the robot, and the PRD rules them out.

## Files added that the PRD's structure does not list

The PRD says the structure may be adjusted where the old AI code requires it.
These five are why:

| File | Why it exists |
| --- | --- |
| `laptop_ai_code/measure_simple_texture_numbers_from_photo.py` | The old feature vector includes ten interpretable image measurements. Dropping them would have changed the AI, which this migration is not supposed to do, and there was no file in the PRD list for them |
| `laptop_ai_code/run_one_complete_scan_through_the_ai.py` | Something has to run the stages in order. Putting that inside the web server would have hidden the most important sequence in the project |
| `laptop_connection_code/start_laptop_server.py` | Something has to assemble the two endpoints and start the server |
| `model_training_and_testing/choose_decision_thresholds_from_validation.py` | A port of `training/thresholds.py`. Dropping it would have meant going back to a hard coded band, which is a change in AI behaviour |
| `model_training_and_testing/build_feature_table_from_dataset.py` | Both the training and the testing script need it, and two copies would drift apart |

## One place where the code does not do what the PRD describes

The PRD says `scan_textiles_and_save_them_for_dataset.py` should "request one
coordinated scan through the main ESP32". It does not. The robot run is started
by typing `textile <id>` and `start` at the main ESP32's serial monitor, and
the script then watches the laptop server and files each scan as it arrives.

The reason: giving the laptop a command channel down to the robot would mean
the main ESP32 polling for instructions it does not otherwise need, and an
operator is standing next to the robot anyway to place the cloth, switch on the
lamp and calibrate the sensor. The script prints exactly what to type. If the
team later wants the laptop to drive the run, the place to add it is a small
instruction endpoint the main ESP32 polls while idle.
