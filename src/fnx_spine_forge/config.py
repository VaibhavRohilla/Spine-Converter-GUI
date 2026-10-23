from dataclasses import dataclass, field

from .source import DEFAULT_LIMITS, SourceLimits


@dataclass(frozen=True)
class InspectionConfig:
    source_limits: SourceLimits = field(default_factory=lambda: DEFAULT_LIMITS)
    max_skeleton_json_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.max_skeleton_json_bytes < 0:
            raise ValueError("max_skeleton_json_bytes must be non-negative")
