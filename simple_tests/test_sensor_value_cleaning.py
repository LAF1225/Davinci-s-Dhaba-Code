from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import clean_and_prepare_colour_sensor_readings as colour

DARK = [100.0, 100.0, 100.0]
WHITE = [20000.0, 19000.0, 18000.0]


def test_a_normal_reading_is_accepted():
    result = colour.calibrate_reading([9000.0, 8000.0, 7000.0], DARK, WHITE)

    assert result["ok"], result["reasons"]
    assert result["raw"] == [9000.0, 8000.0, 7000.0]
    assert len(result["calibrated"]) == 3
    # Reflectance should land between 0 and 1 for a sample between the two
    # references.
    for value in result["calibrated"]:
        assert 0.0 <= value <= 1.0


def test_raw_values_are_never_changed():
    raw = [70000.0, 8000.0, 7000.0]  # the first one is out of range
    result = colour.calibrate_reading(raw, DARK, WHITE)

    assert result["raw"] == raw
    assert not result["ok"]
    assert "colour_out_of_range" in result["reasons"]


def test_a_missing_reading_is_rejected():
    result = colour.calibrate_reading([], DARK, WHITE)

    assert not result["ok"]
    assert "colour_missing" in result["reasons"]


def test_a_stuck_sensor_is_rejected():
    result = colour.calibrate_reading([5000.0, 5000.0, 5000.0], DARK, WHITE)

    assert not result["ok"]
    assert "colour_constant_vector" in result["reasons"]


def test_the_wrong_number_of_channels_is_rejected():
    result = colour.calibrate_reading([5000.0, 6000.0], DARK, WHITE)

    assert not result["ok"]
    assert "colour_channel_count_mismatch" in result["reasons"]


def test_an_uncalibrated_reading_is_rejected_by_default():
    result = colour.calibrate_reading([9000.0, 8000.0, 7000.0])

    assert not result["ok"]
    assert "colour_uncalibrated" in result["reasons"]


def test_a_white_reference_that_is_not_brighter_than_dark_is_caught():
    broken_white = [120.0, 120.0, 120.0]  # barely above DARK
    result = colour.calibrate_reading(
        [9000.0, 8000.0, 7000.0], DARK, broken_white
    )

    assert not result["ok"]
    assert "colour_uncalibrated" in result["reasons"]


def test_the_feature_names_and_values_line_up():
    names = colour.colour_feature_names()
    result = colour.calibrate_reading([9000.0, 8000.0, 7000.0], DARK, WHITE)
    values = colour.get_colour_features(result["calibrated"])

    assert len(names) == len(values), (
        "there are %d colour feature names but %d values, which means the "
        "feature vector layout is broken" % (len(names), len(values))
    )


def test_the_feature_order_is_what_the_model_expects():
    names = colour.colour_feature_names()

    assert len(names) == 16, names
    assert names[0] == "colour_band_0"
    assert names[1] == "colour_band_1"
    assert names[2] == "colour_band_2"
    assert names[3] == "colour_adjdiff_0"
    assert names[-7:] == [
        "colour_mean", "colour_std", "colour_min", "colour_max",
        "colour_range", "colour_slope", "colour_argmax",
    ]


def test_a_short_reading_is_padded_rather_than_crashing():
    values = colour.get_colour_features([0.5])

    assert len(values) == len(colour.colour_feature_names())


def test_the_channel_count_matches_the_settings():
    assert settings.COLOUR_SENSOR_CHANNEL_COUNT == 3
    assert len(settings.COLOUR_SENSOR_CHANNEL_LABELS) == 3
