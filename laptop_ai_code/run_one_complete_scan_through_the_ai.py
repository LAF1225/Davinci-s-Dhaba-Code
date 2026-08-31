import threading

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import check_photo_quality_before_using_ai as quality_check
from laptop_ai_code import clean_and_prepare_colour_sensor_readings as colour
from laptop_ai_code import combine_photo_and_sensor_features as fusion
from laptop_ai_code import get_dinov2_features_from_textile_photo as vision
from laptop_ai_code import load_saved_ai_files as model_files
from laptop_ai_code import measure_simple_texture_numbers_from_photo as texture
from laptop_ai_code import run_saved_svm_textile_prediction as svm
from laptop_ai_code.compare_scan_with_verified_reference_textiles import (
    ReferenceLibrary,
)

_loaded_model = None
_model_problem = None
_reference_library = None
_load_lock = threading.Lock()


def load_the_model(force_reload=False):
    global _loaded_model, _model_problem, _reference_library

    with _load_lock:
        if _loaded_model is not None and not force_reload:
            return _loaded_model
        if _model_problem is not None and not force_reload:
            return None

        _loaded_model = None
        _model_problem = None
        _reference_library = None

        try:
            expected = fusion.describe_expected_schema(
                embedding_size=vision.embedding_size()
                if vision.dinov2_is_available() else None
            )
            _loaded_model = model_files.load_model_folder(current_schema=expected)
            _reference_library = ReferenceLibrary.from_arrays(
                _loaded_model["reference_bank"]
            )
        except (model_files.ModelFilesMissing,
                model_files.ModelDoesNotMatchThisCode) as problem:
            _model_problem = str(problem)
        except Exception as problem:
            _model_problem = "%s: %s" % (type(problem).__name__, problem)

        return _loaded_model


def why_the_model_is_not_loaded():
    return _model_problem or ""


def get_reference_library():
    load_the_model()
    if _reference_library is not None:
        return _reference_library
    return ReferenceLibrary([])


def ai_status():
    load_the_model()
    references = get_reference_library()

    if not vision.dinov2_is_available():
        what_works = "nothing: DINOv2 will not load"
    elif _loaded_model is not None:
        what_works = "full pipeline with the trained classifier"
    elif references.size > 0:
        what_works = "reference comparison only, no trained classifier"
    else:
        what_works = "raw collection only, no classifier and no references"

    return {
        "dinov2_available": vision.dinov2_is_available(),
        "dinov2_detail": vision.why_dinov2_is_not_available() or "loaded and frozen",
        "model_loaded": _loaded_model is not None,
        "model_version": _loaded_model["version"] if _loaded_model else None,
        "model_problem": _model_problem or "",
        "reference_count": references.size,
        "what_works": what_works,
    }


def run_one_scan(joined_scan, rescans_already_done=0, scan_areas_done=0,
                 scan_areas_planned=None):
    if scan_areas_planned is None:
        scan_areas_planned = settings.SCAN_AREAS_PER_TEXTILE

    reasons = []
    photo_quality, photo = quality_check.check_photo(
        joined_scan.get("photo_bytes", b"")
    )
    colour_result = colour.calibrate_reading(
        joined_scan.get("colour_sensor_values", []),
        dark=joined_scan.get("colour_dark_reference"),
        white=joined_scan.get("colour_white_reference"),
        # Without a dark and white reference the reflectance numbers are not
        # comparable between runs, so an uncalibrated reading is not usable
        # for a prediction. It is still stored.
        require_calibration=True,
    )

    if not joined_scan.get("region_ids_agree", True):
        reasons.append("photo_and_sensor_region_ids_disagree")

    quality_reasons = (
        list(photo_quality["all_reasons"]) + list(colour_result["reasons"])
    )
    everything_ok = photo_quality["passed"] and colour_result["ok"]

    quality_report = {
        "photo_ok": photo_quality["passed"],
        "colour_ok": colour_result["ok"],
        "reasons": quality_reasons,
        "measurements": photo_quality["measurements"],
    }
    model = load_the_model()
    model_thresholds = None
    if model is not None:
        model_thresholds = model_files.decision_thresholds_from_model(
            model["information"]
        )
    thresholds = svm.choose_thresholds(model_thresholds)
    if not everything_ok or photo is None:
        prediction = svm.decide_one_scan_area(
            quality_ok=False,
            quality_reasons=quality_reasons,
            probabilities=None,
            reference_match=None,
            thresholds=thresholds,
            model_is_usable=False,
            rescans_already_done=rescans_already_done,
            scan_areas_done=scan_areas_done,
            scan_areas_planned=scan_areas_planned,
        )
        prediction["reasons"].extend(reasons)
        prediction["reference"] = None
        prediction["wording"] = svm.describe_result(prediction["decision"])
        return {
            "quality": quality_report,
            "calibrated_colour": colour_result["calibrated"],
            "prediction": prediction,
            "model_version": None,
        }
    embedding = None
    visual_summary = None
    if vision.dinov2_is_available():
        visual = vision.get_features_from_photo(photo)
        reasons.extend(visual["reasons"])
        if visual["ok"]:
            embedding = visual["embedding"]
            visual_summary = visual["summary"]
        else:
            reasons.append("dinov2_features_failed")
    else:
        reasons.append("dinov2_unavailable")
    reference_match = None
    if embedding is not None:
        reference_match = get_reference_library().compare(embedding)
    probabilities = None
    model_is_usable = False

    if model is None:
        reasons.append("no_trained_model")
        if _model_problem:
            reasons.append("model_problem")
    elif embedding is None:
        reasons.append("no_photo_features")
    else:
        texture_values, texture_names = texture.get_texture_features(photo)
        colour_values = colour.get_colour_features(colour_result["calibrated"])

        vector, schema = fusion.combine(
            embedding=embedding,
            visual_summary=visual_summary,
            texture_values=texture_values,
            texture_names=texture_names,
            colour_values=colour_values,
        )

        matches, detail = fusion.schemas_match(schema, model["schema"])
        if not matches:
            reasons.append("model_does_not_match_this_code")
            reasons.append(detail)
        else:
            try:
                probabilities = svm.predict_probabilities(model["pipeline"], vector)
                model_is_usable = True
            except Exception as problem:
                reasons.append("prediction_failed")
                reasons.append("%s: %s" % (type(problem).__name__, problem))

    if not model_is_usable and reference_match is not None \
            and not reference_match["out_of_domain"]:
        # Reference comparison still says something useful on its own, but it
        # must never be reported as if the full classifier had run.
        reasons.append("reference_comparison_only")

    prediction = svm.decide_one_scan_area(
        quality_ok=True,
        quality_reasons=quality_reasons,
        probabilities=probabilities,
        reference_match=reference_match,
        thresholds=thresholds,
        model_is_usable=model_is_usable,
        rescans_already_done=rescans_already_done,
        scan_areas_done=scan_areas_done,
        scan_areas_planned=scan_areas_planned,
    )
    prediction["reasons"].extend(reasons)
    prediction["reference"] = reference_match
    prediction["wording"] = svm.describe_result(prediction["decision"])
    prediction["threshold_source"] = thresholds["source"]

    return {
        "quality": quality_report,
        "calibrated_colour": colour_result["calibrated"],
        "prediction": prediction,
        "model_version": model["version"] if model else None,
    }
