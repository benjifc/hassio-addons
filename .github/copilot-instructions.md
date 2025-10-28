## Quick summary

This repo is a small Python bridge that reads data from a Huawei SUN2000 inverter over Modbus TCP (using the third-party `huawei_solar` library) and publishes values to an MQTT broker (using `paho.mqtt`). The single entrypoint is `huaweisolar.py` and a `Dockerfile` is provided for containerized runs.

## Big-picture architecture

- Source of truth: `huaweisolar.py` — it constructs a `HuaweiSolar` object and repeatedly calls `inverter.get(<name>)` to retrieve values.
- Transport: MQTT via `paho.mqtt.client`. Topics use the prefix `emon/NodeHuawei/` (e.g. `emon/NodeHuawei/active_power`).
- Deployment: simple Docker image (`Dockerfile`) that installs `requirements.txt` and runs `huaweisolar.py`.

Why this layout: the project is intentionally minimal — a single script that polls the inverter in a tight loop and publishes to MQTT. There are no services or background daemons beyond the script itself and Docker is provided as an easy packaging option.

## Key files to inspect

- `huaweisolar.py` — main script. Look here for polling logic, variable names, and MQTT topic formatting.
- `requirements.txt` — dependencies (`huawei_solar`, `paho.mqtt`).
- `Dockerfile` — how the container image is built and what command runs the script.
- `README.md` — project motivation, diagrams, and example Node-RED listeners.

## Important patterns & conventions (project-specific)

- Variable retrieval: call inverter.get('<var_name>') and use the returned object's `.value` property — e.g.:

  mid = inverter.get('active_power')
  payload = str(mid.value)

- Topic naming: the code publishes every metric under the `emon/NodeHuawei/` prefix. If you add metrics, follow this same prefix.
- Polling strategy: `vars_inmediate` (polled every loop iteration) vs `vars` (polled every ~6 loops). If adding a slow-changing metric, append it to `vars` to reduce freq.
- Minimal error handling: the script uses broad `except: pass` around reads — failures are silent. When extending, replace these with targeted exception handling and logging to avoid hidden failures.
- MQTT connection pattern: uses `client.connected_flag` custom flag with `loop_start()` and `loop_stop()` rather than a blocking loop. Keep that pattern if adding reconnection logic.

## How to run & debug (exact commands)

Local (dev) run — ensure Python 3.8+ and dependencies are installed:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
INVERTER_IP=192.168.1.14 MQTT_HOST=192.168.1.15 python3 huaweisolar.py
```

Docker (build + run):

```bash
docker build -t huawei-sun2000 .
docker run --rm -e INVERTER_IP=192.168.1.14 -e MQTT_HOST=192.168.1.15 huawei-sun2000
```

Quick single-read test (no loop) — useful for debugging connectivity or mapping registers:

```python
from huawei_solar import HuaweiSolar
inv = HuaweiSolar('192.168.1.14', port=502, slave=1)
print(inv.get('active_power').value)
```

## Examples to reference when modifying

- To add a metric `foo_bar` and publish it:

  - add `'foo_bar'` to the appropriate `vars_inmediate` or `vars` list in `huaweisolar.py`
  - published topic will be `emon/NodeHuawei/foo_bar` using the same `clientMQTT.publish(...)` call pattern

- To change topic prefix globally: replace the hardcoded string `emon/NodeHuawei/` in `huaweisolar.py` with a single constant or environment variable and update subscribers accordingly.

## Integration points & external dependencies

- `huawei_solar` (third-party lib): responsible for translating known attribute names (like `pv_01_voltage`) to Modbus register reads. Inspect its docs/source when you need to add attributes not currently used.
- `paho.mqtt` broker: the script expects a reachable MQTT broker on `MQTT_HOST` port 1883. Authentication is currently empty — if you enable auth, update `clientMQTT.username_pw_set(...)` in `huaweisolar.py`.

## Notable caveats discovered in the code

- The script sets internal attributes directly (`inverter._slave = 1`). This hints at library limitations or hacks; prefer library constructor args when possible.
- Silent exception swallowing means connectivity issues may not be obvious — add logging and specific exception captures when hardening.
- The script uses `time.sleep(1)` in a tight loop; long-running runs should consider backoff, health checks, or supervision (systemd/container restarts are recommended for production).

## When you're editing this repo (suggested guardrails)

- Keep `huaweisolar.py` as the canonical polling flow. For larger changes, factor a new module and keep the CLI thin.
- Maintain the `emon/NodeHuawei/` topic convention or clearly document the change in the README.

## Questions for the repo owner (helpful to clarify)

- Do you want non-silent error logging for failed Modbus reads? (current code swallows exceptions)
- Should MQTT authentication be supported and documented in the README and Docker run example?

If anything here is unclear or you'd like extra examples (unit tests, a small module refactor, or safer error handling), tell me which area to expand and I will iterate.
