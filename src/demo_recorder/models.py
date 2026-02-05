"""Pydantic v2 models for demo script schema."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ActionType(str, Enum):
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCROLL = "scroll"
    HOVER = "hover"
    SELECT = "select"
    WAIT = "wait"
    SCREENSHOT = "screenshot"


class Viewport(BaseModel):
    width: int = 1280
    height: int = 720


class Metadata(BaseModel):
    title: str = "Demo Recording"
    description: str = ""
    base_url: str = "http://localhost:8080"
    viewport: Viewport = Field(default_factory=Viewport)
    voice: str = "en-US-AriaNeural"
    rate: str = "+0%"
    output_name: str = "demo"


class Step(BaseModel):
    id: str
    action: ActionType
    narration: str = ""

    # navigate
    url: Optional[str] = None

    # click, type, scroll, hover, select
    selector: Optional[str] = None

    # type
    value: Optional[str] = None
    type_delay: int = 50

    # scroll
    direction: Optional[str] = None  # "up" | "down"
    amount: Optional[int] = None

    # wait
    duration: Optional[int] = None  # ms

    # common
    wait_after: int = 500  # ms pause after action

    @model_validator(mode="after")
    def validate_action_fields(self):
        a = self.action
        if a == ActionType.NAVIGATE and not self.url:
            raise ValueError(f"Step {self.id}: 'navigate' requires 'url'")
        if a == ActionType.CLICK and not self.selector:
            raise ValueError(f"Step {self.id}: 'click' requires 'selector'")
        if a == ActionType.TYPE:
            if not self.selector:
                raise ValueError(f"Step {self.id}: 'type' requires 'selector'")
            if self.value is None:
                raise ValueError(f"Step {self.id}: 'type' requires 'value'")
        if a == ActionType.SCROLL and not self.selector and not self.direction:
            raise ValueError(
                f"Step {self.id}: 'scroll' requires 'selector' or 'direction'+'amount'"
            )
        if a == ActionType.HOVER and not self.selector:
            raise ValueError(f"Step {self.id}: 'hover' requires 'selector'")
        if a == ActionType.SELECT:
            if not self.selector:
                raise ValueError(f"Step {self.id}: 'select' requires 'selector'")
            if self.value is None:
                raise ValueError(f"Step {self.id}: 'select' requires 'value'")
        if a == ActionType.WAIT and not self.duration:
            raise ValueError(f"Step {self.id}: 'wait' requires 'duration'")
        return self


class DemoScript(BaseModel):
    metadata: Metadata = Field(default_factory=Metadata)
    steps: list[Step] = Field(..., min_length=1)
