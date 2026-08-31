import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone

import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import load_saved_ai_files as model_files
from laptop_ai_code.compare_scan_with_verified_reference_textiles import (
    ReferenceLibrary,
)
from model_training_and_testing import build_feature_table_from_dataset as table_builder
from model_training_and_testing import choose_decision_thresholds_from_validation as pick_thresholds
from model_training_and_testing import print_simple_model_results as results
from model_training_and_testing.split_dataset_without_mixing_same_textile import (
    TextileAppearsInTwoSplits,
    describe_split,
    grouped_cross_validation_folds,
    split_by_textile,
)


def build_scaler_and_svm(kernel="linear", c_value=1.0, gamma="scale",
                         calibration_folds=3):
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC

    svm_settings = {
        "kernel": kernel,
        "C": float(c_value),
        # With more machine textiles than handmade ones, an unbalanced SVM
        # learns to say machine. This weights the smaller class up.
        "class_weight": "balanced",
        "random_state": settings.RANDOM_SEED,
    }
    if kernel == "rbf":
        svm_settings["gamma"] = gamma

    scaler_then_svm = Pipeline(steps=[
        ("scaler", StandardScaler()),
        ("svm", SVC(**svm_settings)),
    ])

    return CalibratedClassifierCV(
        estimator=scaler_then_svm,
        method=settings.PROBABILITY_CALIBRATION_METHOD,
        cv=calibration_folds,
    )


def settings_to_try():
    candidates = []
    for c_value in settings.LINEAR_C_VALUES:
        candidates.append({"kernel": "linear", "C": float(c_value),
                           "gamma": "scale"})
    for c_value in settings.RBF_C_VALUES:
        for gamma in settings.RBF_GAMMA_VALUES:
            candidates.append({"kernel": "rbf", "C": float(c_value),
                               "gamma": gamma})
    return candidates


def safe_calibration_folds(labels):
    wanted = settings.PROBABILITY_CALIBRATION_FOLDS
    labels = np.asarray(labels)
    counts = [int((labels == label).sum()) for label in set(labels.tolist())]
    smallest = min(counts) if counts else 0
    if smallest < 2:
        return 2
    return max(2, min(wanted, smallest))


def fit_one(candidate, features, labels):
    model = build_scaler_and_svm(
        kernel=candidate["kernel"],
        c_value=candidate["C"],
        gamma=candidate["gamma"],
        calibration_folds=safe_calibration_folds(labels),
    )
    model.fit(features, labels)
    return model


def pick_the_best_settings(table, split):
    features = table["features"]
    labels = table["labels"]
    textile_ids = table["textile_ids"]

    train_rows = split["train_rows"]
    validation_rows = split["validation_rows"]

    use_cross_validation = validation_rows.size == 0
    folds = []
    if use_cross_validation:
        folds = grouped_cross_validation_folds(
            labels[train_rows].tolist(),
            textile_ids[train_rows].tolist(),
            random_seed=settings.RANDOM_SEED,
        )
        print("  no validation textiles were available, using %d grouped "
              "cross validation folds instead" % len(folds))

    best_model = None
    best_candidate = None
    best_score = -np.inf
    comparison = []

    for candidate in settings_to_try():
        name = "%s(C=%s, gamma=%s)" % (
            candidate["kernel"], candidate["C"], candidate["gamma"])
        try:
            if use_cross_validation:
                scores = []
                for fold_train, fold_test in folds:
                    fold_model = fit_one(
                        candidate,
                        features[train_rows][fold_train],
                        labels[train_rows][fold_train],
                    )
                    measured = results.measure_one_split(
                        fold_model,
                        features[train_rows][fold_test],
                        labels[train_rows][fold_test],
                        textile_ids[train_rows][fold_test],
                    )
                    scores.append(measured.get("balanced_accuracy", 0.0))
                score = float(np.mean(scores)) if scores else 0.0
                model = fit_one(candidate, features[train_rows],
                                labels[train_rows])
            else:
                model = fit_one(candidate, features[train_rows],
                                labels[train_rows])
                measured = results.measure_one_split(
                    model,
                    features[validation_rows],
                    labels[validation_rows],
                    textile_ids[validation_rows],
                )
                score = measured.get("balanced_accuracy", 0.0)
        except Exception as problem:
            # One bad combination must not stop the whole run.
            print("  %-34s failed: %s" % (name, problem))
            comparison.append({**candidate, "validation_balanced_accuracy": None,
                               "error": str(problem)})
            continue

        comparison.append({**candidate, "validation_balanced_accuracy": float(score)})
        print("  %-34s validation balanced accuracy %.3f" % (name, score))

        if score > best_score:
            best_score = score
            best_model = model
            best_candidate = candidate

    if best_model is None:
        raise RuntimeError("every SVM setting failed to fit")

    return best_model, {**best_candidate,
                        "validation_balanced_accuracy": best_score}, comparison


