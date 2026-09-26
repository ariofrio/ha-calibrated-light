"""Configuration, command, state, and persistence behavior in Home Assistant."""

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def setup_proxy(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_OFF,
        {
            "supported_color_modes": ["color_temp"],
            "min_color_temp_kelvin": 2200,
            "max_color_temp_kelvin": 6500,
        },
    )
    entry = MockConfigEntry(
        domain="calibrated_light",
        title="Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow_lists_measured_model_and_source(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_OFF,
        {"supported_color_modes": ["color_temp"]},
    )
    form = await hass.config_entries.flow.async_init("calibrated_light", context={"source": "user"})
    assert form["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"],
        {
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    assert result["type"] == "create_entry"


def intercept_source(hass, monkeypatch):
    calls = []
    service_class = type(hass.services)
    original = service_class.async_call

    async def call(self, domain, service, data=None, **kwargs):
        if domain == "light" and data and data.get("entity_id") == "light.raw_bedroom_lamp":
            calls.append((service, data))
            if service == "turn_on":
                hass.states.async_set(
                    "light.raw_bedroom_lamp",
                    STATE_ON,
                    {
                        "color_mode": "color_temp",
                        "brightness": data["brightness"],
                        "color_temp_kelvin": data["color_temp_kelvin"],
                    },
                )
            elif service == "turn_off":
                hass.states.async_set("light.raw_bedroom_lamp", STATE_OFF)
            return None
        return await original(self, domain, service, data, **kwargs)

    monkeypatch.setattr(service_class, "async_call", call)
    return calls


async def test_entities_track_source_and_preserve_target_on_clip(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    assert hass.states.get("number.bedroom_lamp_target_illuminance") is not None
    assert hass.states.get("number.bedroom_lamp_reference_illuminance") is not None
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance") is not None
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 120},
        blocking=True,
    )
    assert calls[-1][1]["color_temp_kelvin"] == 4001
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "color_temp_kelvin": 2200},
        blocking=True,
    )
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "120.0"
    assert calls[-1][1]["brightness"] == 255
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "color_temp_kelvin": 4001},
        blocking=True,
    )
    assert calls[-1][1]["brightness"] < 255


async def test_off_and_on_restore_requested_values(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 90},
        blocking=True,
    )
    await hass.services.async_call(
        "light",
        "turn_off",
        {"entity_id": "light.bedroom_lamp"},
        blocking=True,
    )
    assert calls[-1] == ("turn_off", {"entity_id": "light.raw_bedroom_lamp"})
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp"},
        blocking=True,
    )
    assert calls[-1][1]["color_temp_kelvin"] == 4001
    assert calls[-1][1]["brightness"] > 0


async def test_external_rgb_mode_makes_estimate_unavailable(hass):
    await setup_proxy(hass)
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {"color_mode": "rgbww", "brightness": 200, "rgbww_color": [0, 0, 0, 50, 50]},
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state == "unavailable"


async def test_brightness_slider_controls_lux_and_reports_actual_raw_output(hass, monkeypatch):
    await setup_proxy(hass)
    calls = intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": "light.bedroom_lamp", "brightness": 128},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert 70 < float(hass.states.get("number.bedroom_lamp_target_illuminance").state) < 100
    assert calls[-1][1]["brightness"] > 128
    assert 70 < float(hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state) < 100
    assert abs(int(hass.states.get("light.bedroom_lamp").attributes["brightness"]) - 128) < 5


async def test_options_change_reference_and_persist_target(hass, monkeypatch):
    entry = await setup_proxy(hass)
    intercept_source(hass, monkeypatch)
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.bedroom_lamp_target_illuminance", "value": 120},
        blocking=True,
    )
    hass.config_entries.async_update_entry(entry, options={"reference_lux": 200})
    await hass.async_block_till_done()
    assert hass.states.get("number.bedroom_lamp_reference_illuminance").state == "200.0"
    assert hass.states.get("number.bedroom_lamp_target_illuminance").state == "120.0"


async def test_configure_dialog_updates_model_selection_and_reference(hass):
    entry = await setup_proxy(hass)
    form = await hass.config_entries.options.async_init(entry.entry_id)
    assert form["type"] == "form"
    assert {key.schema for key in form["data_schema"].schema} == {"model_id", "reference_lux"}
    saved = await hass.config_entries.options.async_configure(
        form["flow_id"], {"model_id": "9290034999", "reference_lux": 200}
    )
    assert saved["type"] == "create_entry"
    await hass.async_block_till_done()
    assert hass.states.get("number.bedroom_lamp_reference_illuminance").state == "200.0"


async def test_new_proxy_adopts_current_white_light_instead_of_starting_at_maximum(hass):
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp"],
            "color_mode": "color_temp",
            "brightness": 41,
            "color_temp_kelvin": 3009,
        },
    )
    entry = MockConfigEntry(
        domain="calibrated_light",
        title="Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    actual = float(hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state)
    requested = float(hass.states.get("number.bedroom_lamp_target_illuminance").state)
    assert requested == pytest.approx(actual, abs=0.02)


async def test_new_proxy_with_source_off_starts_at_minimum_on_target(hass):
    await setup_proxy(hass)
    target = float(hass.states.get("number.bedroom_lamp_target_illuminance").state)
    assert 0 < target < 10


async def test_proxy_adopts_late_source_state_after_startup(hass):
    entry = MockConfigEntry(
        domain="calibrated_light",
        title="Bedroom Lamp",
        unique_id="light.raw_bedroom_lamp",
        data={
            "name": "Bedroom Lamp",
            "source_entity_id": "light.raw_bedroom_lamp",
            "model_id": "9290034999",
            "reference_lux": 173,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    hass.states.async_set(
        "light.raw_bedroom_lamp",
        STATE_ON,
        {
            "supported_color_modes": ["color_temp"],
            "color_mode": "color_temp",
            "brightness": 41,
            "color_temp_kelvin": 3009,
        },
    )
    await hass.async_block_till_done()
    actual = float(hass.states.get("sensor.bedroom_lamp_estimated_illuminance").state)
    requested = float(hass.states.get("number.bedroom_lamp_target_illuminance").state)
    assert requested == pytest.approx(actual, abs=0.02)
