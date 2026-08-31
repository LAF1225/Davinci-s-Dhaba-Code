import json
import os
import shutil
import sys
import time

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import check_photo_quality_before_using_ai as quality_check
from laptop_connection_code import save_scan_information_to_existing_database as store

PRODUCTION_LABELS = ["handmade", "machine"]
PROVENANCE_LEVELS = ["verified", "commercial comparison", "unknown"]


def ask(question, allowed=None, default=None):
    """Ask one question and keep asking until the answer is usable."""
    while True:
        prompt = question
        if allowed:
            prompt += " (" + " / ".join(allowed) + ")"
        if default is not None:
            prompt += " [" + str(default) + "]"
        prompt += ": "

        answer = input(prompt).strip()

        if not answer and default is not None:
            return default
        if not answer:
            print("  that cannot be empty")
            continue
        if allowed and answer not in allowed:
            print("  please answer with one of: " + ", ".join(allowed))
            continue
        return answer


def ask_for_a_number(question, default):
    while True:
        answer = input("%s [%d]: " % (question, default)).strip()
        if not answer:
            return default
        try:
            value = int(answer)
        except ValueError:
            print("  that is not a whole number")
            continue
        if value < 1:
            print("  it has to be at least 1")
            continue
        return value


def folder_for_textile(textile_id, production_label):
    return os.path.join(settings.DATASET_FOLDER, production_label,
                        "textile_" + textile_id)


def collect_textile_information():
    """Ask about the physical textile once, at the start."""
    print()
    print("=" * 68)
    print("COLLECTING SCANS FOR THE DATASET")
    print("=" * 68)
    print()

    textile_id = ask("Textile ID (for example H001 or M014)")
    production_label = ask("Production label", allowed=PRODUCTION_LABELS)
    provenance = ask("Provenance status", allowed=PROVENANCE_LEVELS)
    source_note = ask("Source note (where it came from, who confirmed it)",
                      default="not recorded")
    scan_areas_wanted = ask_for_a_number(
        "Number of scan areas to collect", settings.SCAN_AREAS_PER_TEXTILE
    )

    folder = folder_for_textile(textile_id, production_label)
    if os.path.exists(folder):
        # Never quietly write over an earlier session. Two different pieces of
        # cloth ending up in one folder is the kind of mistake that is
        # impossible to unpick afterwards.
        print()
        print("STOPPING: %s already exists." % folder)
        print("Either this textile has been scanned before, or the id is")
        print("already taken by a different piece of cloth. Pick a new id, or")
        print("move the old folder somewhere else first.")
        return None

    information = {
        "textile_id": textile_id,
        "production_label": production_label,
        "provenance_status": provenance,
        "source_note": source_note,
        "scan_areas_wanted": scan_areas_wanted,
        # Only verified textiles are ground truth. Everything else is saved,
        # clearly marked, and left out of supervised training unless someone
        # deliberately includes it.
        "usable_as_training_ground_truth": provenance == "verified",
        "hardware_profile": settings.HARDWARE_PROFILE_NAME,
        "preprocessing_version": settings.PREPROCESSING_VERSION,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "folder": folder,
    }

    if provenance != "verified":
        print()
        print("NOTE: provenance is '%s', so these scans will be saved but "
              "marked" % provenance)
        print("as not usable as training ground truth. Only verified textiles")
        print("go into the labelled training set.")

    return information


def save_textile_information(information):
    os.makedirs(information["folder"], exist_ok=True)
    path = os.path.join(information["folder"], "textile_information.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(information, handle, indent=2)
    return path


def save_one_scan_area(information, area_number, scan_row):
    """Copy one scan out of the server's records and into the dataset folder."""
    area_folder = os.path.join(information["folder"], "scan_%03d" % area_number)
    os.makedirs(area_folder, exist_ok=True)

    # The raw photo, before any AI touched it.
    photo_destination = os.path.join(area_folder, "textile_photo.jpg")
    if scan_row["photo_path"] and os.path.exists(scan_row["photo_path"]):
        shutil.copyfile(scan_row["photo_path"], photo_destination)
    else:
        return None, "the photo file is missing from the server's records"

    # The raw sensor readings, before calibration.
    colour_path = os.path.join(area_folder, "colour_sensor_readings.json")
    with open(colour_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "raw": json.loads(scan_row["raw_colour_json"] or "[]"),
                "calibrated": json.loads(
                    scan_row["calibrated_colour_json"] or "[]"),
                "channel_labels": settings.COLOUR_SENSOR_CHANNEL_LABELS,
            },
            handle,
            indent=2,
        )

    scan_information = {
        "scan_id": scan_row["scan_id"],
        "textile_id": information["textile_id"],
        "region_id": scan_row["region_id"],
        "scan_area_number": area_number,
        "row_index": scan_row["row_index"],
        "column_index": scan_row["column_index"],
        "x_position": scan_row["x_position"],
        "y_position": scan_row["y_position"],
        "robot_status": scan_row["robot_status"],
        "camera_status": scan_row["camera_status"],
        "quality": json.loads(scan_row["quality_json"] or "{}"),
        "collected_at": scan_row["created_at"],
    }
    information_path = os.path.join(area_folder, "scan_information.json")
    with open(information_path, "w", encoding="utf-8") as handle:
        json.dump(scan_information, handle, indent=2)

    return area_folder, None


