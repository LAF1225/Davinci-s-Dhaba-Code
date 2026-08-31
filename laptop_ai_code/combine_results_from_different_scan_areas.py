import numpy as np

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code.run_saved_svm_textile_prediction import (
    DECISION_HANDMADE,
    DECISION_INCONCLUSIVE,
    DECISION_MACHINE,
    describe_result,
)

# The three commands the main ESP32 has to understand.
COMMAND_CONTINUE = "continue"
COMMAND_RESCAN = "rescan"
COMMAND_COMPLETE = "complete"


def measure_regional_disagreement(scan_areas):
    scored = [
        area for area in scan_areas
        if area["usable"] and area.get("handmade_probability") is not None
    ]
    if len(scored) < 4:
        return None

    have_row_and_column = all(
        area.get("row_index") is not None and area.get("column_index") is not None
        for area in scored
    )
    if not have_row_and_column:
        return None

    columns = np.array([float(area["column_index"]) for area in scored])
    rows = np.array([float(area["row_index"]) for area in scored])
    scores = np.array([float(area["handmade_probability"]) for area in scored])

    middle_column = float(np.median(columns))
    middle_row = float(np.median(rows))

    quadrant_averages = []
    for column_side in (columns <= middle_column, columns > middle_column):
        for row_side in (rows <= middle_row, rows > middle_row):
            quadrant = column_side & row_side
            if quadrant.sum() >= 2:
                quadrant_averages.append(float(scores[quadrant].mean()))

    if len(quadrant_averages) < 2:
        return None
    return float(np.std(quadrant_averages))


