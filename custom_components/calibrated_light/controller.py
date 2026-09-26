"""Shared requested and observed state for one calibrated position."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite

from homeassistant.components.light import ColorMode
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.storage import Store

from .const import CONF_REFERENCE, CONF_SOURCE, DOMAIN
from .model import A23, brightness_for_lux, map_brightness, plan_target


class Controller:
    """One source bulb and one calibrated receiving position."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass = hass
        self.entry = entry
        self.source = entry.options.get(CONF_SOURCE, entry.data[CONF_SOURCE])
        self.model = A23
        self.reference_lux = float(entry.options.get(CONF_REFERENCE, entry.data[CONF_REFERENCE]))
        self.target_lux = self.model.lux(
            self.model.min_dim, self.model.reference_kelvin, self.reference_lux
        )
        self.kelvin = self.model.reference_kelvin
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")
        self.listeners: list[Callable[[], None]] = []
        self.pending_adoption = False

    async def async_load(self) -> None:
        data = await self.store.async_load() or {}
        target = data.get("target_lux")
        kelvin = data.get("kelvin")
        if (
            isinstance(target, (int, float))
            and not isinstance(target, bool)
            and isfinite(target)
            and target >= 0
            and isinstance(kelvin, int)
            and not isinstance(kelvin, bool)
            and self.model.min_kelvin <= kelvin <= self.model.max_kelvin
        ):
            self.target_lux = float(target)
            self.kelvin = kelvin
            return
        self.pending_adoption = True
        await self.async_finish_adoption()

    async def async_finish_adoption(self) -> None:
        """Adopt the first usable source state when there is no saved request."""
        if not self.pending_adoption:
            return
        state = self.source_state()
        if state is None or state.state in ("unknown", "unavailable"):
            return
        if self.is_white():
            actual_lux = self.estimated_lux()
            if actual_lux is not None and actual_lux > 0:
                self.kelvin = round(state.attributes["color_temp_kelvin"])
                self.target_lux = actual_lux
        self.pending_adoption = False
        await self._save()
        self.notify()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        self.listeners.append(listener)

        def remove() -> None:
            self.listeners.remove(listener)

        return remove

    @callback
    def notify(self) -> None:
        for listener in tuple(self.listeners):
            listener()

    def source_state(self) -> State | None:
        return self.hass.states.get(self.source)

    def is_white(self) -> bool:
        state = self.source_state()
        return state is not None and state.attributes.get("color_mode") == ColorMode.COLOR_TEMP

    def estimated_lux(self) -> float | None:
        state = self.source_state()
        if state is None or state.state in ("unavailable", "unknown"):
            return None
        if state.state != STATE_ON:
            return 0.0
        if not self.is_white():
            return None
        brightness = state.attributes.get("brightness")
        kelvin = state.attributes.get("color_temp_kelvin")
        if not isinstance(brightness, (int, float)) or not isinstance(kelvin, (int, float)):
            return None
        dim = max(self.model.min_dim, min(self.model.max_dim, round(brightness * 100 / 255)))
        try:
            return self.model.lux(dim, round(kelvin), self.reference_lux)
        except ValueError:
            return None

    def display_brightness(self) -> int | None:
        actual = self.estimated_lux()
        if actual is None or actual == 0:
            return None
        state = self.source_state()
        assert state is not None
        return brightness_for_lux(
            self.model, actual, round(state.attributes["color_temp_kelvin"]), self.reference_lux
        )

    async def set_target(self, target: float) -> None:
        if not isfinite(target) or target < 0:
            raise ValueError("Target illuminance must be nonnegative and finite")
        self.target_lux = float(target)
        await self._save()
        await self.apply()

    async def set_brightness(self, brightness: int, kelvin: int | None = None) -> None:
        if kelvin is not None:
            self.kelvin = kelvin
        self.target_lux = map_brightness(self.model, brightness, self.kelvin, self.reference_lux)
        await self._save()
        await self.apply()

    async def set_kelvin(self, kelvin: int) -> None:
        if not self.model.min_kelvin <= kelvin <= self.model.max_kelvin:
            raise ValueError("CCT outside measured range")
        self.kelvin = kelvin
        await self._save()
        await self.apply()

    async def turn_on(self) -> None:
        if self.pending_adoption:
            await self._save()
        if self.target_lux == 0:
            self.target_lux = self.model.lux(self.model.min_dim, self.kelvin, self.reference_lux)
            await self._save()
        await self.apply()

    async def turn_off(self) -> None:
        if self.pending_adoption:
            await self._save()
        await self.hass.services.async_call(
            "light", "turn_off", {"entity_id": self.source}, blocking=True
        )
        self.notify()

    async def apply(self) -> None:
        command = plan_target(self.model, self.target_lux, self.kelvin, self.reference_lux)
        self.notify()
        if command.dim is None:
            await self.turn_off()
            return
        await self.hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": self.source,
                "brightness": command.ha_brightness,
                "color_temp_kelvin": self.kelvin,
            },
            blocking=True,
        )
        self.notify()

    async def set_reference(self, reference_lux: float) -> None:
        if not isfinite(reference_lux) or reference_lux <= 0:
            raise ValueError("Reference illuminance must be positive and finite")
        self.reference_lux = float(reference_lux)
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_REFERENCE: reference_lux}
        )
        self.notify()

    async def _save(self) -> None:
        self.pending_adoption = False
        await self.store.async_save({"target_lux": self.target_lux, "kelvin": self.kelvin})
