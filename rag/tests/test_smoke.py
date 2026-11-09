import sys

MINIMUM_PYTHON_VERSION = (3, 13)


def test_python_version_is_supported():
    assert sys.version_info >= MINIMUM_PYTHON_VERSION
