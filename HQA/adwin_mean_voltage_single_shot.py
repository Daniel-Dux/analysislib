"""
Lyse single-shot routine: compute and store mean ADwin analog-input voltage.

Saved results group:
    adwin_mean_voltage
Saved results:
    - shot_mean_voltage_V
    - shot_mean_temperature_C
    - shot_num_channels
    - shot_num_samples
    - channel_means_V (array)
"""

# pyright: reportGeneralTypeIssues=false

import lyse  # type: ignore
import h5py
import numpy as np
from typing import Any, cast

from user_devices.ADwinProII.ADwin_utils import DAC


def get_h5_path():
    try:
        return lyse.path
    except AttributeError:
        pass

    df = lyse.data()
    if df is None or len(df) == 0:
        raise RuntimeError("No shots available in lyse dataframe")
    return df.filepath.iloc[-1]


def choose_tc_channel(channel_means, channel_counts, run_globals):
    if not channel_means:
        return None, np.nan

    preferred_name = str(run_globals.get('tc_channel_name', '')).strip()
    if preferred_name:
        if preferred_name in channel_means:
            return preferred_name, channel_means[preferred_name]

        lower_map = {name.lower(): name for name in channel_means}
        if preferred_name.lower() in lower_map:
            matched = lower_map[preferred_name.lower()]
            return matched, channel_means[matched]

        partial_matches = [name for name in channel_means if preferred_name.lower() in name.lower()]
        if len(partial_matches) == 1:
            matched = partial_matches[0]
            return matched, channel_means[matched]

    preferred_index = run_globals.get('tc_channel_index', None)
    if preferred_index is not None:
        try:
            preferred_index = int(preferred_index)
            common_candidates = [
                f'AIN_{preferred_index}',
                f'ain_{preferred_index}',
            ]
            for candidate in common_candidates:
                if candidate in channel_means:
                    return candidate, channel_means[candidate]

            suffix_matches = [
                name for name in channel_means
                if name.strip().lower().endswith(f'_{preferred_index}')
            ]
            if len(suffix_matches) == 1:
                matched = suffix_matches[0]
                return matched, channel_means[matched]
        except Exception:
            pass

    heuristic_candidates = [
        name for name in channel_means
        if any(token in name.lower() for token in ('temp', 'thermo', 'oven'))
    ]
    if len(heuristic_candidates) == 1:
        matched = heuristic_candidates[0]
        return matched, channel_means[matched]

    if 'AIN_16' in channel_means:
        return 'AIN_16', channel_means['AIN_16']

    total_sum = 0.0
    total_count = 0
    for name, mean_v in channel_means.items():
        count = int(channel_counts.get(name, 0))
        total_sum += float(mean_v) * count
        total_count += count
    if total_count > 0:
        return '__all_weighted__', total_sum / total_count

    return None, np.nan


def extract_channel_means(h5_path, run_globals=None):
    if run_globals is None:
        run_globals = {}

    channel_means = {}
    channel_counts = {}
    total_sum = 0.0
    total_count = 0

    with h5py.File(h5_path, 'r') as f:
        try:
            ain_group = cast(Any, f['devices/ADwin/ANALOG_IN'])
            times_ds = cast(Any, f['devices/ADwin/ANALOG_IN/TIMES'])
            raw_data = cast(Any, f['data/traces/ADwinAnalogIn_DATA'])
        except Exception:
            return channel_means, np.nan, 0, None

        times_table = np.asarray(times_ds[:])
        ain_attrs = dict(ain_group.attrs)

        acquisitions_per_channel = times_table['stop_time'] - times_table['start_time']
        channels_with_data = np.where(acquisitions_per_channel > 0)[0]
        if len(channels_with_data) == 0:
            return channel_means, np.nan, 0, None

        acquisitions_with_data = acquisitions_per_channel[channels_with_data]
        offsets = np.concatenate(([0], np.cumsum(acquisitions_with_data)))

        for idx, channel_idx in enumerate(channels_with_data):
            start_idx = int(offsets[idx])
            stop_idx = int(offsets[idx + 1])
            if stop_idx <= start_idx:
                continue

            data_array = np.asarray(raw_data[start_idx:stop_idx])
            if not data_array.size:
                continue

            values = DAC(data_array, resolution=16, min_V=-10, max_V=10)
            dtype_names = times_table.dtype.names or ()
            if 'gain_mode' in dtype_names:
                gain_mode = times_table['gain_mode'][channel_idx]
                values = values / (2 ** gain_mode)

            label_key = str(channel_idx + 1)
            if label_key in ain_attrs and isinstance(ain_attrs[label_key], (str, bytes)):
                label = ain_attrs[label_key]
                if isinstance(label, bytes):
                    label = label.decode('utf-8')
            else:
                label = f'AIN_{channel_idx + 1}'

            ch_mean = float(np.mean(values))
            channel_means[label] = ch_mean
            channel_counts[label] = int(values.size)

            total_sum += float(np.sum(values))
            total_count += int(values.size)

    selected_channel, selected_mean = choose_tc_channel(channel_means, channel_counts, run_globals)

    if total_count == 0:
        return channel_means, np.nan, 0, selected_channel

    return channel_means, selected_mean, total_count, selected_channel


