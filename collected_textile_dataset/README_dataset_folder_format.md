# collected_textile_dataset

Every scan the team collects, filed by physical textile. This is the data the
classifier is trained on, so how it is organised matters more than it looks.

The folders are in `.gitignore`. A few hundred macro photos would make the
repository unusable. Back them up somewhere else.

## The shape

```
collected_textile_dataset/
  handmade/
    textile_H001/
      textile_information.json
      scan_001/
        textile_photo.jpg
        colour_sensor_readings.json
        scan_information.json
      scan_002/
        ...
    textile_H002/
      ...
  machine/
    textile_M001/
      ...
```

One folder per **physical piece of cloth**. Several scan areas inside it.

That nesting is not decoration. It is what makes it possible to split the
dataset by textile instead of by photo, which is the difference between a real
score and a meaningless one.

## textile_information.json

Everything true about the whole piece of cloth.

```json
{
  "textile_id": "H001",
  "production_label": "handmade",
  "provenance_status": "verified",
  "source_note": "Bought from the weaver in Multan, watched being finished",
  "scan_areas_wanted": 5,
  "usable_as_training_ground_truth": true,
  "hardware_profile": "mobile_mecanum_xiao_v1",
  "preprocessing_version": "2.0.0-xiao",
  "collected_at": "2026-09-02T14:31:07"
}
```

`provenance_status` is one of:

| Value | What it means | Trained on? |
| --- | --- | --- |
| `verified` | Somebody watched it being made, or the weaver confirmed it | Yes |
| `commercial comparison` | Bought as machine made, believed but not confirmed | No, unless you pass `--include-unverified` |
| `unknown` | Nobody knows | No |

**Only `verified` textiles are ground truth.** Everything else is saved and
clearly marked, so it can be looked at without ever being trained on by
accident. A classifier trained on guesses learns the guesses.

## scan_information.json

Everything specific to one area of the cloth: the scan id, the region id, which
row and column, the robot and camera status, and what the quality check found.

## colour_sensor_readings.json

```json
{
  "raw": [9120, 8340, 7015],
  "calibrated": [0.4231, 0.4102, 0.3598],
  "channel_labels": ["red", "green", "blue"]
}
```

Both are kept. The raw counts are the measurement; the calibrated reflectances
are what the AI uses. Keeping the raw values means a calibration mistake can be
corrected later without rescanning the cloth.

## The rule that matters most

**Every scan area of one physical textile goes into exactly one split.**

Five areas of one shawl are five photos of the same cloth, taken centimetres
apart under the same lamp. If some go into training and others into testing,
the classifier gets tested on cloth it has already seen. The score comes out
near perfect and means nothing.

`model_training_and_testing/split_dataset_without_mixing_same_textile.py`
enforces it, and training aborts if the check fails.

Which is also why the `textile_id` has to be right. Two different pieces of
cloth filed under one id, or one piece filed under two, both break it.

## Collecting

```bash
python -m dataset_collection_tools.scan_textiles_and_save_them_for_dataset
```

It asks the questions once, then files each scan area as it arrives. It never
writes over an existing textile folder.

## Checking before you train

```bash
python -m dataset_collection_tools.check_dataset_folders_and_scan_information
```

Missing files, duplicate scan ids, the same textile filed under both labels,
readings with the wrong number of channels, textiles with too few areas.

## How many textiles is enough

Training needs at least two verified textiles of each class, and that is a
floor rather than a target. It is the **number of physical textiles** that
matters, not the number of photos. Ten areas of one shawl is still one piece of
cloth, and the model has still only seen one weaver's work.
