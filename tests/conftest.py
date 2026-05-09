"""
pytest configuration. Registers custom marks so integration tests can be
skipped cleanly when the relevant API key is absent.

Usage in tests:

    @pytest.mark.needs_lightcone
    def test_real_screenshot():
        ...

Run only unit tests:      pytest tests/unit/
Run only integration:     pytest tests/integration/
Skip missing providers:   pytest -m "not needs_lightcone"
"""

import os
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_lightcone: requires LIGHTCONE_API_KEY")
    config.addinivalue_line("markers", "needs_kernel: requires KERNEL_API_KEY")
    config.addinivalue_line("markers", "needs_anthropic: requires ANTHROPIC_API_KEY")
    config.addinivalue_line("markers", "needs_nvidia: requires NVIDIA_API_KEY")
    config.addinivalue_line("markers", "needs_brev: requires brev CLI + BREV_WORKSPACE")


def pytest_collection_modifyitems(items):
    key_map = {
        "needs_lightcone": "LIGHTCONE_API_KEY",
        "needs_kernel": "KERNEL_API_KEY",
        "needs_anthropic": "ANTHROPIC_API_KEY",
        "needs_nvidia": "NVIDIA_API_KEY",
        "needs_brev": "BREV_WORKSPACE",
    }
    for item in items:
        for mark_name, env_var in key_map.items():
            if item.get_closest_marker(mark_name) and not os.environ.get(env_var):
                item.add_marker(
                    pytest.mark.skip(reason=f"{env_var} not set")
                )
