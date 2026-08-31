import csv
import json
import os
import sys

from laptop_ai_code import ai_settings_and_thresholds as settings

PRODUCTION_LABELS = ["handmade", "machine"]

COLUMNS = [
    "textile_id",
    "production_label",
    "provenance_status",
    "usable_as_training_ground_truth",
    "scan_area",
    "scan_id",
    "region_id",
    "row_index",
    "column_index",
    "photo_width",
    "photo_height",
    "quality_passed",
    "quality_reasons",
    "colour_raw",
    "colour_calibrated",
    "collected_at",
    "source_note",
]


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def rows_for_one_textile(textile_folder, production_label):
    information = read_json(
        os.path.join(textile_folder, "textile_information.json"), {}
    )

    area_names = sorted(
        name for name in os.listdir(textile_folder)
        if name.startswith("scan_")
        and os.path.isdir(os.path.join(textile_folder, name))
    )

    rows = []
    for area_name in area_names:
        area_folder = os.path.join(textile_folder, area_name)

        scan_information = read_json(
            os.path.join(area_folder, "scan_information.json"), {}
        )
        colour = read_json(
            os.path.join(area_folder, "colour_sensor_readings.json"), {}
        )
        quality = scan_information.get("quality", {})

        rows.append({
            "textile_id": information.get(
                "textile_id", os.path.basename(textile_folder)),
            "production_label": production_label,
            "provenance_status": information.get("provenance_status", "unknown"),
            "usable_as_training_ground_truth": information.get(
                "usable_as_training_ground_truth", False),
            "scan_area": area_name,
            "scan_id": scan_information.get("scan_id", ""),
            "region_id": scan_information.get("region_id", ""),
            "row_index": scan_information.get("row_index", ""),
            "column_index": scan_information.get("column_index", ""),
            "photo_width": quality.get("measurements", {}).get("width", ""),
            "photo_height": quality.get("measurements", {}).get("height", ""),
            "quality_passed": quality.get("photo_ok", ""),
            "quality_reasons": " ".join(quality.get("reasons", [])),
            "colour_raw": " ".join(str(value) for value in colour.get("raw", [])),
            "colour_calibrated": " ".join(
                "%.4f" % value for value in colour.get("calibrated", [])),
            "collected_at": scan_information.get("collected_at", ""),
            "source_note": information.get("source_note", ""),
        })

    return rows


def main():
    if not os.path.isdir(settings.DATASET_FOLDER):
        print("There is no dataset folder at %s yet." % settings.DATASET_FOLDER)
        return 1

    all_rows = []
    for production_label in PRODUCTION_LABELS:
        label_folder = os.path.join(settings.DATASET_FOLDER, production_label)
        if not os.path.isdir(label_folder):
            continue
        for textile_folder_name in sorted(os.listdir(label_folder)):
            textile_folder = os.path.join(label_folder, textile_folder_name)
            if os.path.isdir(textile_folder):
                all_rows.extend(
                    rows_for_one_textile(textile_folder, production_label)
                )

    if not all_rows:
        print("No scan areas found. Collect some first with:")
        print("  python -m dataset_collection_tools."
              "scan_textiles_and_save_them_for_dataset")
        return 1

    output_path = os.path.join(settings.PROJECT_FOLDER, "dataset_summary.csv")
    with open(output_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    textiles = len({row["textile_id"] for row in all_rows})
    print("wrote %d scan areas across %d physical textiles"
          % (len(all_rows), textiles))
    print("  %s" % output_path)
    print()
    print("Remember that the number that matters is the number of TEXTILES,")
    print("not the number of scan areas. Ten areas of one shawl is still one")
    print("piece of cloth.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
