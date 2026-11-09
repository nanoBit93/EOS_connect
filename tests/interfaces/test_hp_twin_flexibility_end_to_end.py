"""Real HTTP payload from hp-twin -> EOS Flask API -> local MILP -> placement adapter."""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from flask import Flask

pytest.importorskip("pulp")
pytest.importorskip("hp_twin")

from hp_twin.adapters.eos_connect import (  # noqa: E402
    EosContingent,
    planned_windows_from_status,
)
from hp_twin.domain.sg_plan import SgCandidate  # noqa: E402
from src.interfaces.optimization_interface import OptimizationInterface  # noqa: E402
from src.loads import api as loads_api  # noqa: E402
from src.loads.manager import ManagedLoadManager, ManagedLoadSources  # noqa: E402

BERLIN = ZoneInfo("Europe/Berlin")
NOW = datetime(2026, 6, 1, 10, 30, tzinfo=BERLIN)
SLOTS = 192


def _request(prices):
    return {
        "ems": {
            "pv_prognose_wh": [0.0] * SLOTS,
            "strompreis_euro_pro_wh": prices,
            "einspeiseverguetung_euro_pro_wh": [0.00008] * SLOTS,
            "gesamtlast": [100.0] * SLOTS,
            "preis_euro_pro_wh_akku": 0.00010,
        },
        "pv_akku": {
            "device_id": "battery1", "capacity_wh": 10000,
            "charging_efficiency": 0.95, "discharging_efficiency": 0.95,
            "max_charge_power_w": 5000, "initial_soc_percentage": 50,
            "min_soc_percentage": 5, "max_soc_percentage": 100,
        },
        "eauto": None, "dishwasher": None, "temperature_forecast": None,
        "start_solution": None,
    }


class _At(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)


def test_hp_twin_contingent_reaches_real_milp_and_returns_aligned_blocks():
    prices = [0.00045] * SLOTS
    for slot in range(48, 52):
        prices[slot] = 0.00010
    manager = ManagedLoadManager(
        [{
            "id": "sg3_req", "type": "external_contingent", "enabled": True,
            "rated_power_w": 4000, "min_runtime_minutes": 0,
        }],
        time_frame_base=900, time_zone=BERLIN,
        sources=ManagedLoadSources(
            price=lambda: prices,
            feed_in_price=lambda: [0.00008] * SLOTS,
            pv_forecast=lambda: [0.0] * SLOTS,
            base_load=lambda: [100.0] * SLOTS,
        ),
        clock=lambda: NOW,
    )
    interface = OptimizationInterface(
        config={"source": "local_evopt", "timeout": 60},
        time_frame_base=900, timezone=BERLIN,
    )
    manager.external_scheduler = interface.schedules_managed_loads
    loads_api.init_api(manager)
    app = Flask(__name__)
    app.register_blueprint(loads_api.loads_bp)
    app.config["TESTING"] = True
    feasible = [False] * 6 + [True] * 4 + [False] * 182
    contingent = EosContingent(
        3200, 2.5, feasible=feasible, value_eur_per_kwh=10.0,
        max_power_w=3600, start="2026-06-01T10:30:00+02:00", ttl_minutes=60,
    )
    try:
        with app.test_client() as client:
            pushed = client.post(
                "/api/managed_loads/sg3_req/push", json=contingent.to_payload()
            )
            assert pushed.status_code == 200, pushed.get_json()
            manager.run_cycle()
            records = manager.schedulable()
            assert records[0]["deadline_slot"] == 51
            assert records[0]["value_eur_per_wh"] == pytest.approx(0.010)
            assert records[0]["min_runtime_slots"] == 1, records[0]
            assert records[0]["committed_on_slots"] == 0, records[0]
            assert records[0]["committed_off_slots"] == 0, records[0]

            with patch(
                "src.interfaces.optimization_backends.optimization_backend_evopt.datetime",
                _At,
            ):
                response, _ = interface.optimize(
                    _request(prices), managed_loads=records
                )
                assert sum(response["managed_loads"]["sg3_req"]) > 0
                solver_configs = interface.backend._managed_load_configs(records)
                time_params = interface.backend._calculate_time_parameters()
            manager.adopt_schedules(response["managed_loads"])
            status = client.get("/api/managed_loads/sg3_req").get_json()
            assert sum(records[0]["feasible"]) == 4
            assert [i for i, allowed in enumerate(records[0]["feasible"]) if allowed] == [
                48, 49, 50, 51
            ]
            assert solver_configs[0].feasible[:10] == [
                False, False, False, False, False, False, True, True, True, True
            ], {
                "time_params": time_params,
                "allowed": [i for i, allowed in enumerate(solver_configs[0].feasible) if allowed],
                "deadline": solver_configs[0].deadline_slot,
            }
            assert solver_configs[0].deadline_slot == 9
    finally:
        loads_api.init_api(None)

    assert status["plan_anchor"] == "2026-06-01T00:00:00+02:00"
    assert status["time_frame_base"] == 900
    assert status["planned_wh"] > 0
    assert sum(status["plan"][:48]) == 0
    assert sum(status["plan"][52:]) == 0
    windows = planned_windows_from_status(
        status, pd.Timestamp("2026-06-01T10:30:00+02:00"), 48 * 3600
    )
    assert windows
    assert all(0 <= start < end <= 4 * 3600 for start, end in windows)


