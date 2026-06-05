"""
Pytest fixtures shared across the test suite.

Redirects any module-level output directories to a per-session tmp path so
tests can never accidentally clobber the production CSVs / JSON under
data/outputs/. Historically `test_render_with_mock_files` invoked
`render_differentiators`, which writes through to `data/outputs/` and seeded
the production `commercial_levers_latest.csv` with `John Smith` / `Jane Doe`
fixtures. Patching the constants up-front eliminates that class of bug for
every existing and future test.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_module_output_dirs(tmp_path_factory, monkeypatch) -> Path:
    """Redirect known module-level OUTPUTS_DIR constants to a session tmp dir."""
    tmp_outputs = tmp_path_factory.mktemp('outputs')

    # Imports are inside the fixture so test discovery doesn't fail if a
    # particular module is missing or renamed.
    try:
        from src import analysis_differentiators
        monkeypatch.setattr(analysis_differentiators, 'OUTPUTS_DIR', tmp_outputs)
    except ImportError:
        pass

    try:
        from src import reader_advantages
        if hasattr(reader_advantages, 'OUTPUTS_DIR'):
            monkeypatch.setattr(reader_advantages, 'OUTPUTS_DIR', tmp_outputs)
    except ImportError:
        pass

    return tmp_outputs
