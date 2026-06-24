"""
utils/hashrate_parser.py
=========================
Configurable regex-based hashrate parser for miner log output.

Designed to be swapped via config.json without code changes.

Supported log formats:
  1. vLLM GPU progress format (primary — from Salad instance logs):
       ts=... proof_per_sec="86.05 T/s" devices="[RTX 3090: 86.05T/s]"
       ts=... throughput_mhps=41.03 proof_per_sec="84.2 T/s"

  2. Generic miner formats (fallback):
       Hashrate: 92.5 T
       hashrate: 1.23 MH/s
       Hash rate: 500 GH/s
       hashrate=500.0 TH/s
       proof_per_sec=86.05

All extracted hashrates are stored as-is (float).
Unit normalization to TH/s is done by utils.unit_converter (used at comparison time).

Usage:
    parser = HashrateParser()
    metrics = parser.parse(raw_log_line)
    if metrics:
        print(metrics.hashrate, metrics.unit, metrics.gpu_type)
"""
from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Pattern

from utils.config import get_config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Output DTO
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ParsedMetrics:
    """
    Structured output from the hashrate parser.

    Attributes:
        machine_id: Worker/machine identifier extracted from log (or None).
        gpu_type:   GPU model string extracted from log (or None).
        hashrate:   Numeric hashrate value extracted (or None).
        unit:       Unit string (e.g., 'T/s', 'MH/s', 'GH/s', 'TH/s', 'H/s').
        hashrate_ths: Hashrate normalised to TH/s for benchmark comparison (or None).
    """
    machine_id: Optional[str]
    gpu_type: Optional[str]
    hashrate: Optional[float]
    unit: Optional[str]
    hashrate_ths: Optional[float] = None   # normalised to TH/s

    def to_dict(self) -> dict:
        return {
            "machine_id": self.machine_id,
            "gpu_type": self.gpu_type,
            "hashrate": self.hashrate,
            "unit": self.unit,
            "hashrate_ths": self.hashrate_ths,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Unit normalisation (→ TH/s)
# ─────────────────────────────────────────────────────────────────────────────

# Multipliers relative to TH/s  (1 TH/s = 1)
_UNIT_MULTIPLIER: dict[str, float] = {
    # sub-tera
    "h/s":   1e-12,
    "kh/s":  1e-9,
    "mh/s":  1e-6,
    "mhps":  1e-6,   # throughput_mhps
    "gh/s":  1e-3,
    "khs":   1e-9,
    "mhs":   1e-6,
    "ghs":   1e-3,
    # tera
    "th/s":  1.0,
    "t/s":   1.0,    # vLLM logs use "T/s" to mean TH/s
    "ths":   1.0,
    "t":     1.0,    # bare "T" suffix (e.g. "92.5 T")
    # peta
    "ph/s":  1e3,
    "phs":   1e3,
    "eh/s":  1e6,
    "ehs":   1e6,
}


def normalise_to_ths(value: float, unit: Optional[str]) -> Optional[float]:
    """
    Convert *value* (in *unit*) to TH/s.
    Returns None if the unit is unknown.
    """
    if unit is None:
        return None
    key = unit.lower().strip()
    multiplier = _UNIT_MULTIPLIER.get(key)
    if multiplier is None:
        logger.debug("Unknown hashrate unit %r — cannot normalise to TH/s", unit)
        return None
    return value * multiplier


# ─────────────────────────────────────────────────────────────────────────────
# Patterns
# ─────────────────────────────────────────────────────────────────────────────

# ── PRIMARY: vLLM GPU progress log format ────────────────────────────────────
# Matches: proof_per_sec="86.05 T/s"
# Handles both quoted and unquoted values.
VLLM_PROOF_PER_SEC_PATTERN = re.compile(
    r"""proof_per_sec=["']?\s*([\d]+(?:\.[\d]+)?)\s*([A-Za-z/]+)["']?""",
    re.IGNORECASE,
)

# Matches: devices="[RTX 3090: 86.05T/s]"
# Captures GPU name(s) and hashrate from the bracketed device list.
# Format: "[ GPU_NAME : VALUE UNIT, GPU_NAME2 : VALUE2 UNIT2 ]"
VLLM_DEVICES_PATTERN = re.compile(
    r"""devices=["']\[([^\]]+)\]["']""",
    re.IGNORECASE,
)

# Extract individual device entries from the devices string:  "RTX 3090: 86.05T/s"
VLLM_DEVICE_ENTRY_PATTERN = re.compile(
    r"""([A-Za-z0-9 ()]+?):\s*([\d]+(?:\.[\d]+)?)\s*([A-Za-z/]+)""",
)

# ── SECONDARY: Generic miner log formats ─────────────────────────────────────
# Matches:
#   "Hashrate: 92.5 T"            → 92.5, T
#   "hashrate: 1.23 MH/s"         → 1.23, MH/s
#   "Hash rate: 500 GH/s"         → 500.0, GH/s
#   "speed 10.5mhs"               → 10.5, mhs
#   "92.5 H/s"                    → 92.5, H/s
#   "proof_per_sec=86.05"         → 86.05, (no unit)
DEFAULT_HASHRATE_PATTERN = (
    r"(?i)"                                               # case-insensitive
    r"(?:hashrate|hash\s+rate|speed|proof_per_sec)"       # trigger keyword
    r"[\s:=\"\']*?"                                       # optional separators/quotes
    r"([\d]+(?:\.[0-9]+)?)"                              # capture: numeric value
    r"\s*"
    r'([KMGT]?[Hh]/?[sS]|[KMGT]hs|[KMGT][Hh][Ss]|[KMGT]/[sS]|[KMGT])?\"?'  # capture: unit (optional)
)

# Worker pattern
DEFAULT_WORKER_PATTERN = r"(?i)worker[\s:=]+([^\s,]+)"

# GPU pattern — matches: gpu_type:, gpu:, gpu_model:, name:, device: (single GPU label)
DEFAULT_GPU_PATTERN = (
    r"(?i)"
    r"(?:^|\] |\b)"
    r"(?:gpu_model|gpu_type|gpu(?:\(s\))?|device(?!s)|name)"   # 'device' (singular) but NOT 'devices='
    r"\s*[:=]\s*\"?"
    r"([A-Za-z0-9][^\n,\"=]*?)"
    r"(?=\s+\w+=|\s*[,\"\n]|\s*$)"
)


# ─────────────────────────────────────────────────────────────────────────────
# Parser Class
# ─────────────────────────────────────────────────────────────────────────────

class HashrateParser:
    """
    Configurable regex-based parser for miner log output.

    Parsing priority:
      1. vLLM GPU format:  proof_per_sec="VALUE UNIT" devices="[GPU: VALUE UNIT]"
      2. Generic formats:  Hashrate: VALUE UNIT / proof_per_sec=VALUE

    GPU type is extracted from:
      1. devices="[GPU_NAME: ...]" (vLLM format)
      2. GPU: / gpu_type: / gpu_model: fields (generic)

    Example vLLM log:
        ts=2026-06-24T06:02:17.780 level=INFO component=vllm.gpu event=large.progress
        rounds_per_sec=52.17 throughput_mhps=41.03 proof_per_sec="86.05 T/s"
        devices="[RTX 3090: 86.05T/s]" eta=3305s

    Output:
        ParsedMetrics(machine_id=None, gpu_type='RTX 3090', hashrate=86.05,
                      unit='T/s', hashrate_ths=86.05)
    """

    def __init__(
        self,
        hashrate_pattern: Optional[str] = None,
        worker_pattern: Optional[str] = None,
        gpu_pattern: Optional[str] = None,
    ) -> None:
        # Hashrate fallback pattern: prefer explicit arg → config → default
        if hashrate_pattern is not None:
            hr_pat = hashrate_pattern
        else:
            try:
                cfg_pat = get_config().hashrate.regex_pattern
                hr_pat = cfg_pat if cfg_pat else DEFAULT_HASHRATE_PATTERN
            except Exception:
                hr_pat = DEFAULT_HASHRATE_PATTERN

        self._hashrate_re: Pattern = re.compile(hr_pat)
        self._worker_re: Pattern = re.compile(worker_pattern or DEFAULT_WORKER_PATTERN)
        self._gpu_re: Pattern = re.compile(gpu_pattern or DEFAULT_GPU_PATTERN)

        logger.debug("HashrateParser initialised — hashrate_pattern=%r", hr_pat)

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, raw_log: str) -> Optional[ParsedMetrics]:
        """
        Parse a raw log string (one or multiple lines).

        Returns a ParsedMetrics dataclass if at least a hashrate is found,
        otherwise returns None.
        """
        if not raw_log or not raw_log.strip():
            return None

        # ── Try vLLM primary format first ──────────────────────────────────
        result = self._parse_vllm(raw_log)
        if result is not None:
            return result

        # ── Fall back to generic format ────────────────────────────────────
        hashrate, unit = self._extract_hashrate(raw_log)
        machine_id = self._extract_worker(raw_log)
        gpu_type = self._extract_gpu(raw_log)

        # Require at least a hashrate for a non-None result.
        # (Worker or GPU alone without hashrate is not actionable.)
        if hashrate is None:
            return None

        ths = normalise_to_ths(hashrate, unit) if hashrate is not None else None

        return ParsedMetrics(
            machine_id=machine_id,
            gpu_type=gpu_type,
            hashrate=hashrate,
            unit=unit,
            hashrate_ths=ths,
        )

    def parse_many(self, log_lines: List[str]) -> List[ParsedMetrics]:
        """Parse multiple log lines. Returns only lines that contain hashrate data."""
        results: List[ParsedMetrics] = []
        for line in log_lines:
            m = self.parse(line)
            if m is not None:
                results.append(m)
        return results

    def extract_latest_hashrate(self, raw_log: str) -> Optional[float]:
        """
        Extract only the LAST hashrate value (in TH/s) found in the log text.
        Useful when a single log blob contains multiple hashrate readings.
        Returns TH/s-normalised value when unit is known, raw value otherwise.
        """
        # Try vLLM format first — proof_per_sec is the authoritative metric
        matches = VLLM_PROOF_PER_SEC_PATTERN.findall(raw_log)
        if matches:
            last_val, last_unit = matches[-1]
            try:
                value = float(last_val)
                ths = normalise_to_ths(value, last_unit)
                return ths if ths is not None else value
            except (ValueError, TypeError):
                pass

        # Fall back to generic pattern
        all_matches = self._hashrate_re.findall(raw_log)
        if not all_matches:
            return None
        last_match = all_matches[-1]
        value_str = last_match[0] if isinstance(last_match, tuple) else last_match
        try:
            return float(value_str)
        except (ValueError, TypeError):
            return None

    # ── vLLM-specific parsing ─────────────────────────────────────────────────

    def _parse_vllm(self, text: str) -> Optional[ParsedMetrics]:
        """
        Parse the vLLM GPU progress log format:
            proof_per_sec="86.05 T/s" devices="[RTX 3090: 86.05T/s]"

        Returns ParsedMetrics if both proof_per_sec and devices fields are found,
        None if neither is present (so caller falls through to generic parsing).
        """
        # ── proof_per_sec → hashrate ─────────────────────────────────────
        proof_match = VLLM_PROOF_PER_SEC_PATTERN.search(text)
        if proof_match is None:
            return None   # not a vLLM log line

        try:
            hashrate = float(proof_match.group(1))
            unit = proof_match.group(2).strip()
        except (ValueError, IndexError):
            return None

        ths = normalise_to_ths(hashrate, unit)

        # ── devices → GPU name ───────────────────────────────────────────
        gpu_type: Optional[str] = None
        devices_match = VLLM_DEVICES_PATTERN.search(text)
        if devices_match:
            device_str = devices_match.group(1)  # e.g. "RTX 3090: 86.05T/s"
            entry = VLLM_DEVICE_ENTRY_PATTERN.search(device_str)
            if entry:
                gpu_type = entry.group(1).strip()

        # ── worker — not typically in vLLM GPU lines ─────────────────────
        machine_id = self._extract_worker(text)

        return ParsedMetrics(
            machine_id=machine_id,
            gpu_type=gpu_type,
            hashrate=hashrate,
            unit=unit,
            hashrate_ths=ths,
        )

    # ── Private generic helpers ───────────────────────────────────────────────

    def _extract_hashrate(self, text: str) -> tuple[Optional[float], Optional[str]]:
        """Return (value, unit) or (None, None)."""
        match = self._hashrate_re.search(text)
        if not match:
            return None, None
        try:
            groups = match.groups()
            value = float(groups[0])
            unit = groups[1].strip() if len(groups) > 1 and groups[1] else None
            return value, unit
        except (ValueError, TypeError, IndexError):
            return None, None

    def _extract_worker(self, text: str) -> Optional[str]:
        match = self._worker_re.search(text)
        return match.group(1).strip() if match else None

    def _extract_gpu(self, text: str) -> Optional[str]:
        match = self._gpu_re.search(text)
        return match.group(1).strip() if match else None
