import pytest

def test_axisadapter_import():
    try:
        from axisadapter.axisadapter import AxisAdapter
    except ImportError as e:
        pytest.fail(f"Failed to import AxisAdapter: {e}")

    assert AxisAdapter is not None, "AxisAdapter should be imported successfully"