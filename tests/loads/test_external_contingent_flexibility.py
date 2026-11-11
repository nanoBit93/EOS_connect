"""Externally simulated heat-pump flexibility, from push to the MILP hand-over."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from src.loads.injection import InjectionError, parse_push
from src.loads.manager import ManagedLoadManager, ManagedLoadSources

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 6, 1, 10, 30, tzinfo=BERLIN)


def _manager():
    return ManagedLoadManager(
        [{
            "id": "sg3_req", "type": "external_contingent", "enabled": True,
            "rated_power_w": 2000.0, "max_price_ct_kwh": 25.0,
            "min_runtime_minutes": 30, "ttl_minutes": 60,
        }],
        time_frame_base=900,
        time_zone=BERLIN,
        sources=ManagedLoadSources(
            price=lambda: [0.0004] * 192,
            feed_in_price=lambda: [0.00008] * 192,
            pv_forecast=lambda: [0.0] * 192,
            base_load=lambda: [400.0] * 192,
        ),
        clock=lambda: NOW,
    )


def test_contingent_payload_is_aligned_and_reaches_the_scheduler():
    manager = _manager()
    feasible = [False] * 44 + [True] * 12 + [False] * 136
    manager.push("sg3_req", {
        "total_wh": 3200, "deadline_hours": 4,
        "feasible": feasible, "start": "today", "resolution": "15min",
        "max_power_w": 3600, "value_eur_per_kwh": 250,
    })

    manager.run_cycle()
    record = manager.schedulable()[0]
    assert record["feasible"] == feasible
    assert record["max_power_w"] == 3600
    assert record["value_eur_per_wh"] == pytest.approx(0.25)
    # Slot 57 is the last slot ending at or before the four-hour deadline.
    assert record["deadline_slot"] == 57


def test_a_now_mask_denies_the_past_and_uncovered_slots():
    manager = _manager()
    manager.push("sg3_req", {
        "total_wh": 1000, "feasible": [True] * 4,
        "start": "now", "resolution": "15min",
    })
    manager.run_cycle()
    mask = manager.schedulable()[0]["feasible"]
    assert mask[42:46] == [True] * 4
    assert not any(mask[:42])
    assert not any(mask[46:])


@pytest.mark.parametrize("feasible", [[1, 0], ["true", "false"], [], "yes"])
def test_feasible_requires_real_booleans(feasible):
    with pytest.raises(InjectionError, match="feasible"):
        parse_push(
            {"total_wh": 1000, "feasible": feasible, "resolution": "15min"},
            NOW.replace(hour=0, minute=0), 192, 900, 42, now=NOW,
        )


@pytest.mark.parametrize("payload,fragment", [
    ({"value_eur_per_kwh": -1}, "cannot be negative"),
    ({"value_eur_per_kwh": float("nan")}, "finite"),
    ({"max_power_w": 0}, "must be positive"),
])
def test_invalid_flexibility_numbers_are_rejected(payload, fragment):
    with pytest.raises(InjectionError, match=fragment):
        parse_push(
            {"total_wh": 1000, **payload},
            NOW.replace(hour=0, minute=0), 192, 900, 42, now=NOW,
        )


def test_an_hourly_mask_blocks_the_whole_hour_for_one_blocked_quarter():
    result = parse_push(
        {"total_wh": 1000, "feasible": [True, True, True, False], "resolution": "15min"},
        NOW.replace(hour=0, minute=0), 48, 3600, 10, now=NOW,
    )
    assert result.feasible == [False] * 48


def test_expired_contingent_blocks_a_previously_adopted_release():
    clock = {"now": NOW}
    manager = ManagedLoadManager(
        [{
            "id": "sg3_req", "type": "external_contingent", "enabled": True,
            "rated_power_w": 3600, "min_runtime_minutes": 0, "ttl_minutes": 1,
        }],
        time_frame_base=900, time_zone=BERLIN,
        sources=ManagedLoadSources(price=lambda: [0.0001] * 192),
        clock=lambda: clock["now"],
    )
    manager.push("sg3_req", {"total_wh": 900, "ttl_minutes": 1})
    manager.run_cycle()
    item = manager.instance("sg3_req")
    release = item.adopt_schedule(
        [0.0] * 42 + [900.0] + [0.0] * 149, manager._last_ctx
    )
    assert release is not None and release["released"]

    clock["now"] = NOW + timedelta(minutes=2)
    manager.run_cycle()
    assert item.last_release["released"] is False
    assert not any(item.last_plan)
    assert manager.schedulable() == []
