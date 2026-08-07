"""Backward-compatible re-exports — use program_description instead."""

from app.services.program_description import DescriptionError, generate_program_description

GeminiError = DescriptionError

__all__ = ["DescriptionError", "GeminiError", "generate_program_description"]
