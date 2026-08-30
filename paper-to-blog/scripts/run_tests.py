#!/usr/bin/env python3
"""Run the paper-to-blog skill's deterministic test suite."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main() -> int:
    skill_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(skill_root / "scripts"))
    suite = unittest.defaultTestLoader.discover(str(skill_root / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
