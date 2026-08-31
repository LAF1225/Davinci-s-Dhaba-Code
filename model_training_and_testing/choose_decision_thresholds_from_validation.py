import numpy as np

MAXIMUM_FALSE_MACHINE_RATE = 0.05
MAXIMUM_INCONCLUSIVE_FRACTION = 0.40
MINIMUM_GAP_BETWEEN_THRESHOLDS = 0.10


def one_score_per_textile(labels, handmade_probabilities, textile_ids):
    grouped = {}
    for label, probability, textile_id in zip(
            labels, handmade_probabilities, textile_ids):
        entry = grouped.setdefault(
            str(textile_id), {"label": str(label), "scores": []}
        )
        entry["scores"].append(float(probability))

    truths = []
    medians = []
    for _textile_id, entry in sorted(grouped.items()):
        truths.append(entry["label"])
        medians.append(float(np.median(entry["scores"])))
    return truths, medians


def apply_thresholds(score, handmade_min, machine_max):
    if score >= handmade_min:
        return "handmade"
    if score <= machine_max:
        return "machine"
    return "inconclusive"


def measure_one_pair(truths, scores, handmade_min, machine_max):
    decisions = [
        apply_thresholds(score, handmade_min, machine_max) for score in scores
    ]

    handmade_total = sum(1 for label in truths if label == "handmade")
    machine_total = sum(1 for label in truths if label == "machine")

    false_machine = sum(
        1 for label, decision in zip(truths, decisions)
        if label == "handmade" and decision == "machine"
    )
    false_handmade = sum(
        1 for label, decision in zip(truths, decisions)
        if label == "machine" and decision == "handmade"
    )
    right_handmade = sum(
        1 for label, decision in zip(truths, decisions)
        if label == "handmade" and decision == "handmade"
    )
    right_machine = sum(
        1 for label, decision in zip(truths, decisions)
        if label == "machine" and decision == "machine"
    )
    inconclusive = sum(1 for decision in decisions if decision == "inconclusive")

    decided_handmade = right_handmade + false_machine
    decided_machine = right_machine + false_handmade

    handmade_recall = (
        right_handmade / decided_handmade if decided_handmade else 0.0)
    machine_recall = (
        right_machine / decided_machine if decided_machine else 0.0)
    balanced_accuracy = (handmade_recall + machine_recall) / 2.0

    margins = [
        (score - handmade_min) if decision == "handmade"
        else (machine_max - score)
        for score, decision in zip(scores, decisions)
        if decision != "inconclusive"
    ]
    margin = float(min(margins)) if margins else 0.0

    return {
        "margin": margin,
        "false_machine_rate": (
            false_machine / handmade_total if handmade_total else 0.0),
        "false_handmade_rate": (
            false_handmade / machine_total if machine_total else 0.0),
        "inconclusive_fraction": (
            inconclusive / len(truths) if truths else 1.0),
        "balanced_accuracy_on_decided": balanced_accuracy,
        "decided_fraction": (
            1.0 - (inconclusive / len(truths) if truths else 1.0)),
        "predicted_handmade": right_handmade + false_handmade,
        "predicted_machine": right_machine + false_machine,
    }


def choose_thresholds(labels, handmade_probabilities, textile_ids,
                      chosen_on="validation",
                      max_false_machine_rate=MAXIMUM_FALSE_MACHINE_RATE,
                      max_inconclusive_fraction=MAXIMUM_INCONCLUSIVE_FRACTION,
                      minimum_gap=MINIMUM_GAP_BETWEEN_THRESHOLDS,
                      grid_step=0.01):
    notes = []
    truths, scores = one_score_per_textile(
        labels, handmade_probabilities, textile_ids
    )

    if len(truths) < 2 or len(set(truths)) < 2:
        notes.append(
            "only %d textile(s) covering %d class(es) were available, so the "
            "thresholds could not be chosen from data"
            % (len(truths), len(set(truths)))
        )
        return {
            "handmade_min": 0.65,
            "machine_max": 0.35,
            "chosen_on": chosen_on + " (not enough data, defaults used)",
            "false_machine_rate": 0.0,
            "inconclusive_fraction": 1.0,
            "balanced_accuracy_on_decided": 0.0,
            "textile_count": len(truths),
            "constraints_satisfied": False,
            "notes": notes,
        }

    grid = np.round(np.arange(0.0, 1.0 + grid_step, grid_step), 4)

    best = None
    best_key = None
    best_nearly = None
    best_nearly_score = None

    for machine_max in grid:
        for handmade_min in grid:
            if handmade_min < machine_max + minimum_gap:
                continue

            measurements = measure_one_pair(
                truths, scores, float(handmade_min), float(machine_max)
            )
            accuracy = measurements["balanced_accuracy_on_decided"]
            separates = (
                measurements["predicted_handmade"] > 0
                and measurements["predicted_machine"] > 0
                and accuracy > 0.5
            )
            allowed = (
                separates
                and measurements["false_machine_rate"] <= max_false_machine_rate
                and measurements["inconclusive_fraction"]
                <= max_inconclusive_fraction
            )

            if allowed:
                key = (accuracy, measurements["margin"],
                       measurements["decided_fraction"])
                if best_key is None or key > best_key:
                    best_key = key
                    best = (float(handmade_min), float(machine_max), measurements)
            else:
                penalty = (
                    max(0.0, measurements["false_machine_rate"]
                        - max_false_machine_rate) * 2.0
                    + max(0.0, measurements["inconclusive_fraction"]
                          - max_inconclusive_fraction)
                )
                adjusted = accuracy - penalty
                if best_nearly_score is None or adjusted > best_nearly_score:
                    best_nearly_score = adjusted
                    best_nearly = (
                        float(handmade_min), float(machine_max), measurements)

    if best is not None:
        handmade_min, machine_max, measurements = best
        constraints_satisfied = True
    else:
        handmade_min, machine_max, measurements = best_nearly
        constraints_satisfied = False
        notes.append(
            "no pair of thresholds both separated the two classes better than "
            "chance and stayed inside the limits (handmade textiles called "
            "machine at most %.0f%%, inconclusive at most %.0f%%) on %d "
            "textiles. The closest pair is reported. Treat this model as not "
            "ready and collect more verified textiles."
            % (max_false_machine_rate * 100, max_inconclusive_fraction * 100,
               len(truths))
        )

    if abs(handmade_min - 0.5) < 1e-9 and abs(machine_max - 0.5) < 1e-9:
        notes.append(
            "the search landed on 0.5 and 0.5, which leaves no inconclusive "
            "band at all. That is almost always a sign of too little "
            "validation data rather than a very good classifier."
        )

    return {
        "handmade_min": float(handmade_min),
        "machine_max": float(machine_max),
        "chosen_on": chosen_on,
        "false_machine_rate": float(measurements["false_machine_rate"]),
        "inconclusive_fraction": float(measurements["inconclusive_fraction"]),
        "balanced_accuracy_on_decided": float(
            measurements["balanced_accuracy_on_decided"]),
        "textile_count": len(truths),
        "constraints_satisfied": constraints_satisfied,
        "notes": notes,
    }
