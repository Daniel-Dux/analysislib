"""
Lyse single-shot routine: write shot data to InfluxDB.

Reads the single-shot dataframe produced by previous analysis routines
and sends configurable tags and fields to an InfluxDB v2 instance.

Configuration is read from ``influxdb_config.toml`` located next to this
script.  See that file for documentation on available options.

Requirements:
    pip install influxdb-client
"""

import os
from datetime import datetime
from pathlib import Path

import lyse
import h5py
import numpy as np

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11

import influxdb_client

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CONFIG_PATH = Path(__file__).with_name("influxdb_config.toml")




def _load_config(path: Path = _CONFIG_PATH) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def _parse_run_datetime(h5_path: str) -> datetime:
    """Read the run timestamp from HDF5 metadata; fall back to file mtime."""
    candidates: list = []
    try:
        with h5py.File(h5_path, "r") as f:
            for key in ("run time", "run_time", "runtime"):
                if key in f.attrs:
                    candidates.append(f.attrs[key])
            if "globals" in f:
                for key in ("run time", "run_time", "runtime"):
                    if key in f["globals"].attrs:
                        candidates.append(f["globals"].attrs[key])
    except Exception:
        pass

    for value in candidates:
        text = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else str(value)
        text = text.strip()
        if not text:
            continue
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass

    return datetime.fromtimestamp(os.path.getmtime(h5_path))


def _get_globals(h5_path: str) -> dict:
    """Return the run globals dict from a shot file."""
    globals_dict: dict = {}
    with h5py.File(h5_path, "r") as f:
        if "globals" not in f:
            return globals_dict
        for group_name in f["globals"]:
            group = f["globals"][group_name]
            for key, val in group.attrs.items():
                globals_dict[key] = val
    return globals_dict


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # -- Load config --------------------------------------------------------
    cfg = _load_config()
    influx_cfg = cfg.get("INFLUXDB", {})
    host = influx_cfg.get("host", "localhost")
    port = int(influx_cfg.get("port", 8086))
    token = influx_cfg.get("token", "")
    org = influx_cfg.get("org", "ultracold")
    bucket = influx_cfg.get("bucket", "labscript")
    measurement = influx_cfg.get("measurement", "shot_data")
    include_dt = influx_cfg.get("include_time_since_previous_shot", True)

    tags_cfg = cfg.get("TAGS", {})
    fields_cfg = cfg.get("FIELDS", {})

    # -- Determine current shot path ----------------------------------------
    try:
        h5_path = lyse.path
    except AttributeError:
        h5_path = None

    if h5_path is None:
        df = lyse.data()
        if df is None or len(df) == 0:
            print("[influxdb_writer] No shots available.")
            return
        h5_path = df.filepath.iloc[-1]

    # -- Gather the single-shot dataframe -----------------------------------
    df = lyse.data()
    if df is None or len(df) == 0:
        print("[influxdb_writer] Dataframe is empty — nothing to send.")
        return

    # The last row is the current shot
    shot_row = df.iloc[-1]

    # -- Gather globals from the HDF5 file ----------------------------------
    run_globals = _get_globals(h5_path)

    # -- Build the InfluxDB point -------------------------------------------
    point = influxdb_client.Point(measurement)

    # Static tags
    for tag_name, tag_value in tags_cfg.get("static", {}).items():
        point.tag(tag_name, str(tag_value))

    # Tags from globals
    for tag_name, global_name in tags_cfg.get("globals", {}).items():
        value = run_globals.get(global_name)
        if value is not None:
            if isinstance(value, bytes):
                value = value.decode("utf-8", errors="replace")
            point.tag(tag_name, str(value))

    # Fields from the single-shot dataframe
    singleshot_fields = fields_cfg.get("singleshot", {})
    for field_name, column_spec in singleshot_fields.items():
        if not isinstance(column_spec, list) or len(column_spec) != 2:
            print(
                f"[influxdb_writer] Skipping field '{field_name}': "
                f"expected [group, key], got {column_spec!r}"
            )
            continue
        group, key = column_spec
        try:
            value = shot_row[(group, key)]
        except (KeyError, TypeError):
            print(
                f"[influxdb_writer] Field '{field_name}' not found in "
                f"dataframe column ({group!r}, {key!r}) — skipping."
            )
            continue
        # If duplicate columns exist the lookup returns a Series; take last.
        if hasattr(value, "iloc"):
            value = value.iloc[-1]
        if _is_numeric(value):
            point.field(field_name, float(value))
        elif isinstance(value, str):
            point.field(field_name, value)
        else:
            print(
                f"[influxdb_writer] Field '{field_name}' has unsupported "
                f"type {type(value).__name__} — skipping."
            )

    # Fields from globals
    globals_fields = fields_cfg.get("globals", {})
    for field_name, global_name in globals_fields.items():
        value = run_globals.get(global_name)
        if value is None:
            print(
                f"[influxdb_writer] Global '{global_name}' not found — "
                f"skipping field '{field_name}'."
            )
            continue
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")
        if _is_numeric(value):
            point.field(field_name, float(value))
        elif isinstance(value, str):
            point.field(field_name, value)

    # Shot timestamp and time since previous shot
    shot_time = _parse_run_datetime(h5_path)
    # point.time(shot_time)
    if include_dt and len(df) >= 2:
        current_run_time = df["run time"].iloc[-1]
        previous_run_time = df["run time"].iloc[-2]
        try:
            dt = (current_run_time - previous_run_time).total_seconds()
            point.field("Time_Since_Previous_Shot_s", float(dt))
        except Exception:
            pass

    # -- Write to InfluxDB --------------------------------------------------
    try:
        client = influxdb_client.InfluxDBClient(
            url=f"http://{host}:{port}",
            token=token,
            org=org,
        )
        write_api = client.write_api()
        write_api.write(bucket=bucket, record=point)
        write_api.close()
        client.close()
        print("[influxdb_writer] Point written successfully.")
    except Exception as exc:
        print(f"[influxdb_writer] Failed to write to InfluxDB: {exc}")


def _is_numeric(value) -> bool:
    """Return True if *value* can be losslessly converted to float."""
    if isinstance(value, (int, float, np.integer, np.floating)):
        return True
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    main()
