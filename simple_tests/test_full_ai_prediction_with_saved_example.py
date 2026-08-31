import cv2
import numpy as np
import pytest

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import combine_photo_and_sensor_features as fusion
from laptop_ai_code import load_saved_ai_files as model_files
from laptop_ai_code import run_saved_svm_textile_prediction as svm
from laptop_ai_code.compare_scan_with_verified_reference_textiles import (
    ReferenceLibrary,
)


def make_a_photo(width=800, height=600, seed=7):
    random_numbers = np.random.default_rng(seed)
    x_positions, y_positions = np.meshgrid(np.arange(width), np.arange(height))

    weave = (((x_positions // 4) % 2) ^ ((y_positions // 4) % 2)).astype(np.float64)
    gray = 70.0 + 110.0 * weave
    gray += random_numbers.normal(0.0, 8.0, gray.shape)

    gray = np.clip(gray, 0, 255).astype(np.uint8)
    colour = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    return cv2.imencode(".jpg", colour, [cv2.IMWRITE_JPEG_QUALITY, 95])[1].tobytes()

def test_a_missing_model_folder_gives_a_readable_error(tmp_path):
    missing = str(tmp_path / "there_is_nothing_here")

    with pytest.raises(model_files.ModelFilesMissing) as raised:
        model_files.load_model_folder(missing)

    message = str(raised.value)
    assert missing in message, "the error should say which folder it looked in"
    assert "train" in message, "the error should say how to get a model"


def test_a_folder_missing_its_classifier_gives_a_readable_error(tmp_path):
    folder = tmp_path / "half_a_model"
    folder.mkdir()
    (folder / settings.FEATURE_SCHEMA_FILE_NAME).write_text("{}")

    with pytest.raises(model_files.ModelFilesMissing) as raised:
        model_files.load_model_folder(str(folder))

    assert settings.CLASSIFIER_FILE_NAME in str(raised.value)


def test_a_folder_missing_its_schema_gives_a_readable_error(tmp_path):
    folder = tmp_path / "half_a_model"
    folder.mkdir()
    (folder / settings.CLASSIFIER_FILE_NAME).write_bytes(b"not really a model")

    with pytest.raises(model_files.ModelFilesMissing) as raised:
        model_files.load_model_folder(str(folder))

    assert settings.FEATURE_SCHEMA_FILE_NAME in str(raised.value)

def test_the_feature_groups_are_in_the_locked_order():
    schema = fusion.describe_expected_schema(embedding_size=384)
    assert schema["groups"] == list(fusion.GROUP_ORDER)


def test_the_feature_count_is_what_we_expect():
    schema = fusion.describe_expected_schema(embedding_size=384)

    # 384 DINOv2 + 5 tile summary + 10 texture + 16 colour
    assert schema["dimension"] == 415, (
        "the feature vector changed size. That is allowed, but it invalidates "
        "every model trained before the change, so update this number "
        "deliberately and retrain."
    )


def test_the_fingerprint_is_stable():
    first = fusion.schema_fingerprint(
        fusion.describe_expected_schema(embedding_size=384))
    second = fusion.schema_fingerprint(
        fusion.describe_expected_schema(embedding_size=384))
    assert first == second


def test_a_different_layout_gets_a_different_fingerprint():
    normal = fusion.describe_expected_schema(embedding_size=384)
    bigger = fusion.describe_expected_schema(embedding_size=768)

    assert fusion.schema_fingerprint(normal) != fusion.schema_fingerprint(bigger)

    matches, reason = fusion.schemas_match(normal, bigger)
    assert not matches
    assert reason, "a refusal has to come with a reason a person can read"


def test_a_model_trained_on_another_robot_is_refused():
    ours = fusion.describe_expected_schema(embedding_size=384)
    theirs = dict(ours)
    theirs["hardware_profile"] = "some_other_robot"

    matches, reason = fusion.schemas_match(ours, theirs)

    assert not matches
    assert "hardware profile" in reason

def test_the_wording_is_the_approved_wording():
    """We screen textiles. We do not certify them, and the words say so."""
    assert (svm.describe_result(svm.DECISION_HANDMADE)
            == "Likely consistent with handmade production")
    assert (svm.describe_result(svm.DECISION_MACHINE)
            == "Likely consistent with machine production")
    assert svm.describe_result(svm.DECISION_INCONCLUSIVE) == "Inconclusive"

    for wording in svm.RESULT_WORDING.values():
        lowered = wording.lower()
        assert "authentic" not in lowered
        assert "certified" not in lowered
        assert "definitely" not in lowered
        assert "100%" not in lowered

def test_a_bad_photo_asks_for_a_rescan_rather_than_a_guess():
    decision = svm.decide_one_scan_area(
        quality_ok=False,
        quality_reasons=["image_blur"],
        probabilities=None,
        reference_match=None,
        thresholds=svm.choose_thresholds(),
        model_is_usable=False,
        rescans_already_done=0,
    )

    assert decision["decision"] == svm.DECISION_UNUSABLE
    assert decision["robot_command"]["command"] == "rescan"
    assert decision["handmade_probability"] is None


def test_rescanning_stops_after_the_limit():
    decision = svm.decide_one_scan_area(
        quality_ok=False,
        quality_reasons=["image_blur"],
        probabilities=None,
        reference_match=None,
        thresholds=svm.choose_thresholds(),
        model_is_usable=False,
        rescans_already_done=settings.MAXIMUM_RESCANS_PER_AREA,
    )

    assert decision["robot_command"]["command"] == "continue"
    assert "rescan_limit_reached" in decision["reasons"]


def test_no_model_means_inconclusive_not_a_made_up_answer():
    decision = svm.decide_one_scan_area(
        quality_ok=True,
        quality_reasons=[],
        probabilities=None,
        reference_match=None,
        thresholds=svm.choose_thresholds(),
        model_is_usable=False,
    )

    assert decision["decision"] == svm.DECISION_INCONCLUSIVE
    assert decision["handmade_probability"] is None
    assert "no_usable_classifier" in decision["reasons"]


def test_a_confident_score_gives_a_confident_answer():
    decision = svm.decide_one_scan_area(
        quality_ok=True,
        quality_reasons=[],
        probabilities={"handmade": 0.93, "machine": 0.07},
        reference_match={
            "out_of_domain": False,
            "handmade_similarity": 0.81,
            "machine_similarity": 0.44,
            "reasons": [],
        },
        thresholds=svm.choose_thresholds(),
        model_is_usable=True,
    )

    assert decision["decision"] == svm.DECISION_HANDMADE
    assert decision["robot_command"]["command"] == "continue"


def test_an_unfamiliar_textile_is_not_forced_into_a_class():
    decision = svm.decide_one_scan_area(
        quality_ok=True,
        quality_reasons=[],
        probabilities={"handmade": 0.97, "machine": 0.03},
        reference_match={
            "out_of_domain": True,
            "handmade_similarity": 0.11,
            "machine_similarity": 0.09,
            "reasons": ["out_of_domain"],
        },
        thresholds=svm.choose_thresholds(),
        model_is_usable=True,
    )

    assert decision["decision"] == svm.DECISION_INCONCLUSIVE, (
        "a very confident score on a textile we have no references for must "
        "not become a confident answer"
    )


def test_an_empty_reference_library_says_out_of_domain():
    library = ReferenceLibrary([])
    match = library.compare(np.ones(384))

    assert match["out_of_domain"]
    assert "reference_library_empty" in match["reasons"]


def test_cosine_similarity_recognises_the_same_direction():
    library = ReferenceLibrary([])
    library.add("H001", "handmade", np.array([1.0, 2.0, 3.0]))
    library.add("M001", "machine", np.array([-1.0, -2.0, -3.0]))

    # The same direction, twice as long. Cosine similarity ignores length.
    match = library.compare(np.array([2.0, 4.0, 6.0]))

    assert match["nearest_handmade"] == "H001"
    assert match["handmade_similarity"] == pytest.approx(1.0, abs=1e-9)
    assert not match["out_of_domain"]

def test_one_scan_through_the_whole_pipeline():
    from laptop_ai_code import get_dinov2_features_from_textile_photo as vision
    from laptop_ai_code import run_one_complete_scan_through_the_ai as pipeline

    if not vision.dinov2_is_available():
        pytest.skip("DINOv2 is not installed here: %s"
                    % vision.why_dinov2_is_not_available())

    joined_scan = {
        "scan_id": "TEST_R0_1",
        "textile_id": "TEST",
        "region_id": "R0",
        "photo_bytes": make_a_photo(),
        "colour_sensor_values": [9000.0, 8000.0, 7000.0],
        "colour_dark_reference": [100.0, 100.0, 100.0],
        "colour_white_reference": [20000.0, 19000.0, 18000.0],
        "region_ids_agree": True,
    }

    outcome = pipeline.run_one_scan(joined_scan)

    assert outcome["quality"]["photo_ok"]
    assert outcome["quality"]["colour_ok"]
    assert len(outcome["calibrated_colour"]) == 3

    prediction = outcome["prediction"]
    assert prediction["decision"] in (
        svm.DECISION_HANDMADE, svm.DECISION_MACHINE,
        svm.DECISION_INCONCLUSIVE, svm.DECISION_UNUSABLE,
    )
    assert prediction["robot_command"]["command"] in (
        "continue", "rescan", "inspect_neighbours",
    )

    if pipeline.load_the_model() is None:
        # No trained model, which is the normal state of a fresh checkout.
        assert prediction["decision"] == svm.DECISION_INCONCLUSIVE
        assert prediction["handmade_probability"] is None
