from laptop_ai_code import ai_settings_and_thresholds as settings

CLASS_HANDMADE = "handmade"
CLASS_MACHINE = "machine"
DECISION_HANDMADE = "likely_handmade"
DECISION_MACHINE = "likely_machine"
DECISION_INCONCLUSIVE = "inconclusive"
DECISION_UNUSABLE = "unusable"

RESULT_WORDING = {
    DECISION_HANDMADE: "Likely consistent with handmade production",
    DECISION_MACHINE: "Likely consistent with machine production",
    DECISION_INCONCLUSIVE: "Inconclusive",
    DECISION_UNUSABLE: "Unusable scan",
}

DISCLAIMER = (
    "Preliminary screening result. Expert verification is recommended for "
    "formal authentication."
)


def describe_result(decision):
    return RESULT_WORDING.get(decision, "Inconclusive")


def describe_confidence(score):
    if score is None:
        return "unknown"
    distance_from_the_middle = abs(score - 0.5)
    if distance_from_the_middle < 0.10:
        return "very low separation"
    if distance_from_the_middle < 0.20:
        return "low separation"
    if distance_from_the_middle < 0.35:
        return "moderate separation"
    return "high separation"


def predict_probabilities(pipeline, feature_vector):
    import numpy as np

    row = np.asarray(feature_vector, dtype=np.float64).reshape(1, -1)
    probabilities = pipeline.predict_proba(row)[0]

    class_names = [str(name) for name in getattr(pipeline, "classes_",
                                                 (CLASS_HANDMADE, CLASS_MACHINE))]
    return {
        name: float(probability)
        for name, probability in zip(class_names, probabilities)
    }


def _make_robot_command(command, reason, extra_scan_areas=None, settle_ms=None):
    payload = {"command": command, "reason": reason}
    if extra_scan_areas is not None:
        payload["extra_scan_areas"] = extra_scan_areas
    if settle_ms is not None:
        payload["settle_ms"] = settle_ms
    return payload


def _most_useful_reason(reasons, fallback):
    priority = [
        "colour_calibration_degenerate",
        "colour_channel_count_mismatch",
        "image_decode_failed",
        "image_blur",
        "underexposed",
        "overexposed",
        "highlight_clipping",
        "shadow_clipping",
        "low_contrast",
        "image_too_small",
        "colour_missing",
        "colour_constant_vector",
        "colour_non_finite",
        "colour_out_of_range",
        "colour_uncalibrated",
    ]
    for candidate in priority:
        if candidate in reasons:
            return candidate
    return reasons[0] if reasons else fallback


def choose_thresholds(model_thresholds=None):
    low = settings.LOW_CONFIDENCE_MINIMUM
    high = settings.LOW_CONFIDENCE_MAXIMUM
    source = "settings file default"

    if model_thresholds:
        handmade_min = model_thresholds.get("handmade_min")
        machine_max = model_thresholds.get("machine_max")
        if (handmade_min is not None and machine_max is not None
                and 0.0 <= machine_max < handmade_min <= 1.0):
            low = machine_max
            high = handmade_min
            source = "chosen on validation textiles by the saved model"
        else:
            source = (
                "the saved model carried thresholds that do not make sense, so "
                "the settings file values are being used"
            )

    return {"low": low, "high": high, "source": source}