def test_hp_twin_two_hour_sg3_offer_returns_one_uninterrupted_block():
    """The twin's window survives the real HTTP/manager/MILP/response path."""
    prices = [0.00045] * SLOTS
    for slot in range(48, 56):
        prices[slot] = 0.00010
    manager = ManagedLoadManager(
        [{
            "id": "sg3_req", "type": "external_contingent", "enabled": True,
            "rated_power_w": 4000, "min_runtime_minutes": 0,
        }],
        time_frame_base=900, time_zone=BERLIN,
        sources=ManagedLoadSources(
            price=lambda: prices,
            feed_in_price=lambda: [0.00008] * SLOTS,
            pv_forecast=lambda: [0.0] * SLOTS,
            base_load=lambda: [100.0] * SLOTS,
        ),
        clock=lambda: NOW,
    )
    interface = OptimizationInterface(
        config={"source": "local_evopt", "timeout": 60},
        time_frame_base=900, timezone=BERLIN,
    )
    manager.external_scheduler = interface.schedules_managed_loads
    loads_api.init_api(manager)
    app = Flask(__name__)
    app.register_blueprint(loads_api.loads_bp)
    app.config["TESTING"] = True
    feasible = [False] * 2 + [True] * 10 + [False] * 180
    candidate = SgCandidate(
        start_s=1800.0, end_s=9000.0, energy_wh=3200.0,
        max_power_w=3600.0, reason="two-hour window",
    )
    contingent = EosContingent(
        candidate.energy_wh, candidate.deadline_hours(),
        feasible=feasible, value_eur_per_kwh=10.0,
        max_power_w=candidate.max_power_w,
        start="2026-06-01T10:30:00+02:00",
        deadline="2026-06-01T13:00:00+02:00", ttl_minutes=60,
        min_runtime_slots=8, contiguous=True,
    )
    try:
        with app.test_client() as client:
            pushed = client.post(
                "/api/managed_loads/sg3_req/push", json=contingent.to_payload()
            )
            assert pushed.status_code == 200, pushed.get_json()
            manager.run_cycle()
            records = manager.schedulable()
            with patch(
                "src.interfaces.optimization_backends.optimization_backend_evopt.datetime",
                _At,
            ):
                solver_configs = interface.backend._managed_load_configs(records)
                response, _ = interface.optimize(
                    _request(prices), managed_loads=records
                )
            manager.adopt_schedules(response["managed_loads"])
            status = client.get("/api/managed_loads/sg3_req").get_json()
    finally:
        loads_api.init_api(None)

    plan = status["plan"]
    occupied = [slot for slot, energy in enumerate(plan) if energy > 1.0]
    assert len(occupied) == 8
    assert occupied == list(range(occupied[0], occupied[0] + 8))
    assert sum(plan) == pytest.approx(3200.0)
    assert all(energy > 1.0 for energy in plan[occupied[0]:occupied[-1] + 1])
    windows = planned_windows_from_status(
        status, pd.Timestamp("2026-06-01T10:30:00+02:00"), 48 * 3600
    )
    assert len(windows) == 1
    assert windows[0][1] - windows[0][0] == pytest.approx(2 * 3600)
