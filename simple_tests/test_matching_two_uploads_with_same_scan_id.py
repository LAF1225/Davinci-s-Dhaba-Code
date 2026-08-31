import time

from laptop_connection_code.match_photo_and_sensor_data_using_scan_id import (
    WaitingScans,
)

SENSOR_HALF = {
    "textile_id": "H001",
    "region_id": "R2",
    "row_index": 0,
    "column_index": 2,
    "colour_sensor_values": [9000.0, 8000.0, 7000.0],
    "robot_status": "ok",
}

PHOTO_HALF = {
    "region_id": "R2",
    "camera_status": "ok",
}


def test_the_two_halves_are_joined_when_the_ids_match():
    waiting = WaitingScans()

    joined, problem = waiting.add_sensors("H001_R2_1000", SENSOR_HALF)
    assert problem is None
    assert joined is None, "it should wait for the photo"

    joined, problem = waiting.add_photo("H001_R2_1000", PHOTO_HALF, b"jpeg")
    assert problem is None
    assert joined is not None, "both halves are here, it should have joined"

    assert joined["scan_id"] == "H001_R2_1000"
    assert joined["textile_id"] == "H001"
    assert joined["colour_sensor_values"] == [9000.0, 8000.0, 7000.0]
    assert joined["photo_bytes"] == b"jpeg"


def test_it_works_the_other_way_round_too():
    waiting = WaitingScans()

    joined, problem = waiting.add_photo("H001_R3_2000", PHOTO_HALF, b"jpeg")
    assert problem is None
    assert joined is None

    joined, problem = waiting.add_sensors("H001_R3_2000", SENSOR_HALF)
    assert problem is None
    assert joined is not None


def test_two_different_scan_ids_are_never_paired():
    waiting = WaitingScans()

    joined, _ = waiting.add_sensors("H001_R2_1000", SENSOR_HALF)
    assert joined is None

    joined, _ = waiting.add_photo("H001_R9_9999", PHOTO_HALF, b"jpeg")
    assert joined is None, (
        "a photo with a different scan id was paired with a sensor reading, "
        "which would put the wrong numbers next to the wrong photo"
    )

    assert waiting.waiting_count() == 2


def test_the_same_half_arriving_twice_is_reported():
    waiting = WaitingScans()

    waiting.add_photo("H001_R2_1000", PHOTO_HALF, b"jpeg")
    joined, problem = waiting.add_photo("H001_R2_1000", PHOTO_HALF, b"other")

    assert joined is None
    assert problem is not None
    assert "twice" in problem


def test_an_upload_with_no_scan_id_is_refused():
    waiting = WaitingScans()

    joined, problem = waiting.add_photo("", PHOTO_HALF, b"jpeg")

    assert joined is None
    assert problem is not None


def test_a_half_that_never_gets_its_partner_times_out():
    waiting = WaitingScans(timeout_seconds=0.2)

    waiting.add_sensors("H001_R2_1000", SENSOR_HALF)
    assert waiting.waiting_count() == 1

    time.sleep(0.3)

    expired = waiting.take_expired()
    assert expired == ["H001_R2_1000"]
    assert waiting.waiting_count() == 0


def test_a_late_photo_does_not_join_a_timed_out_sensor_reading():
    waiting = WaitingScans(timeout_seconds=0.2)

    waiting.add_sensors("H001_R2_1000", SENSOR_HALF)
    time.sleep(0.3)

    joined, problem = waiting.add_photo("H001_R2_1000", PHOTO_HALF, b"jpeg")

    assert joined is None
    assert problem is None
    assert waiting.waiting_count() == 1


def test_a_repeated_upload_after_joining_is_reported():
    waiting = WaitingScans()

    waiting.add_sensors("H001_R2_1000", SENSOR_HALF)
    joined, _ = waiting.add_photo("H001_R2_1000", PHOTO_HALF, b"jpeg")
    assert joined is not None

    joined, problem = waiting.add_photo("H001_R2_1000", PHOTO_HALF, b"jpeg")
    assert joined is None
    assert problem is not None


def test_disagreeing_region_ids_are_flagged_not_hidden():
    waiting = WaitingScans()

    waiting.add_sensors("H001_R2_1000", SENSOR_HALF)
    joined, _ = waiting.add_photo(
        "H001_R2_1000", {"region_id": "R7", "camera_status": "ok"}, b"jpeg"
    )

    assert joined is not None
    assert joined["region_ids_agree"] is False
