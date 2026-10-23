"""Layout 7 (rules v2.1) against the stored sample game of tests/fixtures/make_layout7_sample.py."""

import importlib.util
from pathlib import Path

import numpy as np

FIXTURES = Path(__file__).parent / "fixtures"


def _generator():
    spec = importlib.util.spec_from_file_location(
        "make_layout7_sample", FIXTURES / "make_layout7_sample.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_layout7_sample():
    new = _generator().play_sample()
    with np.load(FIXTURES / "layout7" / "sample.npz") as stored:
        assert np.array_equal(new["observations"], stored["observations"])
        assert np.array_equal(new["masks"], stored["masks"])
        assert list(new["vector_names"]) == list(stored["vector_names"])
