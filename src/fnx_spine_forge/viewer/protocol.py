"""Versioned, validated command boundary for B5; no reflective method dispatch."""

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite

from ..json_types import JSONDocument, JSONValue, decode_json_object, is_document


class Command(StrEnum):
    PLAY = "PLAY"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP = "STOP"
    SEEK = "SEEK"
    STEP = "STEP"
    SET_ANIMATION = "SET_ANIMATION"
    SET_SKIN = "SET_SKIN"
    SET_LOOP = "SET_LOOP"
    SET_SPEED = "SET_SPEED"
    SET_CAMERA = "SET_CAMERA"
    SET_VIEWPORT = "SET_VIEWPORT"
    SET_BACKGROUND = "SET_BACKGROUND"
    RESET_CAMERA = "RESET_CAMERA"
    SET_DEBUG = "SET_DEBUG"
    CAPTURE_POSE = "CAPTURE_POSE"
    CAPTURE_FRAME = "CAPTURE_FRAME"
    GET_RUNTIME_INFO = "GET_RUNTIME_INFO"
    DISPOSE = "DISPOSE"


@dataclass(frozen=True)
class EmptyPayload:
    pass


@dataclass(frozen=True)
class TimePayload:
    seconds: float


@dataclass(frozen=True)
class AnimationPayload:
    name: str
    mix: float


@dataclass(frozen=True)
class SkinPayload:
    name: str | None


@dataclass(frozen=True)
class TogglePayload:
    enabled: bool


@dataclass(frozen=True)
class SpeedPayload:
    scale: float


@dataclass(frozen=True)
class CameraPayload:
    x: float
    y: float
    width: float
    height: float
    zoom: float


@dataclass(frozen=True)
class DebugPayload:
    bones: bool
    regions: bool
    mesh_triangles: bool
    mesh_hull: bool
    clipping: bool
    bounding_boxes: bool
    paths: bool
    origin: bool
    bounds: bool


@dataclass(frozen=True)
class ViewportPayload:
    width: int
    height: int
    pixel_ratio: float


@dataclass(frozen=True)
class ResponsiveViewportPayload:
    pass


@dataclass(frozen=True)
class BackgroundPayload:
    rgba: tuple[float, float, float, float]


Payload = (
    EmptyPayload
    | TimePayload
    | AnimationPayload
    | SkinPayload
    | TogglePayload
    | SpeedPayload
    | CameraPayload
    | DebugPayload
    | ViewportPayload
    | ResponsiveViewportPayload
    | BackgroundPayload
)


def _number(value: JSONValue, low: float, high: float) -> float:
    if type(value) not in (int, float) or not isinstance(value, (int, float)):
        raise ValueError("Expected finite number")
    if not isfinite(value) or not low <= value <= high:
        raise ValueError("Number outside viewer limits")
    return float(value)


def _string(value: JSONValue, limit: int = 128) -> str:
    if not isinstance(value, str) or not 1 <= len(value) <= limit:
        raise ValueError("Expected bounded nonempty string")
    return value


