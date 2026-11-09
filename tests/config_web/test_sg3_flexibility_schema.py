"""The two managed-load types needed by the hp-twin integration stay configurable."""

from src.config_web.schema import ConfigSchema


def test_sg3_flexibility_settings_are_exposed_by_the_config_schema():
    fields = {field.key: field for field in ConfigSchema().all_fields()}
    required = {
        "eos.source",
        "eos.time_frame",
        "managed_loads.id",
        "managed_loads.type",
        "managed_loads.rated_power_w",
        "managed_loads.min_runtime_minutes",
        "managed_loads.max_price_ct_kwh",
        "managed_loads.ttl_minutes",
        "managed_loads.replaces_sensor",
        "managed_loads.subtract_from_base_load",
        "managed_loads.profile_source",
    }
    assert required <= fields.keys()
    assert fields["eos.source"].default == "local_evopt"
    assert fields["eos.time_frame"].validation["choices"] == [900, 3600]
    assert "external_contingent" in fields["managed_loads.type"].validation["choices"]
    assert "external_profile" in fields["managed_loads.type"].validation["choices"]
    assert fields["managed_loads.profile_source"].default == "push"
    for key in required - {"eos.source", "eos.time_frame"}:
        assert fields[key].help_url