def voltage_to_k_type_temperature_c(voltage_v, run_globals):
    """Convert measured voltage to temperature in °C for a K-type thermocouple.

        Models (global ``tc_model``):
            - ``raw_type_k`` (default): Thermocouple conversion with cold-junction compensation.
            - ``AD595`` / ``AD597``: linear 10 mV/°C frontend.
            - ``AD8495``: linear 5 mV/°C with 1.25 V offset.

        Raw thermocouple globals:
            - ``tc_type``: ``K`` (default), ``J``, ``T``, ``E``.
              (K uses NIST inverse polynomial, other types currently use
              linearized sensitivity with cold-junction compensation.)

        Optional calibration globals:
            - ``tc_temperature_scale``: multiplicative correction factor.
            - ``tc_temperature_offset_C``: additive correction in °C.
        """

    def apply_calibration(temp_c):
        scale = float(run_globals.get('tc_temperature_scale', 1.0))
        offset_c = float(run_globals.get('tc_temperature_offset_C', 0.0))
        return temp_c * scale + offset_c

    def poly_eval(coeffs, x):
        return sum(c * (x ** i) for i, c in enumerate(coeffs))

    def type_k_c_to_emf_mv(temp_c):
        if temp_c < -270 or temp_c > 1372:
            return np.nan

        if temp_c < 0:
            coeffs = [
                0.0,
                3.94501280250e-2,
                2.36223735980e-5,
                -3.28589067840e-7,
                -4.99048287770e-9,
                -6.75090591730e-11,
                -5.74103274280e-13,
                -3.10888728940e-15,
                -1.04516093650e-17,
                -1.98892668780e-20,
            ]
            return poly_eval(coeffs, temp_c)

        coeffs = [
            -1.76004136860e-2,
            3.89212049750e-2,
            1.85587700320e-5,
            -9.94575928740e-8,
            3.18409457190e-10,
            -5.60728448890e-13,
            5.60750590590e-16,
            -3.20207200030e-19,
            9.71511471520e-23,
            -1.21047212750e-26,
        ]
        a0 = 1.18597600000e-1
        a1 = -1.18343200000e-4
        a2 = 1.26968600000e2
        return poly_eval(coeffs, temp_c) + a0 * np.exp(a1 * ((temp_c - a2) ** 2))

    def type_k_emf_mv_to_c(emf_mv):
        if emf_mv < -5.891 or emf_mv > 54.886:
            return np.nan

        if emf_mv < 0:
            coeffs = [
                0.0,
                2.5173462e1,
                -1.1662878,
                -1.0833638,
                -8.9773540e-1,
                -3.7342377e-1,
                -8.6632643e-2,
                -1.0450598e-2,
                -5.1920577e-4,
            ]
            return poly_eval(coeffs, emf_mv)

        if emf_mv <= 20.644:
            coeffs = [
                0.0,
                2.508355e1,
                7.860106e-2,
                -2.503131e-1,
                8.315270e-2,
                -1.228034e-2,
                9.804036e-4,
                -4.413030e-5,
                1.057734e-6,
                -1.052755e-8,
            ]
            return poly_eval(coeffs, emf_mv)

        coeffs = [
            -1.318058e2,
            4.830222e1,
            -1.646031,
            5.464731e-2,
            -9.650715e-4,
            8.802193e-6,
            -3.110810e-8,
        ]
        return poly_eval(coeffs, emf_mv)

    model = str(run_globals.get('tc_model', 'raw_type_k')).strip().lower()
    tc_type = str(run_globals.get('tc_type', 'K')).strip().upper()
    v = float(voltage_v)

    if model in ('ad595', 'ad597'):
        temp_c = (v - float(run_globals.get('tc_offset_v', 0.0))) / float(run_globals.get('tc_v_per_c', 0.01))
        return apply_calibration(temp_c)

    if model == 'ad8495':
        temp_c = (v - float(run_globals.get('tc_offset_v', 1.25))) / float(run_globals.get('tc_v_per_c', 0.005))
        return apply_calibration(temp_c)

    input_gain = float(run_globals.get('tc_input_gain', 1.0))
    input_offset_v = float(run_globals.get('tc_input_offset_V', 0.0))
    if input_gain == 0:
        return np.nan

    emf_measured_mv = (v - input_offset_v) / input_gain * 1e3
    cold_junction_c = float(run_globals.get('tc_cold_junction_C', 25.0))

    if tc_type in ('J', 'T', 'E'):
        sensitivities_uv_per_c = {
            'J': 55.0,
            'T': 43.0,
            'E': 68.0,
        }
        sensitivity_v_per_c = sensitivities_uv_per_c[tc_type] * 1e-6
        if sensitivity_v_per_c == 0:
            return np.nan
        temp_c = cold_junction_c + (emf_measured_mv * 1e-3) / sensitivity_v_per_c
        return apply_calibration(temp_c)

    # Default / K-type path (NIST)
    cold_junction_emf_mv = type_k_c_to_emf_mv(cold_junction_c)
    if not np.isfinite(cold_junction_emf_mv):
        return np.nan

    emf_hot_mv = emf_measured_mv + cold_junction_emf_mv
    temp_c = type_k_emf_mv_to_c(emf_hot_mv)
    if not np.isfinite(temp_c):
        return np.nan
    return apply_calibration(temp_c)


