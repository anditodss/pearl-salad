"""
tests/test_hashrate_parser.py
==============================
Unit tests for utils/hashrate_parser.py

Run with:
    python -m pytest tests/test_hashrate_parser.py -v
"""
from __future__ import annotations

import unittest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils.hashrate_parser import HashrateParser, ParsedMetrics


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: patch get_config() so tests run without a real config.json
# ─────────────────────────────────────────────────────────────────────────────

def _make_parser(**kwargs) -> HashrateParser:
    """Create a HashrateParser without needing config.json on disk."""
    with patch("utils.hashrate_parser.get_config") as mock_cfg:
        mock_cfg.return_value.hashrate.regex_pattern = ""  # empty → falls through to DEFAULT
        return HashrateParser(**kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Test Suite
# ─────────────────────────────────────────────────────────────────────────────

class TestHashrateParser(unittest.TestCase):

    # ── vLLM GPU progress log format (Salad instance actual logs) ──────────────

    def test_vllm_full_log_line(self):
        """Parse the exact vLLM GPU log line seen in Salad instance logs."""
        log = (
            'ts=2026-06-24T06:02:17.780 level=INFO component=vllm.gpu event=large.progress '
            'rounds_per_sec=52.17 throughput_mhps=41.03 proof_per_sec="86.05 T/s" '
            'devices="[RTX 3090: 86.05T/s]" eta=3305s'
        )
        parser = _make_parser()
        result = parser.parse(log)

        self.assertIsNotNone(result, "Should parse vLLM GPU progress log")
        self.assertAlmostEqual(result.hashrate, 86.05, places=2)
        self.assertEqual(result.unit, "T/s")
        self.assertAlmostEqual(result.hashrate_ths, 86.05, places=2)  # T/s = TH/s
        self.assertEqual(result.gpu_type, "RTX 3090")

    def test_vllm_efficiency_against_benchmark(self):
        """RTX 3090 at 86.05 T/s should be 82.6% efficient (below 85% threshold)."""
        from utils.benchmarks import get_benchmark
        log = (
            'ts=... proof_per_sec="86.05 T/s" devices="[RTX 3090: 86.05T/s]"'
        )
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)

        benchmark = get_benchmark("RTX 3090")   # 104.22 TH/s
        self.assertIsNotNone(benchmark)
        efficiency = result.hashrate_ths / benchmark
        self.assertAlmostEqual(efficiency, 86.05 / 104.22, places=3)
        self.assertLess(efficiency, 0.85, "Should be below 85% threshold")

    def test_vllm_proof_per_sec_only(self):
        """proof_per_sec without devices field still extracts hashrate."""
        log = 'rounds_per_sec=52.19 throughput_mhps=41.05 proof_per_sec="86.0 T/s"'
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 86.0)
        self.assertEqual(result.unit, "T/s")
        self.assertIsNone(result.gpu_type)  # no devices field

    def test_vllm_extract_latest_hashrate_returns_ths(self):
        """extract_latest_hashrate returns TH/s-normalised value."""
        log = (
            'proof_per_sec="84.2 T/s" ...\n'
            'proof_per_sec="86.05 T/s" devices="[RTX 3090: 86.05T/s]"'
        )
        parser = _make_parser()
        value = parser.extract_latest_hashrate(log)
        self.assertAlmostEqual(value, 86.05, places=2)

    def test_vllm_multiple_gpu_devices(self):
        """Extracts GPU name from devices field with multiple devices."""
        log = 'proof_per_sec="172.1 T/s" devices="[RTX 3090: 86.05T/s, RTX 3090: 86.05T/s]"'
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 172.1)
        # First GPU name extracted
        self.assertEqual(result.gpu_type, "RTX 3090")

    # ── Multi-line miner log (canonical example from prompt) ─────────────────

    def test_canonical_multiline_log(self):
        """Parser should extract all three fields from the canonical miner log."""
        log = (
            "Worker: abc123\n"
            "GPU: RTX3080\n"
            "Hashrate: 92.5 T"
        )
        parser = _make_parser()
        result = parser.parse(log)

        self.assertIsNotNone(result)
        self.assertIsInstance(result, ParsedMetrics)
        self.assertEqual(result.machine_id, "abc123")
        self.assertEqual(result.gpu_type, "RTX3080")
        self.assertAlmostEqual(result.hashrate, 92.5)
        self.assertEqual(result.unit, "T")

    # ── Hashrate only ────────────────────────────────────────────────────────

    def test_hashrate_only(self):
        """Parser returns metrics when only hashrate is present (worker/GPU may be None)."""
        log = "Hash rate: 500 GH/s"
        parser = _make_parser()
        result = parser.parse(log)

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 500.0)
        self.assertEqual(result.unit, "GH/s")
        self.assertIsNone(result.machine_id)
        self.assertIsNone(result.gpu_type)

    def test_hashrate_mhs_unit(self):
        log = "hashrate: 1.23 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 1.23)

    def test_hashrate_plain_hs(self):
        log = "Speed: 92.5 H/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 92.5)

    def test_hashrate_integer(self):
        log = "Hashrate: 100 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 100.0)

    def test_hashrate_with_equals_separator(self):
        log = "hashrate=500.0 TH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 500.0)

    # ── No hashrate ──────────────────────────────────────────────────────────

    def test_no_hashrate_returns_none(self):
        log = "Worker: node-001\nGPU: A100\nStatus: OK"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        parser = _make_parser()
        self.assertIsNone(parser.parse(""))
        self.assertIsNone(parser.parse("   "))
        self.assertIsNone(parser.parse(None))  # type: ignore

    # ── Worker/machine extraction ─────────────────────────────────────────────

    def test_worker_with_colon(self):
        log = "Worker: node-xyz\nHashrate: 10 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertEqual(result.machine_id, "node-xyz")

    def test_worker_with_equals(self):
        log = "worker=miner-01\nHashrate: 10 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertEqual(result.machine_id, "miner-01")

    # ── GPU extraction ────────────────────────────────────────────────────────

    def test_gpu_extracted(self):
        log = "GPU: RTX 3090\nHashrate: 120 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertEqual(result.gpu_type, "RTX 3090")

    def test_device_field_mapped_to_gpu(self):
        log = "Device: GTX 1080 Ti\nHashrate: 50 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertEqual(result.gpu_type, "GTX 1080 Ti")

    def test_gpu_type_field(self):
        log = "gpu_type: A100\nHashrate: 500 MH/s"
        parser = _make_parser()
        result = parser.parse(log)
        self.assertEqual(result.gpu_type, "A100")

    # ── parse_many ────────────────────────────────────────────────────────────

    def test_parse_many_filters_no_hashrate(self):
        lines = [
            "Status: OK",
            "Hashrate: 100 MH/s",
            "Connected",
            "Worker: abc\nHashrate: 200 MH/s",
        ]
        parser = _make_parser()
        results = parser.parse_many(lines)
        self.assertEqual(len(results), 2)
        self.assertAlmostEqual(results[0].hashrate, 100.0)
        self.assertAlmostEqual(results[1].hashrate, 200.0)

    def test_parse_many_empty_list(self):
        parser = _make_parser()
        self.assertEqual(parser.parse_many([]), [])

    # ── extract_latest_hashrate ───────────────────────────────────────────────

    def test_extract_latest_from_multi_occurrence(self):
        log = (
            "Hashrate: 80.0 MH/s\n"
            "Hashrate: 85.0 MH/s\n"
            "Hashrate: 90.0 MH/s"
        )
        parser = _make_parser()
        value = parser.extract_latest_hashrate(log)
        self.assertAlmostEqual(value, 90.0)

    def test_extract_latest_none_when_no_match(self):
        parser = _make_parser()
        self.assertIsNone(parser.extract_latest_hashrate("No data here"))

    # ── Custom pattern ────────────────────────────────────────────────────────

    def test_custom_hashrate_pattern(self):
        """User can provide a custom regex via config override."""
        # Custom pattern: "speed 10.5mhs" style
        custom_pattern = r"speed\s+([\d.]+)\s*mhs"
        parser = _make_parser(hashrate_pattern=custom_pattern)
        log = "speed 10.5mhs"
        result = parser.parse(log)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.hashrate, 10.5)

    def test_custom_worker_pattern(self):
        custom_worker = r"node_id=([^\s]+)"
        parser = _make_parser(worker_pattern=custom_worker)
        log = "node_id=gpu-42\nHashrate: 50 MH/s"
        result = parser.parse(log)
        self.assertEqual(result.machine_id, "gpu-42")

    # ── to_dict ───────────────────────────────────────────────────────────────

    def test_to_dict_output(self):
        log = "Worker: abc123\nGPU: RTX3080\nHashrate: 92.5 T"
        parser = _make_parser()
        result = parser.parse(log)
        d = result.to_dict()
        self.assertIn("machine_id", d)
        self.assertIn("gpu_type", d)
        self.assertIn("hashrate", d)
        self.assertIn("unit", d)
        self.assertEqual(d["machine_id"], "abc123")
        self.assertEqual(d["gpu_type"], "RTX3080")
        self.assertAlmostEqual(d["hashrate"], 92.5)

    # ── Case insensitivity ────────────────────────────────────────────────────

    def test_case_insensitive_hashrate_keyword(self):
        for keyword in ["Hashrate", "HASHRATE", "hashrate", "Hash rate", "HASH RATE"]:
            log = f"{keyword}: 50 MH/s"
            parser = _make_parser()
            result = parser.parse(log)
            self.assertIsNotNone(result, msg=f"Failed for keyword: {keyword}")
            self.assertAlmostEqual(result.hashrate, 50.0)


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
