from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from laptop_connection_code import scan_command_words as words
from laptop_connection_code.match_photo_and_sensor_data_using_scan_id import (
    waiting_scans,
)
from laptop_connection_code.receive_camera_photo_from_xiao import check_robot_key

router = APIRouter()

on_scan_complete = None


class SensorUpload(BaseModel):
    scan_id: str = Field(min_length=1, max_length=96)
    textile_id: str = ""
    region_id: str = ""

    scan_index: int | None = None
    row_index: int | None = None
    column_index: int | None = None

    x_position: float | None = None
    y_position: float | None = None

    timestamp: str | None = None
    robot_status: str = ""

    colour_sensor_values: list[float] = Field(default_factory=list)
    colour_dark_reference: list[float] | None = None
    colour_white_reference: list[float] | None = None


@router.post(words.SENSOR_UPLOAD_PATH, status_code=status.HTTP_202_ACCEPTED)
async def receive_sensor_values(
    upload: SensorUpload,
    x_robot_key: str = Header(default=""),
):
    check_robot_key(x_robot_key)

    fields = upload.model_dump()
    joined, problem = waiting_scans.add_sensors(upload.scan_id, fields)
    if problem:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=problem
        )

    if joined is not None and on_scan_complete is not None:
        on_scan_complete(joined)

    return {
        "accepted": True,
        "scan_id": upload.scan_id,
        "waiting_for_photo": joined is None,
        "poll": "%s/%s" % (words.SCAN_RESULT_PATH, upload.scan_id),
    }
