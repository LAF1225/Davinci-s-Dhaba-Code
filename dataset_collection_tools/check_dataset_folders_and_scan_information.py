import json
import os
import sys

from laptop_ai_code import ai_settings_and_thresholds as settings

PRODUCTION_LABELS = ["handmade", "machine"]


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle), None
    except FileNotFoundError:
        return None, "missing"
    except json.JSONDecodeError as problem:
        return None, "not valid JSON: %s" % problem


def check_one_scan_area(area_folder):
    """Return a list of problems with one scan_NNN folder."""
    problems = []

    photo_path = os.path.join(area_folder, "textile_photo.jpg")
    if not os.path.exists(photo_path):
        problems.append("textile_photo.jpg is missing")
    elif os.path.getsize(photo_path) < 1000:
        problems.append("textile_photo.jpg is suspiciously small")

    colour, problem = read_json(
        os.path.join(area_folder, "colour_sensor_readings.json")
    )
    if problem:
        problems.append("colour_sensor_readings.json is " + problem)
    else:
        raw = colour.get("raw", [])
        if not raw:
            problems.append("the colour reading is empty")
        elif len(raw) != settings.COLOUR_SENSOR_CHANNEL_COUNT:
            problems.append(
                "the colour reading has %d channels, expected %d"
                % (len(raw), settings.COLOUR_SENSOR_CHANNEL_COUNT)
            )

    scan_information, problem = read_json(
        os.path.join(area_folder, "scan_information.json")
    )
    if problem:
        problems.append("scan_information.json is " + problem)
    elif not scan_information.get("scan_id"):
        problems.append("scan_information.json has no scan_id")

    return problems, (scan_information or {}).get("scan_id")


def check_everything():
    problems_by_folder = {}
    textiles_by_id = {}
    scan_ids_seen = {}
    total_scan_areas = 0

    if not os.path.isdir(settings.DATASET_FOLDER):
        print("There is no dataset folder at %s yet." % settings.DATASET_FOLDER)
        return 1

    for production_label in PRODUCTION_LABELS:
        label_folder = os.path.join(settings.DATASET_FOLDER, production_label)
        if not os.path.isdir(label_folder):
            continue

        for textile_folder_name in sorted(os.listdir(label_folder)):
            textile_folder = os.path.join(label_folder, textile_folder_name)
            if not os.path.isdir(textile_folder):
                continue

            problems = []

            information, problem = read_json(
                os.path.join(textile_folder, "textile_information.json")
            )
            if problem:
                problems.append("textile_information.json is " + problem)
                information = {}

            textile_id = information.get("textile_id", textile_folder_name)

            # The same physical textile filed under both labels means one of
            # the two labels is wrong, and training on it would teach the
            # classifier that the same cloth is both.
            if textile_id in textiles_by_id:
                first_label = textiles_by_id[textile_id]["production_label"]
                if first_label != production_label:
                    problems.append(
                        "this textile id is also filed under '%s'" % first_label
                    )
            else:
                textiles_by_id[textile_id] = {
                    "production_label": production_label,
                    "folder": textile_folder,
                    "provenance": information.get("provenance_status", "unknown"),
                    "ground_truth": information.get(
                        "usable_as_training_ground_truth", False),
                    "scan_areas": 0,
                }

            area_folders = sorted(
                name for name in os.listdir(textile_folder)
                if name.startswith("scan_")
                and os.path.isdir(os.path.join(textile_folder, name))
            )

            if not area_folders:
                problems.append("no scan areas at all")

            for area_name in area_folders:
                area_folder = os.path.join(textile_folder, area_name)
                area_problems, scan_id = check_one_scan_area(area_folder)
                for area_problem in area_problems:
                    problems.append("%s: %s" % (area_name, area_problem))

                if scan_id:
                    if scan_id in scan_ids_seen:
                        problems.append(
                            "%s: scan_id %s is already used by %s"
                            % (area_name, scan_id, scan_ids_seen[scan_id])
                        )
                    else:
                        scan_ids_seen[scan_id] = "%s/%s" % (
                            textile_folder_name, area_name)

                total_scan_areas += 1
                if textile_id in textiles_by_id:
                    textiles_by_id[textile_id]["scan_areas"] += 1

            if problems:
                problems_by_folder[textile_folder] = problems

    return report(textiles_by_id, problems_by_folder, total_scan_areas)


def report(textiles_by_id, problems_by_folder, total_scan_areas):
    print()
    print("=" * 68)
    print("DATASET CHECK")
    print("=" * 68)
    print()

    ground_truth = {label: 0 for label in PRODUCTION_LABELS}
    other = {label: 0 for label in PRODUCTION_LABELS}

    for details in textiles_by_id.values():
        bucket = ground_truth if details["ground_truth"] else other
        bucket[details["production_label"]] += 1

    print("Physical textiles")
    for label in PRODUCTION_LABELS:
        print("  %-10s verified: %-4d other provenance: %d"
              % (label, ground_truth[label], other[label]))
    print("  total scan areas: %d" % total_scan_areas)
    print()

    thin = [
        (textile_id, details) for textile_id, details in textiles_by_id.items()
        if details["scan_areas"] < 3
    ]
    if thin:
        print("Textiles with fewer than three scan areas:")
        for textile_id, details in sorted(thin):
            print("  %-12s %d area(s)" % (textile_id, details["scan_areas"]))
        print("  One or two areas is not enough to say anything about a piece")
        print("  of cloth, and they will drag the training set around.")
        print()

    if problems_by_folder:
        print("Problems")
        for folder in sorted(problems_by_folder):
            print("  %s" % folder)
            for problem in problems_by_folder[folder]:
                print("    - %s" % problem)
        print()
    else:
        print("No problems found in the folders.")
        print()

    smallest_class = min(ground_truth.values()) if ground_truth else 0
    if smallest_class < 2:
        print("NOT READY TO TRAIN")
        print("  Training needs at least two verified textiles of each class,")
        print("  so that a split by textile can put different cloth on each")
        print("  side. There are %d handmade and %d machine."
              % (ground_truth["handmade"], ground_truth["machine"]))
        print()
        return 1

    if problems_by_folder:
        print("Fix the problems above before training.")
        return 1

    print("The dataset looks usable.")
    return 0


if __name__ == "__main__":
    sys.exit(check_everything())
