import json
import os
import sys

import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import check_photo_quality_before_using_ai as quality_check
from laptop_ai_code import clean_and_prepare_colour_sensor_readings as colour
from laptop_ai_code import combine_photo_and_sensor_features as fusion
from laptop_ai_code import get_dinov2_features_from_textile_photo as vision
from laptop_ai_code import measure_simple_texture_numbers_from_photo as texture

PRODUCTION_LABELS = ["handmade", "machine"]


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def build_table(only_verified=True, skip_failed_quality=True):
    if not vision.dinov2_is_available():
        raise RuntimeError(
            "DINOv2 will not load, so no features can be built: %s"
            % vision.why_dinov2_is_not_available()
        )

    feature_rows = []
    labels = []
    textile_ids = []
    scan_ids = []
    embeddings = []
    skipped = []
    schema = None

    for production_label in PRODUCTION_LABELS:
        label_folder = os.path.join(settings.DATASET_FOLDER, production_label)
        if not os.path.isdir(label_folder):
            continue

        for textile_folder_name in sorted(os.listdir(label_folder)):
            textile_folder = os.path.join(label_folder, textile_folder_name)
            if not os.path.isdir(textile_folder):
                continue

            information = read_json(
                os.path.join(textile_folder, "textile_information.json"), {}
            )
            textile_id = information.get("textile_id", textile_folder_name)

            if only_verified and not information.get(
                    "usable_as_training_ground_truth", False):
                skipped.append((
                    textile_id,
                    "provenance is '%s', not verified"
                    % information.get("provenance_status", "unknown"),
                ))
                continue

            for area_name in sorted(os.listdir(textile_folder)):
                area_folder = os.path.join(textile_folder, area_name)
                if not area_name.startswith("scan_") or not os.path.isdir(
                        area_folder):
                    continue

                row = build_one_row(area_folder, skip_failed_quality)
                if row is None or row.get("problem"):
                    skipped.append((
                        "%s/%s" % (textile_id, area_name),
                        row["problem"] if row else "could not be read",
                    ))
                    continue

                if schema is None:
                    schema = row["schema"]
                elif (fusion.schema_fingerprint(row["schema"])
                      != fusion.schema_fingerprint(schema)):
                    # The layout changing partway through would quietly corrupt
                    # the table, so the odd row out is dropped rather than
                    # stacked on top of rows that mean something else.
                    skipped.append((
                        "%s/%s" % (textile_id, area_name),
                        "the feature layout changed partway through the build",
                    ))
                    continue

                feature_rows.append(row["vector"])
                embeddings.append(row["embedding"])
                labels.append(production_label)
                textile_ids.append(textile_id)
                scan_ids.append(row["scan_id"])

    if not feature_rows:
        raise RuntimeError(
            "no usable scan areas were found in %s (%d skipped). Collect some "
            "with:\n  python -m dataset_collection_tools."
            "scan_textiles_and_save_them_for_dataset"
            % (settings.DATASET_FOLDER, len(skipped))
        )

    return {
        "features": np.vstack(feature_rows),
        "embeddings": np.vstack(embeddings),
        "labels": np.array(labels, dtype=object),
        "textile_ids": np.array(textile_ids, dtype=object),
        "scan_ids": np.array(scan_ids, dtype=object),
        "schema": schema,
        "skipped": skipped,
    }


def build_one_row(area_folder, skip_failed_quality=True):
    photo_path = os.path.join(area_folder, "textile_photo.jpg")
    if not os.path.exists(photo_path):
        return {"problem": "the photo is missing"}

    scan_information = read_json(
        os.path.join(area_folder, "scan_information.json"), {}
    )
    colour_readings = read_json(
        os.path.join(area_folder, "colour_sensor_readings.json"), {}
    )

    with open(photo_path, "rb") as handle:
        photo_bytes = handle.read()

    quality, photo = quality_check.check_photo(photo_bytes)
    if photo is None:
        return {"problem": "the photo could not be decoded"}
    if skip_failed_quality and not quality["passed"]:
        return {"problem": "failed the quality check: %s"
                           % ", ".join(quality["all_reasons"])}

    calibrated = colour_readings.get("calibrated") or []
    if not calibrated:
        return {"problem": "no calibrated colour values were saved with this "
                           "scan, so it cannot be used for training"}

    visual = vision.get_features_from_photo(photo)
    if not visual["ok"]:
        return {"problem": "DINOv2 found nothing usable: %s"
                           % ", ".join(visual["reasons"])}

    texture_values, texture_names = texture.get_texture_features(photo)
    colour_values = colour.get_colour_features(calibrated)

    vector, schema = fusion.combine(
        embedding=visual["embedding"],
        visual_summary=visual["summary"],
        texture_values=texture_values,
        texture_names=texture_names,
        colour_values=colour_values,
    )

    return {
        "vector": vector,
        "embedding": visual["embedding"],
        "schema": schema,
        "scan_id": scan_information.get("scan_id", os.path.basename(area_folder)),
        "problem": None,
    }


def describe_table(table):
    labels = table["labels"].tolist()
    textile_ids = table["textile_ids"].tolist()

    textiles_per_class = {}
    for label, textile_id in zip(labels, textile_ids):
        textiles_per_class.setdefault(label, set()).add(textile_id)

    return {
        "scan_area_count": int(table["features"].shape[0]),
        "textile_count": len(set(textile_ids)),
        "textiles_per_class": {
            label: len(ids) for label, ids in textiles_per_class.items()},
        "scan_areas_per_class": {
            label: labels.count(label) for label in set(labels)},
        "feature_count": int(table["features"].shape[1]),
        "feature_groups": table["schema"]["groups"],
        "feature_fingerprint": fusion.schema_fingerprint(table["schema"]),
        "skipped_count": len(table["skipped"]),
    }


def main():
    print("building the feature table (this runs DINOv2 on every photo, so it "
          "takes a while)")
    table = build_table()

    print()
    for key, value in describe_table(table).items():
        print("  %-24s %s" % (key, value))

    if table["skipped"]:
        print()
        print("Skipped %d:" % len(table["skipped"]))
        for what, why in table["skipped"][:20]:
            print("  %s: %s" % (what, why))
        if len(table["skipped"]) > 20:
            print("  ... and %d more" % (len(table["skipped"]) - 20))

    return 0


if __name__ == "__main__":
    sys.exit(main())
