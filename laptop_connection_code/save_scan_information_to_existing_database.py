import json
import os
import sqlite3
from datetime import datetime, timezone

from laptop_ai_code import ai_settings_and_thresholds as settings

DATABASE_PATH = os.path.join(settings.PROJECT_FOLDER, "saved_ai_files", "scans.db")
PHOTO_FOLDER = os.path.join(settings.PROJECT_FOLDER, "saved_ai_files", "scan_photos")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS scans (
    scan_id                  TEXT PRIMARY KEY,
    textile_id               TEXT,
    region_id                TEXT,
    scan_index               INTEGER,
    row_index                INTEGER,
    column_index             INTEGER,
    x_position               REAL,
    y_position               REAL,
    photo_path               TEXT,
    camera_status            TEXT,
    robot_status             TEXT,
    raw_colour_json          TEXT,
    calibrated_colour_json   TEXT,
    quality_json             TEXT,
    decision                 TEXT,
    handmade_probability     REAL,
    machine_probability      REAL,
    confidence               REAL,
    nearest_handmade         TEXT,
    handmade_similarity      REAL,
    nearest_machine          TEXT,
    machine_similarity       REAL,
    out_of_domain            INTEGER DEFAULT 0,
    robot_command_json       TEXT,
    reasons_json             TEXT,
    model_version            TEXT,
    rescan_count             INTEGER DEFAULT 0,
    status                   TEXT DEFAULT 'stored',
    error_message            TEXT,
    created_at               TEXT,
    processed_at             TEXT
)
"""

CREATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS scans_by_textile ON scans (textile_id)"
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def open_database():
    """Open the database, creating the file and the table if they are new."""
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute(CREATE_TABLE_SQL)
    connection.execute(CREATE_INDEX_SQL)
    connection.commit()
    return connection


def save_photo_file(scan_id, photo_bytes):
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    safe_name = "".join(
        character if character.isalnum() or character in "-_" else "_"
        for character in str(scan_id)
    )[:96]
    path = os.path.join(PHOTO_FOLDER, safe_name + ".jpg")
    with open(path, "wb") as handle:
        handle.write(photo_bytes)
    return path


def scan_already_exists(scan_id):
    connection = open_database()
    try:
        row = connection.execute(
            "SELECT scan_id FROM scans WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        return row is not None
    finally:
        connection.close()


def count_rescans_for_area(textile_id, region_id):
    connection = open_database()
    try:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM scans "
            "WHERE textile_id = ? AND region_id = ?",
            (textile_id, region_id),
        ).fetchone()
        return int(row["total"]) if row else 0
    finally:
        connection.close()


def save_scan(joined_scan, photo_path, rescan_count=0):
    connection = open_database()
    try:
        connection.execute(
            "INSERT OR REPLACE INTO scans ("
            " scan_id, textile_id, region_id, scan_index, row_index, column_index,"
            " x_position, y_position, photo_path, camera_status, robot_status,"
            " raw_colour_json, rescan_count, status, created_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                joined_scan["scan_id"],
                joined_scan.get("textile_id", ""),
                joined_scan.get("region_id", ""),
                joined_scan.get("scan_index"),
                joined_scan.get("row_index"),
                joined_scan.get("column_index"),
                joined_scan.get("x_position"),
                joined_scan.get("y_position"),
                photo_path,
                joined_scan.get("camera_status", ""),
                joined_scan.get("robot_status", ""),
                json.dumps(joined_scan.get("colour_sensor_values", [])),
                int(rescan_count),
                "stored",
                _now(),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def save_result(scan_id, quality, prediction, calibrated_colour, model_version,
                error_message=None):
    connection = open_database()
    try:
        connection.execute(
            "UPDATE scans SET"
            " calibrated_colour_json = ?, quality_json = ?, decision = ?,"
            " handmade_probability = ?, machine_probability = ?, confidence = ?,"
            " nearest_handmade = ?, handmade_similarity = ?,"
            " nearest_machine = ?, machine_similarity = ?, out_of_domain = ?,"
            " robot_command_json = ?, reasons_json = ?, model_version = ?,"
            " status = ?, error_message = ?, processed_at = ?"
            " WHERE scan_id = ?",
            (
                json.dumps(calibrated_colour or []),
                json.dumps(quality or {}),
                prediction.get("decision"),
                prediction.get("handmade_probability"),
                prediction.get("machine_probability"),
                prediction.get("confidence"),
                (prediction.get("reference") or {}).get("nearest_handmade"),
                (prediction.get("reference") or {}).get("handmade_similarity"),
                (prediction.get("reference") or {}).get("nearest_machine"),
                (prediction.get("reference") or {}).get("machine_similarity"),
                1 if (prediction.get("reference") or {}).get("out_of_domain") else 0,
                json.dumps(prediction.get("robot_command") or {}),
                json.dumps(prediction.get("reasons") or []),
                model_version,
                "failed" if error_message else "complete",
                error_message,
                _now(),
                scan_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def get_scan(scan_id):
    connection = open_database()
    try:
        row = connection.execute(
            "SELECT * FROM scans WHERE scan_id = ?", (scan_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        connection.close()


def get_scan_areas_for_textile(textile_id):
    connection = open_database()
    try:
        rows = connection.execute(
            "SELECT * FROM scans WHERE textile_id = ? ORDER BY created_at",
            (textile_id,),
        ).fetchall()
    finally:
        connection.close()

    newest_per_area = {}
    for row in rows:
        newest_per_area[row["region_id"]] = row

    scan_areas = []
    for row in newest_per_area.values():
        scan_areas.append({
            "scan_id": row["scan_id"],
            "decision": row["decision"] or "inconclusive",
            "handmade_probability": row["handmade_probability"],
            "usable": row["status"] == "complete" and row["decision"] != "unusable",
            "handmade_similarity": row["handmade_similarity"],
            "machine_similarity": row["machine_similarity"],
            "out_of_domain": bool(row["out_of_domain"]),
            "row_index": row["row_index"],
            "column_index": row["column_index"],
            "rescan_count": int(row["rescan_count"] or 0),
        })
    return scan_areas