def combine_scan_areas(scan_areas, scan_areas_planned=None):
    result = {
        "decision": DECISION_INCONCLUSIVE,
        "score": None,
        "enough_evidence": False,
        "valid_scan_area_count": 0,
        "rejected_scan_area_count": 0,
        "median_handmade": None,
        "mean_handmade": None,
        "score_spread": None,
        "handmade_fraction": 0.0,
        "machine_fraction": 0.0,
        "inconclusive_fraction": 0.0,
        "mean_handmade_similarity": None,
        "mean_machine_similarity": None,
        "out_of_domain_fraction": 0.0,
        "regional_disagreement": None,
        "total_rescans": 0,
        "reasons": [],
    }

    usable = [area for area in scan_areas if area["usable"]]
    result["valid_scan_area_count"] = len(usable)
    result["rejected_scan_area_count"] = len(scan_areas) - len(usable)
    result["total_rescans"] = sum(
        int(area.get("rescan_count", 0)) for area in scan_areas
    )

    if not usable:
        result["reasons"].append("no_usable_scan_areas")
        result["wording"] = describe_result(result["decision"])
        result["robot_command"] = _choose_command(result, scan_areas_planned)
        return result

    total = float(len(usable))
    result["handmade_fraction"] = sum(
        1 for area in usable if area["decision"] == DECISION_HANDMADE) / total
    result["machine_fraction"] = sum(
        1 for area in usable if area["decision"] == DECISION_MACHINE) / total
    result["inconclusive_fraction"] = sum(
        1 for area in usable if area["decision"] == DECISION_INCONCLUSIVE) / total
    result["out_of_domain_fraction"] = sum(
        1 for area in usable if area.get("out_of_domain")) / total

    scores = [
        float(area["handmade_probability"]) for area in usable
        if area.get("handmade_probability") is not None
    ]
    if scores:
        result["median_handmade"] = float(np.median(scores))
        result["mean_handmade"] = float(np.mean(scores))
        result["score_spread"] = float(np.std(scores))
        # The median, not the mean: one strange scan area should not drag the
        # whole answer across a threshold.
        result["score"] = result["median_handmade"]

    handmade_similarities = [
        area["handmade_similarity"] for area in usable
        if area.get("handmade_similarity") is not None
    ]
    machine_similarities = [
        area["machine_similarity"] for area in usable
        if area.get("machine_similarity") is not None
    ]
    if handmade_similarities:
        result["mean_handmade_similarity"] = float(np.mean(handmade_similarities))
    if machine_similarities:
        result["mean_machine_similarity"] = float(np.mean(machine_similarities))

    result["regional_disagreement"] = measure_regional_disagreement(usable)

    # ---- is there enough evidence yet ------------------------------------
    if result["valid_scan_area_count"] < settings.MINIMUM_VALID_SCAN_AREAS:
        result["reasons"].append("not_enough_valid_scan_areas")
        result["decision"] = DECISION_INCONCLUSIVE
        result["wording"] = describe_result(result["decision"])
        result["robot_command"] = _choose_command(result, scan_areas_planned)
        return result

    result["enough_evidence"] = True

    if not scores:
        result["reasons"].append("no_probabilities_available")
        result["decision"] = DECISION_INCONCLUSIVE
        result["wording"] = describe_result(result["decision"])
        result["robot_command"] = _choose_command(result, scan_areas_planned)
        return result

    # ---- reasons the evidence cannot support any confident answer ---------
    blocked = False
    if result["inconclusive_fraction"] > settings.MAXIMUM_INCONCLUSIVE_FRACTION:
        result["reasons"].append("too_many_inconclusive_scan_areas")
        blocked = True
    if result["score_spread"] > settings.MAXIMUM_SCORE_SPREAD:
        result["reasons"].append("scan_areas_disagree_too_much")
        blocked = True
    if result["out_of_domain_fraction"] > 0.5:
        result["reasons"].append("mostly_out_of_domain")
        blocked = True

    if blocked:
        result["decision"] = DECISION_INCONCLUSIVE
        result["wording"] = describe_result(result["decision"])
        result["robot_command"] = _choose_command(result, scan_areas_planned)
        return result

    median = float(result["median_handmade"])

    if (median >= settings.HANDMADE_MEDIAN_MINIMUM
            and result["handmade_fraction"] >= settings.MINIMUM_SUPPORTING_FRACTION):
        result["decision"] = DECISION_HANDMADE
        result["reasons"].append("median_and_support_favour_handmade")
    elif (median <= settings.MACHINE_MEDIAN_MAXIMUM
            and result["machine_fraction"] >= settings.MINIMUM_SUPPORTING_FRACTION):
        result["decision"] = DECISION_MACHINE
        result["reasons"].append("median_and_support_favour_machine")
    else:
        result["decision"] = DECISION_INCONCLUSIVE
        result["reasons"].append("scan_areas_do_not_agree_enough")

    # One region looking different from the rest overrides a confident call.
    if (result["regional_disagreement"] is not None
            and result["regional_disagreement"] > settings.MAXIMUM_SCORE_SPREAD):
        result["reasons"].append("one_region_looks_different")
        result["decision"] = DECISION_INCONCLUSIVE

    result["wording"] = describe_result(result["decision"])
    result["robot_command"] = _choose_command(result, scan_areas_planned)
    return result


def _choose_command(result, scan_areas_planned):
    if scan_areas_planned is None:
        scan_areas_planned = settings.SCAN_AREAS_PER_TEXTILE

    scanned = result["valid_scan_area_count"] + result["rejected_scan_area_count"]

    # Every planned area has been visited.
    if scanned >= scan_areas_planned:
        if result["valid_scan_area_count"] >= settings.MINIMUM_VALID_SCAN_AREAS:
            return {"command": COMMAND_COMPLETE, "reason": "all_scan_areas_done"}
        # We got to the end but too much of it was unusable. Rather than
        # announcing an answer from too little evidence, ask for more.
        return {
            "command": COMMAND_RESCAN,
            "reason": "not_enough_usable_scan_areas",
        }

    return {"command": COMMAND_CONTINUE, "reason": "more_scan_areas_planned"}