@dataclass(frozen=True)
class ViewerRequest:
    session_id: str
    request_id: str
    command: Command
    payload: Payload
    protocol_version: int = 1

    @classmethod
    def decode(cls, text: str) -> "ViewerRequest":
        doc = decode_json_object(text, "Viewer request")
        if set(doc) != {"protocolVersion", "sessionId", "requestId", "command", "payload"}:
            raise ValueError("Invalid request fields")
        if type(doc["protocolVersion"]) is not int or doc["protocolVersion"] != 1:
            raise ValueError("Unsupported protocol version")
        session = _string(doc["sessionId"])
        request = _string(doc["requestId"])
        command = Command(_string(doc["command"]))
        raw = doc["payload"]
        if command == Command.SET_VIEWPORT and raw is None:
            return cls(session, request, command, ResponsiveViewportPayload())
        if not is_document(raw):
            raise ValueError("Expected object payload")
        payload: Payload
        keys: set[str] = set()
        if command in (Command.SEEK, Command.STEP):
            keys = {"seconds"}
            payload = TimePayload(
                _number(raw.get("seconds"), 0, 600 if command == Command.SEEK else 1)
            )
        elif command == Command.SET_ANIMATION:
            keys = {"name", "mix"}
            payload = AnimationPayload(
                _string(raw.get("name"), 1024), _number(raw.get("mix"), 0, 10)
            )
        elif command == Command.SET_SKIN:
            keys = {"name"}
            name = raw.get("name")
            if name is not None and (not isinstance(name, str) or len(name) > 1024):
                raise ValueError("Invalid skin name")
            payload = SkinPayload(name)
        elif command == Command.SET_LOOP:
            keys = {"enabled"}
            flag = raw.get("enabled")
            if not isinstance(flag, bool):
                raise ValueError("Expected boolean toggle")
            payload = TogglePayload(flag)
        elif command == Command.SET_DEBUG:
            keys = {
                "bones",
                "regions",
                "meshTriangles",
                "meshHull",
                "clipping",
                "boundingBoxes",
                "paths",
                "origin",
                "bounds",
            }
            flags: dict[str, bool] = {}
            for key in keys:
                flag_value = raw.get(key)
                if not isinstance(flag_value, bool):
                    raise ValueError("Expected debug flag")
                flags[key] = flag_value
            payload = DebugPayload(
                flags["bones"],
                flags["regions"],
                flags["meshTriangles"],
                flags["meshHull"],
                flags["clipping"],
                flags["boundingBoxes"],
                flags["paths"],
                flags["origin"],
                flags["bounds"],
            )
        elif command == Command.SET_VIEWPORT:
            keys = {"width", "height", "pixelRatio"}
            width, height = raw.get("width"), raw.get("height")
            if type(width) is not int or type(height) is not int:
                raise ValueError("Integer viewport dimensions required")
            w, h = int(_number(width, 1, 4096)), int(_number(height, 1, 4096))
            ratio = _number(raw.get("pixelRatio"), 0.25, 3)
            if w * h * ratio * ratio > 16777216:
                raise ValueError("Viewport allocation limit exceeded")
            payload = ViewportPayload(w, h, ratio)
        elif command == Command.SET_BACKGROUND:
            keys = {"rgba"}
            rgba = raw.get("rgba")
            if not isinstance(rgba, list) or len(rgba) != 4:
                raise ValueError("Four RGBA channels required")
            payload = BackgroundPayload(
                (
                    _number(rgba[0], 0, 1),
                    _number(rgba[1], 0, 1),
                    _number(rgba[2], 0, 1),
                    _number(rgba[3], 0, 1),
                )
            )
        elif command == Command.SET_SPEED:
            keys = {"scale"}
            payload = SpeedPayload(_number(raw.get("scale"), 0, 4))
        elif command == Command.SET_CAMERA:
            keys = {"x", "y", "width", "height", "zoom"}
            payload = CameraPayload(
                _number(raw.get("x"), -1e9, 1e9),
                _number(raw.get("y"), -1e9, 1e9),
                _number(raw.get("width"), 1e-9, 1e9),
                _number(raw.get("height"), 1e-9, 1e9),
                _number(raw.get("zoom"), 0.01, 100),
            )
        else:
            payload = EmptyPayload()
        if set(raw) != keys:
            raise ValueError("Invalid command payload fields")
        return cls(session, request, command, payload)

    def to_dict(self) -> JSONDocument:
        p = self.payload
        payload: JSONValue
        if isinstance(p, TimePayload):
            payload = {"seconds": p.seconds}
        elif isinstance(p, AnimationPayload):
            payload = {"name": p.name, "mix": p.mix}
        elif isinstance(p, SkinPayload):
            payload = {"name": p.name}
        elif isinstance(p, TogglePayload):
            payload = {"enabled": p.enabled}
        elif isinstance(p, SpeedPayload):
            payload = {"scale": p.scale}
        elif isinstance(p, DebugPayload):
            payload = {
                "bones": p.bones,
                "regions": p.regions,
                "meshTriangles": p.mesh_triangles,
                "meshHull": p.mesh_hull,
                "clipping": p.clipping,
                "boundingBoxes": p.bounding_boxes,
                "paths": p.paths,
                "origin": p.origin,
                "bounds": p.bounds,
            }
        elif isinstance(p, ViewportPayload):
            payload = {"width": p.width, "height": p.height, "pixelRatio": p.pixel_ratio}
        elif isinstance(p, ResponsiveViewportPayload):
            payload = None
        elif isinstance(p, BackgroundPayload):
            payload = {"rgba": list(p.rgba)}
        elif isinstance(p, CameraPayload):
            payload = {"x": p.x, "y": p.y, "width": p.width, "height": p.height, "zoom": p.zoom}
        else:
            payload = {}
        return {
            "protocolVersion": self.protocol_version,
            "sessionId": self.session_id,
            "requestId": self.request_id,
            "command": self.command.value,
            "payload": payload,
        }
