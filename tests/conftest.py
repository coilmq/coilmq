from __future__ import annotations

from typing import Generator

import pytest

import coilmq.util.codec


@pytest.fixture(scope="session", autouse=True)
def register() -> Generator[None, None, None]:
    """Ensure the custom codecs are registered before a test uses one."""
    with coilmq.util.codec.register():
        yield
