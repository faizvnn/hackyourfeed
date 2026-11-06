"""Load fixture JSON into a contract model."""

from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from .config import FIXTURES

T = TypeVar("T", bound=BaseModel)


def load(name: str, model: type[T]) -> T:
    return model.model_validate(json.loads((FIXTURES / f"{name}.json").read_text()))
