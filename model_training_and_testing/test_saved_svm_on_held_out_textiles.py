import argparse
import os
import sys

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import combine_photo_and_sensor_features as fusion
from laptop_ai_code import load_saved_ai_files as model_files
from model_training_and_testing import build_feature_table_from_dataset as table_builder
from model_training_and_testing import print_simple_model_results as results


def main():
    parser = argparse.ArgumentParser(
        description="Test a saved model on the textiles it never saw")
    parser.add_argument("--model", default=None,
                        help="the saved model folder (default: the active one)")
    parser.add_argument("--all-textiles", action="store_true",
                        help="test on every textile in the dataset, including "
                             "the ones it was trained on. Only useful for "
                             "debugging, and the score means nothing.")
    arguments = parser.parse_args()

    model_folder = arguments.model or settings.SAVED_MODEL_FOLDER

    print("=" * 70)
    print("TESTING A SAVED MODEL")
    print("=" * 70)
    print()

    try:
        expected_schema = fusion.describe_expected_schema()
        model = model_files.load_model_folder(model_folder, expected_schema)
    except model_files.ModelFilesMissing as problem:
        print("Cannot test: %s" % problem, file=sys.stderr)
        return 1
    except model_files.ModelDoesNotMatchThisCode as problem:
        print("Cannot test: %s" % problem, file=sys.stderr)
        print(file=sys.stderr)
        print("This means the code now builds a different feature vector than "
              "the one this model was trained on. Either use the version of "
              "the code the model was trained with, or retrain.",
              file=sys.stderr)
        return 1

    information = model["information"]
    print("Model %s" % model["version"])
    print("  trained on %s textiles"
          % information.get("textile_count", "an unrecorded number of"))
    print("  notes: %s" % (information.get("notes") or "(none)"))
    print()

    test_textiles = set(information.get("test_textile_ids", []))
    train_textiles = set(information.get("train_textile_ids", []))

    if not test_textiles and not arguments.all_textiles:
        print("This model does not record which textiles were held out, so "
              "there is no honest test set to use. Retrain it, or pass "
              "--all-textiles and treat the result as a debugging number "
              "rather than a result.", file=sys.stderr)
        return 1

    print("building features (DINOv2 runs on every photo, so this takes a "
          "while)")
    table = table_builder.build_table()
    print()

    if arguments.all_textiles:
        keep = [True] * len(table["textile_ids"])
        title = "EVERY TEXTILE, INCLUDING TRAINING ONES"
        print("WARNING: this includes textiles the model was trained on. The")
        print("score below is not a measure of how well it generalises.")
        print()
    else:
        keep = [str(textile_id) in test_textiles
                for textile_id in table["textile_ids"]]
        title = "HELD OUT TEST TEXTILES"

    if not any(keep):
        print("None of the model's test textiles are in the dataset folders "
              "any more. Were they moved or renamed?", file=sys.stderr)
        print("  the model expected: %s" % sorted(test_textiles),
              file=sys.stderr)
        return 1

    leaked = {
        str(textile_id) for textile_id, wanted in zip(table["textile_ids"], keep)
        if wanted and str(textile_id) in train_textiles
    }
    if leaked and not arguments.all_textiles:
        print("STOPPING: %s appear in both this model's training list and its "
              "test list. Something is wrong with the saved model's records, "
              "and any score measured here would be meaningless."
              % sorted(leaked), file=sys.stderr)
        return 2

    import numpy as np

    keep = np.array(keep, dtype=bool)
    measured = results.measure_one_split(
        model["pipeline"],
        table["features"][keep],
        table["labels"][keep],
        table["textile_ids"][keep],
    )
    results.print_results(measured, title)

    thresholds = model_files.decision_thresholds_from_model(information)
    if thresholds:
        print("This model carries thresholds chosen on validation data:")
        print("  handmade at %.2f or above, machine at %.2f or below"
              % (thresholds["handmade_min"], thresholds["machine_max"]))
        print("  Note that the numbers above use a plain 0.5 split, so they")
        print("  do not include the inconclusive band the robot actually uses.")
    else:
        print("This model carries no validated thresholds, so the robot will "
              "use the values in ai_settings_and_thresholds.py.")

    print()
    print("Saved model folder: %s" % os.path.abspath(model_folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
