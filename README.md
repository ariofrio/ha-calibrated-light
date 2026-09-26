# Calibrated Light for Home Assistant

A white-light proxy whose **target illuminance is in lux at a position you choose**. It wraps an existing tunable-white light, uses a measured model of that bulb's dimming and color-temperature response, and controls the source through Home Assistant. It is separate from [Daylight](https://github.com/ariofrio/ha-daylight): Daylight describes an outdoor clear-sky reference; Calibrated Light describes a lamp's estimated contribution at one indoor position.

The first measured profile is the [Philips WiZ 21 W A23, retail model 9290034999](https://www.usa.lighting.philips.com/consumer/p/smart-led-bulb-21w-eq150w-a23-e26/046677578718). WiZ's HA model string `SHRGB` is too broad to identify this retail model automatically. Select the measured model only if the bulb label matches.

## Install

Requires Home Assistant 2026.9 or newer.

1. In HACS, add `https://github.com/ariofrio/ha-calibrated-light` as a custom repository of type **Integration** and download **Calibrated Light**. Restart Home Assistant.
2. If you want the proxy to take your lamp's familiar entity ID, first rename the physical source entity (for example, `light.bedroom_lamp` → `light.raw_bedroom_lamp`). Check and update any automations or dashboards that refer to the old ID before doing so.
3. Open **Settings → Devices & services → Add integration → Calibrated Light**. Choose the source light, bulb model, name, and the reference illuminance described below. You may rename the proxy entity afterward to the desired ID.

[Add repository to HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=ariofrio&repository=ha-calibrated-light&category=integration) · [Set up Calibrated Light](https://my.home-assistant.io/redirect/config_flow_start/?domain=calibrated_light)

Manual installation: copy `custom_components/calibrated_light/` into your HA configuration directory, restart, then complete step 3. [HACS integration instructions](https://www.hacs.dev/docs/use/repositories/type/integration/).

## Calibrate a position

Put the light meter at the position and orientation you care about. Measure the source **off**, then at **4000 K and 100%**, as close together in time as practical. Enter `on reading − off reading` as the **Reference illuminance** in lx. This is the lamp's contribution at that position, not total room illuminance or the bulb's lumens. Avoid moving the meter or changing other lights between readings. Daylight is fine if its contribution is stable across the pair.

Andres's bedroom example: 25 lx off and 198 lx on gave **173 lx** at the bed. An independent 50% reading gave 78 lx lamp-only; the curve predicts about 77.4 lx. Those readings are at one position and do not transfer to another position without a new reference measurement.

Create another Calibrated Light setup for another bulb and position. The current version allows one proxy per source light; it does not coordinate multiple proxies that command the same source.

## Entities and behavior

For a device named **Bedroom Lamp**, Home Assistant normally assigns:

| Entity | Purpose |
|---|---|
| `light.bedroom_lamp` | On/off, tunable-white CCT, and a 1–255 brightness slider mapped across the *achievable lamp-only lux range* at the current CCT |
| `number.bedroom_lamp_target_illuminance` | Requested lamp-only lux at the calibrated position; the main numeric control |
| `sensor.bedroom_lamp_estimated_illuminance` | Estimated actual lamp-only lux from the source's reported brightness and CCT; 0 when off, unavailable when its output cannot be modeled |
| `number.bedroom_lamp_reference_illuminance` | Calibration number, in lx; marked as a configuration entity |

Entity IDs are assigned by HA and can be renamed. The original source light remains its own HA entity; this integration does not hide or rename it.

A CCT change keeps the requested lux. If the warmer/cooler setting cannot achieve that target, the source is driven to its maximum there, while the target number stays unchanged. Moving back to a CCT with more output restores the original target. An explicit change to the light's brightness slider *does* set a new target. Setting the target number sends a command immediately; setting it to zero turns the light off. The source's minimum on setting is about 10%, so positive targets below that physical floor produce the minimum on output.

Turning the proxy off retains the requested lux and CCT in HA storage. Turning it on explicitly sends both values again, rather than relying on the physical bulb's memory. If the target was zero, turning on starts at minimum on output. Source changes made outside the proxy are reflected in its actual light brightness and estimated sensor, but do not overwrite the requested target. If the source enters RGB/effect mode, the estimated sensor becomes unavailable; the next proxy control command returns it to tunable white. RGB/effects are not calibrated in this version.

On first setup, the proxy waits for the source's first usable state, then adopts its current white-light output as the initial target, so its first command does not jump to maximum. If the source is off or in an unmodeled mode, it starts with the minimum on output as its saved target. Later setups restore the saved request.

## Model and limits

The calculation is:

```text
predicted lamp-only lx = reference lx × dimming_fraction(D) × peak_output(CCT) / peak_output(4000 K)
```

`D` is the WiZ percentage (10–100). The two curves are monotone piecewise cubic interpolations of the supplied [measurements](docs/original-measurements.csv); the compact [curve coefficients](custom_components/calibrated_light/a23_curve.json) are evaluated without SciPy in HA. The original 4000 K/100% room reading calibrates all predictions at this one location. The 50% room reading independently checks the scaling within about 1 lx.

The CCT curve and dimming curve were measured inside the lampshade. Predicting across CCT at another position assumes the shade and room preserve those relative ratios; that has **not** been separately measured. The bulb's published 2550 lm rating is not used as an absolute calibration, and the model does not claim to measure emitted lumens. Sensor accuracy, meter position, ambient-light drift, and bulb variation affect the result. See [model provenance and limitations](docs/model.md).

## Development

```sh
uv venv --python 3.14
uv pip install -r requirements-test.txt
uv run --no-project ruff check .
uv run --no-project ruff format --check .
uv run --no-project pytest -q
```

Code is MIT licensed. Initial implementation and documentation were written by Codex at the repository owner's direction. The measurements were supplied by Andres Riofrio.
