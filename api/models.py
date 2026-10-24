"""Response models for the Unghosted REST API.

These are the only new wire types the API adds on top of the ``core.contracts``
models, which are returned unchanged. ``Envelope`` wraps a contract payload with
the shared legal text for the findings and nearby-docks routes (R8.8); every
error route uses :class:`ErrorBody`.

Defaults for the legal strings come from ``app.settings`` so the app, API and
MCP server share a single source for the Attribution and Disclaimer text.
"""
from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.settings import ATTRIBUTION, DISCLAIMER

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """Legal-text wrapper for findings and nearby-docks responses.

    Shape: ``{"data": T, "attribution": [ATTRIBUTION], "disclaimer": DISCLAIMER}``.
    ``data`` holds an unchanged contract model (or list of models); the
    attribution list is non-empty and the disclaimer carries the exact Glossary
    text (R8.8).
    """

    data: T
    attribution: list[str] = Field(default_factory=lambda: [ATTRIBUTION])
    disclaimer: str = DISCLAIMER


class ErrorBody(BaseModel):
    """JSON body for every API error.

    ``error`` is the machine code (``validation_error``, ``not_found``,
    ``live_unavailable``, ``internal_error``); ``message`` is human-readable and
    never contains a stack trace, file path or raw exception text. ``params`` is
    present only on 422 responses, where it names each offending parameter.
    """

    error: str
    message: str
    params: list[str] | None = None
