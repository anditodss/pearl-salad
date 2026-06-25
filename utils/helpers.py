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


def instance_status(hashrate: Optional[float], cost_per_hour: float) -> str:
    """
    Return a status label based on hashrate vs cost per hour.
    Target hashrate is cost_per_hour * 1000.

    - GOOD    : hashrate >= target
    - WARNING : hashrate >= target * 0.85
    - BAD     : hashrate < target * 0.85
    - UNKNOWN : no data or cost is 0
    """
    if hashrate is None or cost_per_hour <= 0.0:
        return "UNKNOWN"
    
    target = cost_per_hour * 1000.0
    if hashrate >= target:
        return "GOOD"
    if hashrate >= target * 0.85:
        return "WARNING"
    return "BAD"


def get_gpu_cost_per_hour(gpu_type: Optional[str]) -> float:
    """Return the cost per hour for a given GPU type."""
    if not gpu_type:
        return 0.0
    
    lower_gpu = gpu_type.lower()
    
    # RTX 50 Series
    if "5090 laptop" in lower_gpu: return 0.10
    if "5090" in lower_gpu: return 0.25
    if "5080" in lower_gpu: return 0.18
    if "5070 ti" in lower_gpu: return 0.10
    if "5070" in lower_gpu: return 0.08
    if "5060 ti" in lower_gpu: return 0.07
    if "5060" in lower_gpu: return 0.065
    
    # RTX 40 Series
    if "4090" in lower_gpu: return 0.16
    if "4080" in lower_gpu: return 0.11
    if "4070 ti super" in lower_gpu: return 0.09
    if "4070 ti" in lower_gpu: return 0.08
    if "4070 super" in lower_gpu: return 0.07
    if "4070 laptop" in lower_gpu: return 0.05
    if "4070" in lower_gpu: return 0.07
    if "4060 ti" in lower_gpu: return 0.08
    if "4060" in lower_gpu: return 0.05
    
    # RTX 30 Series
    if "3090 ti" in lower_gpu: return 0.10
    if "3090" in lower_gpu: return 0.09
    if "3080 ti" in lower_gpu: return 0.08
    if "3080" in lower_gpu: return 0.06
    if "3070 ti" in lower_gpu: return 0.06
    if "3070" in lower_gpu: return 0.04
    if "3060 ti" in lower_gpu: return 0.03
    if "3060" in lower_gpu: return 0.04
    if "3050" in lower_gpu: return 0.03
    
    # RTX 20 Series
    if "2080 ti" in lower_gpu: return 0.06
    if "2080" in lower_gpu: return 0.05
    if "2070" in lower_gpu: return 0.02
    if "2060" in lower_gpu: return 0.02
    
    # GTX 16/10 Series
    if "1660 super" in lower_gpu: return 0.02
    if "1660" in lower_gpu: return 0.02
    if "1650" in lower_gpu: return 0.015
    if "1080 ti" in lower_gpu or "1080ti" in lower_gpu: return 0.02
    if "1080" in lower_gpu: return 0.02
    if "1070" in lower_gpu: return 0.02
    if "1060" in lower_gpu: return 0.02
    if "1050 ti" in lower_gpu: return 0.015
    
    # Workstation / Others
    if "a5000" in lower_gpu: return 0.09
    if "9070 xt" in lower_gpu: return 0.07
    
    return 0.0
