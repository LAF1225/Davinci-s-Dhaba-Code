import queue
import threading
import time

from fastapi import FastAPI, HTTPException

from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_ai_code import combine_results_from_different_scan_areas as combiner
from laptop_ai_code import run_one_complete_scan_through_the_ai as pipeline
from laptop_connection_code import receive_camera_photo_from_xiao as photo_endpoint
from laptop_connection_code import receive_sensor_values_from_main_esp32 as sensor_endpoint
from laptop_connection_code import save_scan_information_to_existing_database as store
from laptop_connection_code import scan_command_words as words
from laptop_connection_code.match_photo_and_sensor_data_using_scan_id import (
    waiting_scans,
)

app = FastAPI(title="ASIL textile analyser laptop server")
app.include_router(photo_endpoint.router)
app.include_router(sensor_endpoint.router)

_work_queue = queue.Queue()
_worker_started = False


def _handle_completed_scan(joined_scan):
    photo_path = store.save_photo_file(
        joined_scan["scan_id"], joined_scan["photo_bytes"]
    )
    rescans_already_done = store.count_rescans_for_area(
        joined_scan.get("textile_id", ""), joined_scan.get("region_id", "")
    )
    store.save_scan(joined_scan, photo_path, rescan_count=rescans_already_done)
    _work_queue.put((joined_scan, rescans_already_done))


def _worker_loop():
    while True:
        joined_scan, rescans_already_done = _work_queue.get()
        try:
            already_done = len(
                store.get_scan_areas_for_textile(joined_scan.get("textile_id", ""))
            )
            outcome = pipeline.run_one_scan(
                joined_scan,
                rescans_already_done=rescans_already_done,
                scan_areas_done=already_done,
                scan_areas_planned=settings.SCAN_AREAS_PER_TEXTILE,
            )
            store.save_result(
                joined_scan["scan_id"],
                outcome["quality"],
                outcome["prediction"],
                outcome["calibrated_colour"],
                outcome["model_version"],
            )
        except Exception as problem:
            store.save_result(
                joined_scan["scan_id"],
                {},
                {"decision": "unusable", "robot_command":
                    {"command": words.RESCAN, "reason": "laptop_error"}},
                [],
                None,
                error_message="%s: %s" % (type(problem).__name__, problem),
            )
        finally:
            _work_queue.task_done()


def _timeout_sweeper():
    while True:
        time.sleep(settings.SCAN_JOIN_TIMEOUT_SECONDS)
        for scan_id in waiting_scans.take_expired():
            print("[join] scan %s never received its other half within %.0f "
                  "seconds; the robot should rescan that area"
                  % (scan_id, settings.SCAN_JOIN_TIMEOUT_SECONDS))


def start_background_threads():
    global _worker_started
    if _worker_started:
        return
    _worker_started = True

    photo_endpoint.on_scan_complete = _handle_completed_scan
    sensor_endpoint.on_scan_complete = _handle_completed_scan

    threading.Thread(target=_worker_loop, daemon=True).start()
    threading.Thread(target=_timeout_sweeper, daemon=True).start()


def print_what_works():
    state = pipeline.ai_status()
    print("ASIL laptop server")
    print("  DINOv2        : %s" % state["dinov2_detail"])
    print("  trained model : %s" % (state["model_version"] or "none loaded"))
    if state["model_problem"]:
        print("  model problem : %s" % state["model_problem"])
    print("  references    : %d verified textiles" % state["reference_count"])
    print("  what works    : %s" % state["what_works"])


start_background_threads()


@app.get(words.HEALTH_PATH)
def health():
    status = pipeline.ai_status()
    status["scans_waiting_for_their_other_half"] = waiting_scans.waiting_count()
    status["scans_waiting_for_the_ai"] = _work_queue.qsize()
    return status


@app.get(words.SCAN_RESULT_PATH + "/{scan_id}")
def scan_result(scan_id: str):
    """The main ESP32 polls this after uploading its sensor values."""
    if waiting_scans.is_waiting_for_other_half(scan_id):
        return {"scan_id": scan_id, "status": "waiting_for_the_other_half"}

    row = store.get_scan(scan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="no scan with that scan_id")

    if row["status"] == "stored":
        return {"scan_id": scan_id, "status": "processing"}

    import json

    robot_command = json.loads(row["robot_command_json"] or "{}")
    return {
        "scan_id": scan_id,
        "status": row["status"],
        "decision": row["decision"],
        "handmade_probability": row["handmade_probability"],
        "confidence": row["confidence"],
        "quality": json.loads(row["quality_json"] or "{}"),
        "reasons": json.loads(row["reasons_json"] or "[]"),
        "command": robot_command.get("command", words.CONTINUE),
        "command_reason": robot_command.get("reason", ""),
        "extra_scan_areas": robot_command.get("extra_scan_areas"),
        "settle_ms": robot_command.get("settle_ms"),
        "error": row["error_message"],
    }


@app.get(words.TEXTILE_RESULT_PATH + "/{textile_id}")
def textile_result(textile_id: str):
    """The answer for one whole textile, from all its scan areas so far."""
    scan_areas = store.get_scan_areas_for_textile(textile_id)
    if not scan_areas:
        raise HTTPException(
            status_code=404, detail="no scans stored for that textile_id"
        )

    combined = combiner.combine_scan_areas(
        scan_areas, scan_areas_planned=settings.SCAN_AREAS_PER_TEXTILE
    )
    combined["textile_id"] = textile_id
    combined["disclaimer"] = (
        "Preliminary screening result. Expert verification is recommended for "
        "formal authentication."
    )
    return combined


def main():
    import uvicorn

    print_what_works()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
