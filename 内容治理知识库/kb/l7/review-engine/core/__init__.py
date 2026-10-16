"""Local deterministic review core."""

from .rule_engine import scan_text
from .review_engine import decide

__all__ = ["scan_text", "decide"]
