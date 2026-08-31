import numpy as np

CLASS_ORDER = ("handmade", "machine")


def count_the_two_kinds_of_mistake(true_labels, predicted_labels):
    handmade_total = sum(1 for label in true_labels if label == "handmade")
    machine_total = sum(1 for label in true_labels if label == "machine")

    called_machine_but_handmade = sum(
        1 for true, predicted in zip(true_labels, predicted_labels)
        if true == "handmade" and predicted == "machine"
    )
    called_handmade_but_machine = sum(
        1 for true, predicted in zip(true_labels, predicted_labels)
        if true == "machine" and predicted == "handmade"
    )

    return {
        "false_machine_count": called_machine_but_handmade,
        "false_machine_rate": (
            called_machine_but_handmade / handmade_total if handmade_total else 0.0
        ),
        "false_handmade_count": called_handmade_but_machine,
        "false_handmade_rate": (
            called_handmade_but_machine / machine_total if machine_total else 0.0
        ),
        "verified_handmade_count": handmade_total,
        "verified_machine_count": machine_total,
    }


def scan_area_results(true_labels, predicted_labels):
    from sklearn.metrics import (
        balanced_accuracy_score,
        confusion_matrix,
        f1_score,
        precision_recall_fscore_support,
    )

    true_labels = list(true_labels)
    predicted_labels = list(predicted_labels)
    if not true_labels:
        return {"scan_area_count": 0}

    precision, recall, f1, support = precision_recall_fscore_support(
        true_labels, predicted_labels, labels=list(CLASS_ORDER), zero_division=0
    )
    matrix = confusion_matrix(
        true_labels, predicted_labels, labels=list(CLASS_ORDER)
    )

    results = {
        "scan_area_count": len(true_labels),
        "balanced_accuracy": float(
            balanced_accuracy_score(true_labels, predicted_labels)),
        "macro_f1": float(
            f1_score(true_labels, predicted_labels, average="macro",
                     zero_division=0)),
        "confusion_matrix": matrix.tolist(),
        "confusion_matrix_labels": list(CLASS_ORDER),
    }
    for position, label in enumerate(CLASS_ORDER):
        results[label + "_precision"] = float(precision[position])
        results[label + "_recall"] = float(recall[position])
        results[label + "_f1"] = float(f1[position])
        results[label + "_scan_areas"] = int(support[position])

    results["mistakes"] = count_the_two_kinds_of_mistake(
        true_labels, predicted_labels
    )
    return results


def textile_results(true_labels, handmade_probabilities, textile_ids,
                    threshold=0.5):
    """Combine the scan areas of each textile into one answer per textile."""
    from sklearn.metrics import balanced_accuracy_score, confusion_matrix, f1_score

    per_textile = {}
    for label, probability, textile_id in zip(
            true_labels, handmade_probabilities, textile_ids):
        entry = per_textile.setdefault(
            str(textile_id), {"label": str(label), "scores": []}
        )
        entry["scores"].append(float(probability))

    if not per_textile:
        return {"textile_count": 0}

    truths = []
    predictions = []
    details = []

    for textile_id, entry in sorted(per_textile.items()):
        median = float(np.median(entry["scores"]))
        truths.append(entry["label"])
        predictions.append("handmade" if median >= threshold else "machine")
        details.append({
            "textile_id": textile_id,
            "median_handmade": median,
            "true_label": entry["label"],
            "scan_area_count": len(entry["scores"]),
        })

    matrix = confusion_matrix(truths, predictions, labels=list(CLASS_ORDER))
    return {
        "textile_count": len(per_textile),
        "balanced_accuracy": float(balanced_accuracy_score(truths, predictions)),
        "macro_f1": float(
            f1_score(truths, predictions, average="macro", zero_division=0)),
        "confusion_matrix": matrix.tolist(),
        "confusion_matrix_labels": list(CLASS_ORDER),
        "mistakes": count_the_two_kinds_of_mistake(truths, predictions),
        "per_textile": details,
    }


def measure_one_split(pipeline, features, true_labels, textile_ids):
    """Everything worth knowing about how the model did on one split."""
    if features.shape[0] == 0:
        return {"scan_area_count": 0, "textile_count": 0,
                "note": "this split is empty"}

    predicted_labels = [str(item) for item in pipeline.predict(features)]
    probabilities = pipeline.predict_proba(features)

    class_names = [str(name) for name in pipeline.classes_]
    handmade_column = (
        class_names.index("handmade") if "handmade" in class_names else 0
    )
    handmade_probabilities = probabilities[:, handmade_column]

    results = scan_area_results(true_labels, predicted_labels)
    results["textile_count"] = len({str(item) for item in textile_ids})
    results["textile_level"] = textile_results(
        true_labels, handmade_probabilities, textile_ids
    )
    results["mean_handmade_probability"] = float(np.mean(handmade_probabilities))
    return results


def print_results(results, title):
    """Print one split's results."""
    print("--- %s ---" % title)

    if not results.get("scan_area_count"):
        print("  (this split is empty)")
        return

    print("  %d scan areas across %d independent physical textiles"
          % (results["scan_area_count"], results.get("textile_count", 0)))
    print("  balanced accuracy per scan area : %.3f"
          % results["balanced_accuracy"])
    print("  macro F1 per scan area          : %.3f" % results["macro_f1"])

    for label in CLASS_ORDER:
        precision = results.get(label + "_precision")
        if precision is not None:
            print("  %-9s precision %.3f  recall %.3f"
                  % (label, precision, results[label + "_recall"]))

    matrix = results.get("confusion_matrix")
    if matrix:
        print("  confusion, rows are the true label %s: %s"
              % (list(CLASS_ORDER), matrix))

    textile = results.get("textile_level") or {}
    if textile.get("textile_count"):
        print("  PER TEXTILE balanced accuracy   : %.3f over %d textiles"
              % (textile["balanced_accuracy"], textile["textile_count"]))

        mistakes = textile["mistakes"]
        print("  handmade textiles called machine: %d of %d  (%.3f)"
              % (mistakes["false_machine_count"],
                 mistakes["verified_handmade_count"],
                 mistakes["false_machine_rate"]))
        print("  machine textiles called handmade: %d of %d  (%.3f)"
              % (mistakes["false_handmade_count"],
                 mistakes["verified_machine_count"],
                 mistakes["false_handmade_rate"]))
    print()