def build_reference_bank(table, split):
    allowed = set(split["train_textiles"])
    library = ReferenceLibrary([])

    for position in range(len(table["textile_ids"])):
        textile_id = str(table["textile_ids"][position])
        if textile_id not in allowed:
            continue
        library.add(
            textile_id=textile_id,
            label=str(table["labels"][position]),
            embedding=table["embeddings"][position],
            scan_id=str(table["scan_ids"][position]),
            verification_level="verified",
        )

    return library


def current_git_commit():
    try:
        finished = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=settings.PROJECT_FOLDER,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return finished.stdout.strip() if finished.returncode == 0 else ""
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(
        description="Train an SVM on the collected textile scans")
    parser.add_argument("--version", default=None,
                        help="what to call this model, for example v0.2.0")
    parser.add_argument("--notes", default="",
                        help="a sentence about what changed since last time")
    parser.add_argument("--output", default=None,
                        help="where to write it (default: saved_ai_files/<version>)")
    parser.add_argument("--include-unverified", action="store_true",
                        help="also train on textiles whose provenance is not "
                             "verified. Only do this for experiments, never "
                             "for a model anyone will rely on.")
    arguments = parser.parse_args()

    print("=" * 70)
    print("TRAINING A TEXTILE CLASSIFIER")
    print("=" * 70)
    print()

    table = table_builder.build_table(only_verified=not arguments.include_unverified)
    summary = table_builder.describe_table(table)

    print("Dataset")
    for key in ("textile_count", "textiles_per_class", "scan_area_count",
                "scan_areas_per_class", "feature_count", "skipped_count"):
        print("  %-22s %s" % (key, summary[key]))
    print()

    classes = set(table["labels"].tolist())
    if len(classes) < 2:
        print("STOPPING: only one class is present (%s). Collect verified "
              "textiles of both kinds before training." % classes,
              file=sys.stderr)
        return 1

    textiles_per_class = summary["textiles_per_class"]
    if min(textiles_per_class.values()) < 2:
        print("STOPPING: a split by textile needs at least two independent "
              "textiles of each class, and there are %s." % textiles_per_class,
              file=sys.stderr)
        return 1

    try:
        split = split_by_textile(
            table["labels"].tolist(),
            table["textile_ids"].tolist(),
            train_fraction=settings.TRAIN_FRACTION,
            validation_fraction=settings.VALIDATION_FRACTION,
            random_seed=settings.RANDOM_SEED,
        )
    except TextileAppearsInTwoSplits as problem:
        print("STOPPING: %s" % problem, file=sys.stderr)
        return 2

    split_summary = describe_split(split)
    print("Split by physical textile, never by photo")
    print("  textiles   %s" % split_summary["textiles"])
    print("  scan areas %s" % split_summary["scan_areas"])
    print("  train      %s" % ", ".join(split_summary["train_textile_ids"]))
    print("  validation %s"
          % (", ".join(split_summary["validation_textile_ids"]) or "(none)"))
    print("  test       %s"
          % (", ".join(split_summary["test_textile_ids"]) or "(none)"))
    print()

    print("Trying a few SVM settings")
    model, chosen, comparison = pick_the_best_settings(table, split)
    print()
    print("Chose %s with C=%s gamma=%s"
          % (chosen["kernel"], chosen["C"], chosen["gamma"]))
    print()

    measurements = {
        "chosen_settings": chosen,
        "all_settings_tried": comparison,
        "dataset": summary,
        "split": split_summary,
    }

    for name, rows in (("TRAINING", split["train_rows"]),
                       ("VALIDATION", split["validation_rows"]),
                       ("TEST", split["test_rows"])):
        measured = results.measure_one_split(
            model,
            table["features"][rows],
            table["labels"][rows],
            table["textile_ids"][rows],
        )
        measurements[name.lower()] = measured
        results.print_results(measured, name)

    threshold_rows = split["validation_rows"]
    chosen_on = "validation textiles"
    if threshold_rows.size == 0:
        threshold_rows = split["test_rows"]
        chosen_on = "test textiles, because there were no validation textiles"
    if threshold_rows.size == 0:
        threshold_rows = split["train_rows"]
        chosen_on = "training textiles, because nothing was held out"

    probabilities = model.predict_proba(table["features"][threshold_rows])
    class_names = [str(name) for name in model.classes_]
    handmade_column = (
        class_names.index("handmade") if "handmade" in class_names else 0
    )

    threshold_choice = pick_thresholds.choose_thresholds(
        table["labels"][threshold_rows].tolist(),
        probabilities[:, handmade_column].tolist(),
        table["textile_ids"][threshold_rows].tolist(),
        chosen_on=chosen_on,
    )
    measurements["decision_thresholds"] = threshold_choice

    print("Decision thresholds, chosen on %s" % threshold_choice["chosen_on"])
    print("  handmade if the score is at least %.2f"
          % threshold_choice["handmade_min"])
    print("  machine  if the score is at most  %.2f"
          % threshold_choice["machine_max"])
    print("  anything in between is inconclusive")
    print("  handmade textiles called machine : %.3f"
          % threshold_choice["false_machine_rate"])
    print("  inconclusive fraction            : %.3f"
          % threshold_choice["inconclusive_fraction"])
    for note in threshold_choice["notes"]:
        print("  NOTE: %s" % note)
    print()

    version = arguments.version or (
        "v" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    )
    output_folder = arguments.output or os.path.join(
        settings.SAVED_AI_FOLDER, version)

    reference_library = build_reference_bank(table, split)

    import sklearn

    model_files.save_model_folder(
        output_folder,
        trained_pipeline=model,
        schema=table["schema"],
        results=measurements,
        information={
            "model_version": version,
            "notes": arguments.notes,
            "train_textile_ids": split_summary["train_textile_ids"],
            "validation_textile_ids": split_summary["validation_textile_ids"],
            "test_textile_ids": split_summary["test_textile_ids"],
            "textile_count": summary["textile_count"],
            "scan_area_count": summary["scan_area_count"],
            "trained_on_verified_only": not arguments.include_unverified,
            "chosen_settings": chosen,
            "reference_bank_size": reference_library.size,
            "decision_thresholds": {
                "handmade_min": threshold_choice["handmade_min"],
                "machine_max": threshold_choice["machine_max"],
                "chosen_on": threshold_choice["chosen_on"],
                "constraints_satisfied":
                    threshold_choice["constraints_satisfied"],
            },
            "random_seed": settings.RANDOM_SEED,
            "sklearn_version": sklearn.__version__,
            "numpy_version": np.__version__,
            "git_commit": current_git_commit(),
        },
        reference_bank=reference_library.to_arrays(),
    )

    print("=" * 70)
    print("MODEL %s WRITTEN" % version)
    print("  folder : %s" % output_folder)
    print()
    print("It is NOT switched on yet. To use it, copy that folder to:")
    print("  %s" % settings.SAVED_MODEL_FOLDER)
    print("and restart the laptop server.")
    print()
    print("Remember: the numbers above are measured over %d independent"
          % summary["textile_count"])
    print("physical textiles. The scan area count is bigger, and it is not a")
    print("sample size.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
