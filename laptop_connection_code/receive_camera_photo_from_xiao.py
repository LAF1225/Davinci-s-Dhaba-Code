import json
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile, status
from laptop_ai_code import ai_settings_and_thresholds as settings
from laptop_connection_code import scan_command_words as words
from laptop_connection_code.match_photo_and_sensor_data_using_scan_id import (
    waiting_scans,
)

router = APIRouter()

MAXIMUM_UPLOAD_BYTES = settings.MAXIMUM_PHOTO_UPLOAD_MEGABYTES * 1024 * 1024

on_scan_complete = None


def check_robot_key(supplied_key):
    if not settings.ROBOT_SHARED_KEY:
        return
    if supplied_key != settings.ROBOT_SHARED_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="the %s header did not match" % words.ROBOT_KEY_HEADER,
        )


@router.post(words.PHOTO_UPLOAD_PATH, status_code=status.HTTP_202_ACCEPTED)
async def receive_photo(
    photo: UploadFile = File(...),
    metadata: str = Form(...),
    x_robot_key: str = Header(default=""),
):
    check_robot_key(x_robot_key)

    try:
        fields = json.loads(metadata)
    except json.JSONDecodeError as problem:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the metadata part was not valid JSON: %s" % problem,
        )

    scan_id = str(fields.get("scan_id", "")).strip()
    if not scan_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the metadata did not contain a scan_id",
        )

    photo_bytes = await photo.read()
    if not photo_bytes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the photo upload was empty",
        )
    if len(photo_bytes) > MAXIMUM_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="the photo is %d bytes and the limit is %d"
                   % (len(photo_bytes), MAXIMUM_UPLOAD_BYTES),
        )

    joined, problem = waiting_scans.add_photo(scan_id, fields, photo_bytes)
    if problem:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=problem
        )

    if joined is not None and on_scan_complete is not None:
        on_scan_complete(joined)

    return {
        "accepted": True,
        "scan_id": scan_id,
        "waiting_for_sensor_values": joined is None,
    }