def main():
    h5_path = get_h5_path()
    run = lyse.Run(h5_path)
    run_globals = run.get_globals()
    result_group = 'results/adwin_mean_voltage'

    channel_means, shot_mean, total_samples, selected_channel = extract_channel_means(h5_path, run_globals=run_globals)

    # Always save core extraction results, even if temperature conversion fails.
    run.save_result('shot_mean_voltage_V', float(shot_mean) if np.isfinite(shot_mean) else np.nan, group=result_group)
    run.save_result('shot_num_channels', int(len(channel_means)), group=result_group)
    run.save_result('shot_num_samples', int(total_samples), group=result_group)
    run.save_result('shot_source_channel', str(selected_channel) if selected_channel is not None else 'none', group=result_group)

    def convert_temp_safe(voltage_v, globals_dict):
        try:
            if not np.isfinite(voltage_v):
                return np.nan
            return voltage_to_k_type_temperature_c(voltage_v, globals_dict)
        except Exception:
            return np.nan

    shot_temp_c = convert_temp_safe(shot_mean, run_globals)
    run.save_result('shot_mean_temperature_C', float(shot_temp_c) if np.isfinite(shot_temp_c) else np.nan, group=result_group)

    if bool(run_globals.get('tc_compare_types', False)) and np.isfinite(shot_mean):
        for tc_type in ('K', 'J', 'T', 'E'):
            rg_copy = dict(run_globals)
            rg_copy['tc_type'] = tc_type
            temp_try = convert_temp_safe(shot_mean, rg_copy)
            run.save_result(
                f'shot_mean_temperature_C_{tc_type}',
                float(temp_try) if np.isfinite(temp_try) else np.nan,
                group=result_group,
            )

    if channel_means:
        ordered_names = sorted(channel_means.keys())
        means = np.array([channel_means[name] for name in ordered_names], dtype=float)
        temperatures = np.array([
            convert_temp_safe(channel_means[name], run_globals)
            for name in ordered_names
        ], dtype=float)
        run.save_result_array('channel_means_V', means, group=result_group)
        run.save_result_array('channel_temperatures_C', temperatures, group=result_group)

    if np.isfinite(shot_mean) and np.isfinite(shot_temp_c):
        print(
            f"ADwin shot mean: {shot_mean:.6g} V -> {shot_temp_c:.3f} degC "
            f"across {total_samples} samples"
        )
    else:
        print('No ADwin analog-input data found for this shot')


if __name__ == '__main__':
    main()
