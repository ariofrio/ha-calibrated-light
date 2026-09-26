"""Measured WiZ curve and control-state invariants."""

import pytest

from custom_components.calibrated_light.model import A23, map_brightness, plan_target


def test_measured_reference_and_independent_room_check():
    assert A23.lux(100, 4001, 173) == pytest.approx(173)
    assert A23.lux(50, 4001, 173) == pytest.approx(77.4, abs=0.5)
    assert A23.lux(10, 4001, 173) > 0
    assert A23.lux(100, 2200, 173) < A23.lux(100, 4001, 173)


def test_inverse_preserves_requested_target_across_cct_clipping():
    requested = 120
    warm = plan_target(A23, requested, 2200, 173)
    assert warm.requested_lux == requested
    assert warm.estimated_lux == pytest.approx(A23.lux(100, 2200, 173))
    assert warm.clipped == "above_maximum"
    middle = plan_target(A23, requested, 4001, 173)
    assert middle.requested_lux == requested
    assert middle.estimated_lux == pytest.approx(requested, abs=1.5)
    assert middle.clipped is None


def test_brightness_maps_across_achievable_on_range():
    assert map_brightness(A23, 1, 4001, 173) == pytest.approx(A23.lux(10, 4001, 173))
    assert map_brightness(A23, 255, 4001, 173) == pytest.approx(173)
    assert map_brightness(A23, 128, 2200, 173) < map_brightness(A23, 128, 4001, 173)


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_rejects_invalid_target(value):
    with pytest.raises(ValueError):
        plan_target(A23, value, 4000, 173)
