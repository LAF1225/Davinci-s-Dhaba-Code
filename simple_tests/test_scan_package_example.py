import json

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_connection_code import scan_command_words as words
from laptop_connection_code.match_photo_and_sensor_data_using_scan_id import (
    WaitingScans,
)


def test_the_photo_metadata_has_everything_the_laptop_needs():
    fields = json.loads(EXAMPLE_PHOTO_METADATA)

    assert fields["scan_id"], "without a scan id the photo cannot be paired"
    assert "region_id" in fields
    assert "camera_status" in fields
    assert "timestamp" in fields
    assert fields["image_capture_settings"]["format"] == "jpeg"


def test_the_sensor_upload_has_everything_the_laptop_needs():
    fields = json.loads(EXAMPLE_SENSOR_UPLOAD)

    assert fields["scan_id"]
    assert fields["textile_id"], (
        "without a textile id the scan cannot be filed under a piece of cloth"
    )
    assert len(fields["colour_sensor_values"]) == (
        settings.COLOUR_SENSOR_CHANNEL_COUNT
    )
    assert len(fields["colour_dark_reference"]) == (
        settings.COLOUR_SENSOR_CHANNEL_COUNT
    )
    assert len(fields["colour_white_reference"]) == (
        settings.COLOUR_SENSOR_CHANNEL_COUNT
    )


def test_the_white_reference_in_the_example_is_actually_brighter_than_dark():
    fields = json.loads(EXAMPLE_SENSOR_UPLOAD)

    for dark, white in zip(fields["colour_dark_reference"],
                           fields["colour_white_reference"]):
        assert white - dark >= settings.MINIMUM_WHITE_MINUS_DARK


def test_both_examples_use_the_same_scan_id():
    photo = json.loads(EXAMPLE_PHOTO_METADATA)
    sensors = json.loads(EXAMPLE_SENSOR_UPLOAD)

    assert photo["scan_id"] == sensors["scan_id"]


def test_the_example_pair_joins_into_one_record():
    waiting = WaitingScans()
    photo = json.loads(EXAMPLE_PHOTO_METADATA)
    sensors = json.loads(EXAMPLE_SENSOR_UPLOAD)

    waiting.add_sensors(sensors["scan_id"], sensors)
    joined, problem = waiting.add_photo(photo["scan_id"], photo, b"fake jpeg")

    assert problem is None
    assert joined is not None
    assert joined["textile_id"] == "H001"
    assert joined["region_ids_agree"] is True
    assert joined["colour_sensor_values"] == [9120, 8340, 7015]


def test_the_command_words_the_firmware_must_handle_exist():
    assert words.CONTINUE == "continue"
    assert words.RESCAN == "rescan"
    assert words.COMPLETE == "complete"
    assert words.INSPECT_NEIGHBOURS in words.ALL_LAPTOP_COMMANDS


def test_the_upload_paths_match_what_the_firmware_posts_to():
    assert words.PHOTO_UPLOAD_PATH == "/api/v1/scan_photo"
    assert words.SENSOR_UPLOAD_PATH == "/api/v1/scan_sensors"
    assert words.SCAN_RESULT_PATH == "/api/v1/scan_result"
