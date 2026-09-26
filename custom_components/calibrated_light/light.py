"""Calibrated light entity."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)

from .const import DOMAIN
from .entity import ProxyEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([CalibratedLight(hass.data[DOMAIN][entry.entry_id])])


class CalibratedLight(ProxyEntity, LightEntity):
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, controller) -> None:
        super().__init__(controller, "light")
        self._attr_min_color_temp_kelvin = controller.model.min_kelvin
        self._attr_max_color_temp_kelvin = controller.model.max_kelvin

    @property
    def available(self) -> bool:
        source = self.controller.source_state()
        return source is not None and source.state not in ("unknown", "unavailable")

    @property
    def is_on(self) -> bool:
        source = self.controller.source_state()
        return source is not None and source.state == "on"

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.COLOR_TEMP

    @property
    def color_temp_kelvin(self) -> int | None:
        state = self.controller.source_state()
        if state is None or not self.controller.is_white():
            return None
        return state.attributes.get("color_temp_kelvin")

    @property
    def brightness(self) -> int | None:
        return self.controller.display_brightness()

    @property
    def extra_state_attributes(self) -> dict:
        command = self.controller
        return {
            "requested_illuminance_lx": round(command.target_lux, 2),
            "source_entity_id": command.source,
            "source_color_mode": (
                command.source_state().attributes.get("color_mode")
                if command.source_state()
                else None
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        kelvin = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        transition = kwargs.get(ATTR_TRANSITION)
        if brightness is not None:
            await self.controller.set_brightness(brightness, kelvin, transition)
        elif kelvin is not None:
            await self.controller.set_kelvin(kelvin, transition)
        else:
            await self.controller.turn_on(transition)

    async def async_turn_off(self, **kwargs) -> None:
        await self.controller.turn_off(kwargs.get(ATTR_TRANSITION))
