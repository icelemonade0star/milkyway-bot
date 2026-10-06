import base64
import struct
import zlib
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CANVAS_WIDTH = 800
CANVAS_HEIGHT = 600
MAX_CANVAS_WIDTH = 1920
MAX_CANVAS_HEIGHT = 1080
MAX_FINAL_PNG_LENGTH = 8_000_000
MAX_POINTS = 25000
MAX_DURATION_MS = 600000


class DrawingDonationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    minimum_amount: int = Field(default=1000, ge=0, le=100000000)
    replay_seconds: int = Field(default=20, ge=3, le=120)
    hold_seconds: int = Field(default=5, ge=1, le=30)
    canvas_width: int = Field(default=CANVAS_WIDTH, ge=320, le=MAX_CANVAS_WIDTH)
    canvas_height: int = Field(default=CANVAS_HEIGHT, ge=180, le=MAX_CANVAS_HEIGHT)
    show_donor: bool = True

    @model_validator(mode="before")
    @classmethod
    def discard_legacy_display_width(cls, value: object) -> object:
        # 기존 DB 설정과 재생 항목의 표시 너비는 전체 화면 재생에서 사용하지 않는다.
        if isinstance(value, dict) and "display_width" in value:
            return {key: item for key, item in value.items() if key != "display_width"}
        return value


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    x: float = Field(ge=0, le=MAX_CANVAS_WIDTH)
    y: float = Field(ge=0, le=MAX_CANVAS_HEIGHT)
    t: int = Field(ge=0, le=MAX_DURATION_MS)


class Stroke(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    type: Literal["stroke"]
    tool: Literal["pen", "eraser"] = "pen"
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    width: float = Field(ge=1, le=60)
    points: list[Point] = Field(min_length=1, max_length=MAX_POINTS)


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["undo", "clear"]
    t: int = Field(ge=0, le=MAX_DURATION_MS)


class Recording(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=CANVAS_WIDTH, ge=320, le=MAX_CANVAS_WIDTH)
    height: int = Field(default=CANVAS_HEIGHT, ge=180, le=MAX_CANVAS_HEIGHT)
    actions: list[Annotated[Stroke | Edit, Field(discriminator="type")]] = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_timeline(self):
        previous, count = -1, 0
        for action in self.actions:
            if isinstance(action, Stroke) and any(point.x > self.width or point.y > self.height for point in action.points):
                raise ValueError("그리기 좌표가 캔버스 크기를 벗어났습니다.")
            times = [point.t for point in action.points] if isinstance(action, Stroke) else [action.t]
            count += len(times)
            for timestamp in times:
                if timestamp < previous:
                    raise ValueError("그리기 기록의 시간 순서가 올바르지 않습니다.")
                previous = timestamp
        if count > MAX_POINTS or not any(isinstance(action, Stroke) for action in self.actions):
            raise ValueError("그리기 기록은 선을 포함하고 25,000개 포인트 이하여야 합니다.")
        return self


class DrawingSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    save_key: UUID
    recording: Recording
    # 전체 10MB 요청에서 기록 JSON과 메타데이터가 들어갈 공간을 남긴다.
    final_png: str = Field(max_length=MAX_FINAL_PNG_LENGTH)

    @model_validator(mode="after")
    def validate_png(self):
        prefix = "data:image/png;base64,"
        if not self.final_png.startswith(prefix):
            raise ValueError("완성본은 PNG 이미지여야 합니다.")
        try:
            data = base64.b64decode(self.final_png[len(prefix):], validate=True)
        except ValueError as exc:
            raise ValueError("완성본 이미지가 올바르지 않습니다.") from exc
        if len(data) < 33 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
            raise ValueError("완성본 PNG 헤더가 올바르지 않습니다.")
        if struct.unpack(">II", data[16:24]) != (self.recording.width, self.recording.height):
            raise ValueError("완성본 크기는 그리기 캔버스 크기와 같아야 합니다.")
        # 헤더만 위조한 이미지나 압축 데이터 손상을 저장 전에 확인한다.
        offset, compressed, ended, color_type = 8, bytearray(), False, None
        try:
            while offset < len(data):
                size = struct.unpack(">I", data[offset:offset + 4])[0]
                kind = data[offset + 4:offset + 8]
                end = offset + 12 + size
                if end > len(data):
                    raise ValueError("PNG 청크 길이 오류")
                chunk = data[offset + 8:end - 4]
                crc = struct.unpack(">I", data[end - 4:end])[0]
                if zlib.crc32(kind + chunk) != crc:
                    raise ValueError("PNG 청크 검증 오류")
                if kind == b"IHDR":
                    if offset != 8 or size != 13 or chunk[8] != 8 or chunk[9] not in (2, 6) or chunk[10:] != b"\0\0\0":
                        raise ValueError("PNG 이미지 형식 오류")
                    color_type = chunk[9]
                elif kind == b"IDAT":
                    compressed.extend(chunk)
                elif kind == b"IEND":
                    if size or end != len(data):
                        raise ValueError("PNG 종료 청크 오류")
                    ended = True
                offset = end
            expected = (self.recording.width * (4 if color_type == 6 else 3) + 1) * self.recording.height
            decoder = zlib.decompressobj()
            pixels = decoder.decompress(bytes(compressed), expected + 1)
            if not ended or color_type is None or not decoder.eof or decoder.unused_data or len(pixels) != expected:
                raise ValueError("PNG 이미지 데이터 오류")
        except (ValueError, struct.error, zlib.error) as exc:
            raise ValueError("완성본 PNG 데이터가 올바르지 않습니다.") from exc
        return self