def decide_one_scan_area(quality_ok, quality_reasons, probabilities,
                         reference_match, thresholds, model_is_usable,
                         rescans_already_done=0, scan_areas_done=0,
                         scan_areas_planned=20):
    reasons = []

    # 1. Quality gate. A bad photo or a bad sensor reading means rescan.
    if not quality_ok:
        reasons.extend(quality_reasons)

        if (settings.FAILED_QUALITY_MEANS_RESCAN
                and rescans_already_done < settings.MAXIMUM_RESCANS_PER_AREA):
            # Asking for a longer settle only helps a blurry photo, so only ask
            # for it when the photo is what failed.
            photo_failed = any(
                reason.startswith("image") for reason in quality_reasons
            )
            command = _make_robot_command(
                "rescan",
                _most_useful_reason(quality_reasons, "quality_check_failed"),
                settle_ms=800 if photo_failed else None,
            )
            reasons.append("rescan_requested")
            return {
                "decision": DECISION_UNUSABLE,
                "handmade_probability": None,
                "machine_probability": None,
                "confidence": None,
                "robot_command": command,
                "reasons": reasons,
            }

        # A permanently damaged patch must not stall the whole run.
        reasons.append("rescan_limit_reached")
        return {
            "decision": DECISION_UNUSABLE,
            "handmade_probability": None,
            "machine_probability": None,
            "confidence": None,
            "robot_command": _make_robot_command("continue", "rescan_limit_reached"),
            "reasons": reasons,
        }

    # 2. No usable classifier. Keep collecting, do not invent a prediction.
    if not model_is_usable or not probabilities:
        reasons.append("no_usable_classifier")
        if reference_match is not None and not reference_match["out_of_domain"]:
            reasons.append("reference_similarity_only")
        return {
            "decision": DECISION_INCONCLUSIVE,
            "handmade_probability": None,
            "machine_probability": None,
            "confidence": None,
            "robot_command": _make_robot_command("continue", "no_usable_classifier"),
            "reasons": reasons,
        }

    handmade = float(probabilities.get(CLASS_HANDMADE, 0.0))
    machine = float(probabilities.get(CLASS_MACHINE, 1.0 - handmade))
    confidence = max(handmade, machine)

    if reference_match is not None and reference_match["out_of_domain"]:
        reasons.append("out_of_domain")
        reasons.extend(reference_match["reasons"])
        return {
            "decision": DECISION_INCONCLUSIVE,
            "handmade_probability": handmade,
            "machine_probability": machine,
            "confidence": confidence,
            "robot_command": _make_robot_command(
                "inspect_neighbours",
                "out_of_domain",
                extra_scan_areas=settings.EXTRA_SCAN_AREAS_WHEN_DOUBTFUL,
            ),
            "reasons": reasons,
        }

    best_similarity = None
    if reference_match is not None:
        candidates = [
            value
            for value in (reference_match["handmade_similarity"],
                          reference_match["machine_similarity"])
            if value is not None
        ]
        best_similarity = max(candidates) if candidates else None

    if (best_similarity is not None
            and best_similarity < settings.MINIMUM_REFERENCE_SIMILARITY):
        reasons.append("low_reference_similarity")
        return {
            "decision": DECISION_INCONCLUSIVE,
            "handmade_probability": handmade,
            "machine_probability": machine,
            "confidence": confidence,
            "robot_command": _make_robot_command(
                "inspect_neighbours",
                "low_reference_similarity",
                extra_scan_areas=settings.EXTRA_SCAN_AREAS_WHEN_DOUBTFUL,
            ),
            "reasons": reasons,
        }

    if thresholds["low"] <= handmade <= thresholds["high"]:
        reasons.append("low_confidence")
        nearly_finished = (
            scan_areas_planned > 0
            and scan_areas_done >= int(0.8 * scan_areas_planned)
        )
        if nearly_finished:
            reasons.append("run_nearly_complete")
            command = _make_robot_command("continue", "low_confidence_late_in_run")
        else:
            command = _make_robot_command(
                "inspect_neighbours",
                "low_confidence",
                extra_scan_areas=settings.EXTRA_SCAN_AREAS_WHEN_DOUBTFUL,
            )
        return {
            "decision": DECISION_INCONCLUSIVE,
            "handmade_probability": handmade,
            "machine_probability": machine,
            "confidence": confidence,
            "robot_command": command,
            "reasons": reasons,
        }

    decision = (
        DECISION_HANDMADE if handmade > thresholds["high"] else DECISION_MACHINE
    )
    reasons.append("sufficient_confidence")
    return {
        "decision": decision,
        "handmade_probability": handmade,
        "machine_probability": machine,
        "confidence": confidence,
        "robot_command": _make_robot_command("continue", "sufficient_confidence"),
        "reasons": reasons,
    }
