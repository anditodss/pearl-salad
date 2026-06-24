"""
utils/helpers.py
=================
Shared utility functions.
"""
from __future__ import annotations

import re
import datetime
from typing import Optional


def extract_hashrate(log_text: str, pattern: str) -> Optional[float]:
    """
    Extract the LAST hashrate value found in log_text using the given regex.
    The regex must contain a capture group for the numeric value.

    Returns None if no match is found or the value cannot be parsed.
    """
    matches = re.findall(pattern, log_text)
    if not matches:
        return None
    try:
        # Take the last occurrence (most recent log line)
        return float(matches[-1])
    except (ValueError, TypeError):
        return None


def format_efficiency(value: Optional[float]) -> str:
    """Format an efficiency ratio (0–1) as a percentage string."""
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%"


def format_hashrate(value: Optional[float], unit: str = "H/s") -> str:
    """Format a hashrate number with unit."""
    if value is None:
        return "N/A"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} M{unit}"
    if value >= 1_000:
        return f"{value / 1_000:.2f} K{unit}"
    return f"{value:.2f} {unit}"


def utcnow() -> datetime.datetime:
    """Return timezone-naive UTC datetime."""
    return datetime.datetime.utcnow()


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide safely, returning default when denominator is zero."""
    if denominator == 0:
        return default
    return numerator / denominator


def instance_status(efficiency: Optional[float], threshold: float) -> str:
    """
    Return a status label based on efficiency vs threshold.

    - GOOD    : efficiency >= threshold
    - WARNING : efficiency >= threshold * 0.75 (within 75% of threshold)
    - BAD     : efficiency < threshold * 0.75
    - UNKNOWN : no data
    """
    if efficiency is None:
        return "UNKNOWN"
    if efficiency >= threshold:
        return "GOOD"
    if efficiency >= threshold * 0.75:
        return "WARNING"
    return "BAD"


def get_gpu_cost_per_hour(gpu_type: Optional[str]) -> float:
    """Return the cost per hour for a given GPU type."""
    if not gpu_type:
        return 0.0
    
    lower_gpu = gpu_type.lower()
    if "4070 ti super" in lower_gpu:
        return 0.09
    elif "4070 ti" in lower_gpu:
        return 0.08
    elif "4070 super" in lower_gpu:
        return 0.07
    elif "4070" in lower_gpu:
        return 0.07
    elif "3080" in lower_gpu:
        return 0.06
        
    return 0.0
