import threading
import time

from laptop_ai_code import ai_settings_and_thresholds as settings


class WaitingScans:
    def __init__(self, timeout_seconds=None):
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.SCAN_JOIN_TIMEOUT_SECONDS
        )
        self._lock = threading.Lock()
        # scan_id -> {"photo": {...} or None, "sensors": {...} or None,
        #             "first_arrival": time}
        self._waiting = {}
        # scan_ids that have already been joined and handed on, kept so a
        # repeated upload is spotted instead of starting a new half.
        self._already_joined = set()

    def add_photo(self, scan_id, photo_fields, photo_bytes):
        return self._add(scan_id, "photo", dict(photo_fields, photo_bytes=photo_bytes))

    def add_sensors(self, scan_id, sensor_fields):
        return self._add(scan_id, "sensors", dict(sensor_fields))

    def _add(self, scan_id, half_name, payload):
        scan_id = str(scan_id)
        if not scan_id:
            return None, "the upload had no scan_id"

        with self._lock:
            self._drop_expired_already_locked()

            if scan_id in self._already_joined:
                return None, (
                    "scan_id %s has already been joined and processed; this "
                    "looks like a repeated upload" % scan_id
                )

            entry = self._waiting.get(scan_id)
            if entry is None:
                entry = {"photo": None, "sensors": None,
                         "first_arrival": time.monotonic()}
                self._waiting[scan_id] = entry

            if entry[half_name] is not None:
                return None, (
                    "the %s half of scan_id %s arrived twice" % (half_name, scan_id)
                )

            entry[half_name] = payload

            if entry["photo"] is None or entry["sensors"] is None:
                return None, None

            joined = self._join(scan_id, entry["photo"], entry["sensors"])
            del self._waiting[scan_id]
            self._already_joined.add(scan_id)
            return joined, None


    @staticmethod
    def _join(scan_id, photo_half, sensor_half):
        return {
            "scan_id": scan_id,

            "textile_id": sensor_half.get("textile_id", ""),
            "region_id": sensor_half.get("region_id", ""),
            "scan_index": sensor_half.get("scan_index"),
            "row_index": sensor_half.get("row_index"),
            "column_index": sensor_half.get("column_index"),
            "x_position": sensor_half.get("x_position"),
            "y_position": sensor_half.get("y_position"),
            "colour_sensor_values": sensor_half.get("colour_sensor_values", []),
            "colour_dark_reference": sensor_half.get("colour_dark_reference"),
            "colour_white_reference": sensor_half.get("colour_white_reference"),
            "robot_status": sensor_half.get("robot_status", ""),
            "sensor_timestamp": sensor_half.get("timestamp"),

            "photo_bytes": photo_half.get("photo_bytes", b""),
            "camera_status": photo_half.get("camera_status", ""),
            "camera_settings": photo_half.get("image_capture_settings", {}),
            "camera_timestamp": photo_half.get("timestamp"),
            "camera_region_id": photo_half.get("region_id", ""),

            "region_ids_agree": (
                not photo_half.get("region_id")
                or str(photo_half.get("region_id")) == str(
                    sensor_half.get("region_id", ""))
            ),
        }


    def _drop_expired_already_locked(self):
        now = time.monotonic()
        expired = [
            scan_id for scan_id, entry in self._waiting.items()
            if now - entry["first_arrival"] > self.timeout_seconds
        ]
        for scan_id in expired:
            del self._waiting[scan_id]
        return expired

    def take_expired(self):
        with self._lock:
            return self._drop_expired_already_locked()

    def waiting_count(self):
        with self._lock:
            return len(self._waiting)

    def is_waiting_for_other_half(self, scan_id):
        with self._lock:
            return str(scan_id) in self._waiting


waiting_scans = WaitingScans()
