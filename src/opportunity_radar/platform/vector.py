"""pgvector's `vector(N)` as a SQLAlchemy type, without the `pgvector` package.

The extension's text form is `[x,y,...]`, in both directions, so a small user-defined type
covers everything the radar needs. Two choices matter more than the conversion itself:

* Every bound value goes through an explicit `CAST(... AS vector(N))`. Left to itself, the
  driver would send the text as `varchar` or `unknown` and let the server guess; with the
  cast, the server parses exactly one type, and a vector of the wrong size fails there too.
* A wrong length or a non-finite value is refused here, with `ValueError`, before a
  statement is built. A NaN that reached the index would poison every distance computed
  against it without any error.
"""

from __future__ import annotations

import math
import typing
from collections.abc import Callable, Sequence
from typing import Any

from sqlalchemy import Float, cast
from sqlalchemy.engine import Dialect
from sqlalchemy.sql.elements import BindParameter, ColumnElement
from sqlalchemy.sql.operators import ColumnOperators
from sqlalchemy.types import UserDefinedType


class Vector(UserDefinedType[list[float]]):
    """A fixed-size pgvector column; values are plain lists of floats."""

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("a vector needs at least one dimension")
        self.dimensions = dimensions

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dimensions})"

    @property
    def python_type(self) -> type[Any]:
        return list

    def bind_processor(self, dialect: Dialect) -> Callable[[list[float] | None], str | None]:
        def process(value: list[float] | None) -> str | None:
            return None if value is None else to_text(value, self.dimensions)

        return process

    def bind_expression(
        self, bindvalue: BindParameter[list[float]]
    ) -> ColumnElement[list[float]]:
        return cast(bindvalue, self)

    def result_processor(
        self, dialect: Dialect, coltype: object
    ) -> Callable[[Any], list[float] | None]:
        def process(value: Any) -> list[float] | None:
            return None if value is None else from_text(value)

        return process


def to_text(values: Sequence[float], dimensions: int) -> str:
    """The pgvector literal for `values`, or `ValueError` when it could not be stored."""
    if len(values) != dimensions:
        raise ValueError(f"expected {dimensions} dimensions, got {len(values)}")
    parts: list[str] = []
    for value in values:
        # `bool` is an `int`, and a vector of flags is always a caller's mistake.
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError(f"vector components must be numbers, got {type(value).__name__}")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("vector components must be finite")
        parts.append(repr(number))
    return "[" + ",".join(parts) + "]"


def from_text(value: Any) -> list[float]:
    """Read what the server returns: the text form, or a list if a driver adapter parsed it."""
    if isinstance(value, str):
        body = value.strip().removeprefix("[").removesuffix("]")
        return [float(part) for part in body.split(",")] if body else []
    return [float(part) for part in value]


def cosine_distance(vector: ColumnOperators, other: Any) -> ColumnElement[float]:
    """pgvector's `<=>`: 0 for the same direction, 2 for opposite ones.

    The HNSW index is built with `vector_cosine_ops`, so this is the operator it serves.
    """
    return typing.cast(
        ColumnElement[float], vector.op("<=>", return_type=Float())(other)
    )


__all__ = ["Vector", "cosine_distance", "from_text", "to_text"]
