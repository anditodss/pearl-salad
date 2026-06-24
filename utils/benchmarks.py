"""
utils/benchmarks.py
====================
Static GPU benchmark hashrate table.

Expected hashrates are in TH/s (terahashes per second) on the Pearl Fortune
pool. Used as the denominator when computing per-instance efficiency so that
every instance is judged against a fixed, well-known expectation for its GPU
model rather than the floating peer-median.

Efficiency formula:
    efficiency = actual_hashrate / benchmark_hashrate

Where actual_hashrate is the latest parsed value from Salad container logs
(in the same unit as benchmark — TH/s).

Usage:
    from utils.benchmarks import get_benchmark, GPU_BENCHMARKS

    expected = get_benchmark("RTX 4070 SUPER")  # → 111.19
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Benchmark table  (unit: TH/s — terahashes per second on Pearl Fortune pool)
# ---------------------------------------------------------------------------
GPU_BENCHMARKS: dict[str, float] = {
    # Ada Lovelace (RTX 50xx)
    "RTX 5090":             322.45,
    "RTX 5080":             161.26,
    "RTX 5070 Ti":          146.19,
    "RTX 5070":             103.02,
    "RTX 5060 Ti":           77.32,
    "RTX 5060":              64.61,

    # Ada Lovelace (RTX 40xx)
    "RTX 4090":             265.81,
    "RTX 4090 D":           239.61,
    "RTX 4070 Ti SUPER":    154.44,
    "RTX 4070 Ti":          121.61,
    "RTX 4070 SUPER":       111.19,
    "RTX 4070":             104.38,
    "RTX 4060 Ti":           67.78,

    # Ampere (RTX 30xx)
    "RTX 3090":             104.22,
    "RTX 3080 Ti":          103.70,
    "RTX 3080":              93.01,
    "RTX 3070":              46.92,
    "RTX 3060 Ti":           40.12,
    "RTX 3060":              35.82,

    # Professional / Data-centre
    "A100-PCIE-40GB":       191.83,
    "A100-SXM4-80GB":       221.56,
    "NVIDIA L40S":           218.83,
}

# ---------------------------------------------------------------------------
# Fuzzy-match aliases — common display-name variations returned by Salad API
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    # Full NVIDIA branding
    "NVIDIA GeForce RTX 5090":             "RTX 5090",
    "NVIDIA GeForce RTX 5080":             "RTX 5080",
    "NVIDIA GeForce RTX 5070 Ti":          "RTX 5070 Ti",
    "NVIDIA GeForce RTX 5070":             "RTX 5070",
    "NVIDIA GeForce RTX 5060 Ti":          "RTX 5060 Ti",
    "NVIDIA GeForce RTX 5060":             "RTX 5060",
    "NVIDIA GeForce RTX 4090":             "RTX 4090",
    "NVIDIA GeForce RTX 4070 Ti SUPER":    "RTX 4070 Ti SUPER",
    "NVIDIA GeForce RTX 4070 Ti":          "RTX 4070 Ti",
    "NVIDIA GeForce RTX 4070 SUPER":       "RTX 4070 SUPER",
    "NVIDIA GeForce RTX 4070":             "RTX 4070",
    "NVIDIA GeForce RTX 4060 Ti":          "RTX 4060 Ti",
    "NVIDIA GeForce RTX 3090":             "RTX 3090",
    "NVIDIA GeForce RTX 3080 Ti":          "RTX 3080 Ti",
    "NVIDIA GeForce RTX 3080":             "RTX 3080",
    "NVIDIA GeForce RTX 3070":             "RTX 3070",
    "NVIDIA GeForce RTX 3060 Ti":          "RTX 3060 Ti",
    "NVIDIA GeForce RTX 3060":             "RTX 3060",
    # Short lowercase variants
    "rtx 5090": "RTX 5090",
    "rtx 4090": "RTX 4090",
    "rtx 4070 ti super": "RTX 4070 Ti SUPER",
    "rtx 4070 ti": "RTX 4070 Ti",
    "rtx 4070 super": "RTX 4070 SUPER",
    "rtx 4070": "RTX 4070",
    "rtx 4060 ti": "RTX 4060 Ti",
    "rtx 3090": "RTX 3090",
    "rtx 3080 ti": "RTX 3080 Ti",
    "rtx 3080": "RTX 3080",
    "rtx 3070": "RTX 3070",
    "rtx 3060 ti": "RTX 3060 Ti",
    "rtx 3060": "RTX 3060",
    # Data-centre abbreviations
    "a100": "A100-PCIE-40GB",
    "a100-pcie": "A100-PCIE-40GB",
    "a100-sxm": "A100-SXM4-80GB",
    "l40s": "NVIDIA L40S",
}


def _normalise(gpu_name: str) -> str:
    """
    Normalise a GPU name string for lookup.

    1. Try exact match first.
    2. Try alias table (case-insensitive).
    3. Try substring match against known benchmark keys.
    """
    # Exact match
    if gpu_name in GPU_BENCHMARKS:
        return gpu_name

    # Alias table
    canonical = _ALIASES.get(gpu_name) or _ALIASES.get(gpu_name.lower())
    if canonical and canonical in GPU_BENCHMARKS:
        return canonical

    # Substring match — find longest matching key
    lower = gpu_name.lower()
    best: Optional[str] = None
    best_len = 0
    for key in GPU_BENCHMARKS:
        if key.lower() in lower and len(key) > best_len:
            best = key
            best_len = len(key)

    if best:
        return best

    return gpu_name  # unchanged — caller will get None from get_benchmark()


def get_benchmark(gpu_type: Optional[str]) -> Optional[float]:
    """
    Return the expected hashrate (TH/s) for *gpu_type*, or None if unknown.

    Args:
        gpu_type: GPU model string as returned by Salad API
                  (e.g. "RTX 4070 SUPER", "NVIDIA GeForce RTX 3090").

    Returns:
        Expected hashrate as a float, or None if the GPU is not in the table.
    """
    if not gpu_type:
        return None
    normalised = _normalise(gpu_type.strip())
    result = GPU_BENCHMARKS.get(normalised)
    if result is None:
        logger.debug("No benchmark found for GPU type: %r (normalised: %r)", gpu_type, normalised)
    return result