def check_the_photo(area_folder):
    """Run the same quality check the AI uses, and say what it found."""
    photo_path = os.path.join(area_folder, "textile_photo.jpg")
    with open(photo_path, "rb") as handle:
        photo_bytes = handle.read()

    result, _ = quality_check.check_photo(photo_bytes)

    if result["passed"]:
        print("  quality check: passed")
    else:
        print("  quality check: FAILED (%s)" % ", ".join(result["all_reasons"]))

    measurements = result["measurements"]
    if "blur_variance" in measurements:
        print("    sharpness  %.1f (needs %.0f or more)"
              % (measurements["blur_variance"], settings.MINIMUM_SHARPNESS))
    if "mean_luminance" in measurements:
        print("    brightness %.1f" % measurements["mean_luminance"])
    if "width" in measurements:
        print("    size       %d by %d"
              % (measurements["width"], measurements["height"]))

    return result


def wait_for_a_new_scan(textile_id, already_seen, timeout_seconds=300):
    """Wait until the server has a scan for this textile we have not filed yet."""
    started_at = time.time()
    dots_printed = 0

    while time.time() - started_at < timeout_seconds:
        connection = store.open_database()
        try:
            rows = connection.execute(
                "SELECT * FROM scans WHERE textile_id = ? ORDER BY created_at",
                (textile_id,),
            ).fetchall()
        finally:
            connection.close()

        for row in rows:
            if row["scan_id"] in already_seen:
                continue
            # Wait until the server has finished with it, so the quality and
            # calibrated values are filled in.
            if row["status"] == "stored":
                continue
            if dots_printed:
                print()
            return dict(row)

        print(".", end="", flush=True)
        dots_printed += 1
        time.sleep(2)

    if dots_printed:
        print()
    return None


def main():
    information = collect_textile_information()
    if information is None:
        return 1

    save_textile_information(information)

    print()
    print("-" * 68)
    print("Now open the main ESP32 serial monitor at 115200 and type:")
    print()
    print("    textile %s" % information["textile_id"])
    print("    start")
    print()
    print("Then come back here. Every scan area that arrives will be filed")
    print("under %s" % information["folder"])
    print("Press ctrl+c to stop early.")
    print("-" * 68)

    already_seen = set()
    area_number = 1
    rejected = 0

    while area_number <= information["scan_areas_wanted"]:
        print()
        print("waiting for scan area %d of %d"
              % (area_number, information["scan_areas_wanted"]))

        scan_row = wait_for_a_new_scan(information["textile_id"], already_seen)
        if scan_row is None:
            print("nothing arrived for five minutes. Is the robot running?")
            keep_waiting = ask("Keep waiting", allowed=["yes", "no"],
                               default="yes")
            if keep_waiting == "no":
                break
            continue

        if scan_row["scan_id"] in already_seen:
            # Should not happen, but a duplicate id would silently overwrite a
            # scan area, so it is worth saying out loud.
            print("  WARNING: scan_id %s has already been filed, skipping it"
                  % scan_row["scan_id"])
            continue

        already_seen.add(scan_row["scan_id"])

        print("  scan_id %s" % scan_row["scan_id"])
        area_folder, problem = save_one_scan_area(
            information, area_number, scan_row
        )
        if problem:
            print("  could not save it: %s" % problem)
            continue

        quality = check_the_photo(area_folder)

        default_answer = "keep" if quality["passed"] else "reject"
        choice = ask("  Keep this scan area", allowed=["keep", "reject"],
                     default=default_answer)

        if choice == "reject":
            shutil.rmtree(area_folder)
            rejected += 1
            print("  rejected and deleted. Rescan this area on the robot.")
            continue

        print("  saved as scan_%03d" % area_number)
        area_number += 1

    print()
    print("=" * 68)
    print("Done with textile %s" % information["textile_id"])
    print("  scan areas kept     : %d" % (area_number - 1))
    print("  scan areas rejected : %d" % rejected)
    print("  folder              : %s" % information["folder"])
    if not information["usable_as_training_ground_truth"]:
        print()
        print("  These scans are marked NOT usable as training ground truth,")
        print("  because the provenance is '%s'."
              % information["provenance_status"])
    print("=" * 68)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print("stopped. Everything saved so far is still on disk.")
        sys.exit(1)
