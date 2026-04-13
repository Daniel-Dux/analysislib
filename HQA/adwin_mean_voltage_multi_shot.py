"""
Lyse multi-shot routine: plot saved thermocouple temperature vs run time.

Reads single-shot result:
    adwin_mean_voltage / shot_mean_temperature_C
Compatibility fallback:
    adwin_mean_voltage / shot_mean_voltage_V
"""

# pyright: reportGeneralTypeIssues=false

import os
import re
from datetime import datetime, timedelta

import lyse  # type: ignore
import h5py
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Any, cast
try:
    from scipy.optimize import curve_fit
except Exception:
    curve_fit = None

from user_devices.ADwinProII.ADwin_utils import DAC


# Offset-exponential fitting configuration:
#   model: y(t) = offset + amplitude * exp(-(t - t0) / tau)
# Fit ranges are in elapsed seconds from first valid point.
# Use None for open-ended bounds.
ENABLE_OFFSET_EXP_FITS = True
FIT_WINDOWS_SECONDS = [
    (100, 500),
    (750, None)
]


def offset_exponential_decay(t_s, offset, amplitude, tau_s):
    return offset + amplitude * np.exp(-t_s / tau_s)


def fit_offset_exp_windows(elapsed_s, values, fit_windows_seconds):
    if curve_fit is None:
        print('[fit] scipy is not available; skipping offset-exponential fits')
        return []

    results = []

    for idx, (lower_s, upper_s) in enumerate(fit_windows_seconds, start=1):
        lo = -np.inf if lower_s is None else float(lower_s)
        hi = np.inf if upper_s is None else float(upper_s)

        if lo >= hi:
            print(f'[fit {idx}] skipped: invalid bounds ({lower_s}, {upper_s})')
            continue

        mask = (elapsed_s >= lo) & (elapsed_s <= hi)
        if int(np.count_nonzero(mask)) < 4:
            print(f'[fit {idx}] skipped: not enough points in bounds ({lower_s}, {upper_s})')
            continue

        t_window = elapsed_s[mask]
        y_window = values[mask]
        t0 = float(t_window[0])
        t_fit = t_window - t0

        offset0 = float(np.mean(y_window[-max(1, len(y_window) // 5):]))
        amplitude0 = float(y_window[0] - offset0)
        if np.isclose(amplitude0, 0.0):
            amplitude0 = float(np.max(y_window) - np.min(y_window))
            if np.isclose(amplitude0, 0.0):
                amplitude0 = 1.0
        tau0 = max(float(t_fit[-1] - t_fit[0]) * 0.5, 1e-3)

        try:
            popt, _ = curve_fit(
                offset_exponential_decay,
                t_fit,
                y_window,
                p0=[offset0, amplitude0, tau0],
                bounds=([-np.inf, -np.inf, 1e-9], [np.inf, np.inf, np.inf]),
                maxfev=10000,
            )
        except Exception as exc:
            print(f'[fit {idx}] failed in bounds ({lower_s}, {upper_s}): {exc}')
            continue

        y_pred = offset_exponential_decay(t_fit, *popt)
        residuals = y_window - y_pred
        ss_res = float(np.sum(residuals ** 2))
        ss_tot = float(np.sum((y_window - np.mean(y_window)) ** 2))
        r2 = np.nan if np.isclose(ss_tot, 0.0) else 1.0 - (ss_res / ss_tot)

        results.append({
            'index': idx,
            'bounds': (lower_s, upper_s),
            'mask': mask,
            't0': t0,
            'offset': float(popt[0]),
            'amplitude': float(popt[1]),
            'tau_s': float(popt[2]),
            'r2': r2,
        })

    return results


def format_fit_parameters_text(fit_results):
    lines = []
    for fit in fit_results:
        tau_s = fit['tau_s']
        slope_inv_s = -1.0 / tau_s if tau_s > 0 else np.nan
        t0_s = fit['t0']
        offset = fit['offset']
        amplitude = fit['amplitude']

        equation = (
            f"T(t) = {offset:.6g} + ({amplitude:.6g})"
            f"*exp(-(t - {t0_s:.6g})/{tau_s:.6g})"
        )

        lines.append(
            f"Fit {fit['index']} bounds={fit['bounds']} s\n"
            f"{equation}\n"
            f"slope={slope_inv_s:.6g} 1/s, R2={fit['r2']:.5f}"
        )
    return '\n'.join(lines)


def parse_run_number(h5_path, fallback_idx):
    basename = os.path.basename(h5_path)

    match = re.match(r'^\d{4}-\d{2}-\d{2}_(\d+)_', basename)
    if match:
        return int(match.group(1))

    match = re.search(r'_(\d+)_', basename)
    if match:
        return int(match.group(1))

    return int(fallback_idx)


def parse_run_datetime(h5_path):
    """Read run timestamp from HDF5 metadata; fallback to file mtime."""
    candidates = []

    try:
        with h5py.File(h5_path, 'r') as f:
            for key in ('run time', 'run_time', 'runtime'):
                if key in f.attrs:
                    candidates.append(f.attrs[key])

            if 'globals' in f:
                globals_group = cast(Any, f['globals'])
                for key in ('run time', 'run_time', 'runtime'):
                    if key in globals_group.attrs:
                        candidates.append(globals_group.attrs[key])
    except Exception:
        pass

    for value in candidates:
        if isinstance(value, bytes):
            text = value.decode('utf-8', errors='ignore')
        else:
            text = str(value)

        text = text.strip()
        if not text:
            continue

        for fmt in (
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M:%S.%f',
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                pass

        try:
            return datetime.fromisoformat(text.replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            pass

    return datetime.fromtimestamp(os.path.getmtime(h5_path))


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


def extract_shot_mean_from_h5(h5_path, run_globals=None):
    if run_globals is None:
        run_globals = {}

    with h5py.File(h5_path, 'r') as f:
        try:
            ain_group = cast(Any, f['devices/ADwin/ANALOG_IN'])
            times_ds = cast(Any, f['devices/ADwin/ANALOG_IN/TIMES'])
            raw_data = cast(Any, f['data/traces/ADwinAnalogIn_DATA'])
        except Exception:
            return np.nan

        times_table = np.asarray(times_ds[:])
        ain_attrs = dict(ain_group.attrs)

        acquisitions_per_channel = times_table['stop_time'] - times_table['start_time']
        channels_with_data = np.where(acquisitions_per_channel > 0)[0]
        if len(channels_with_data) == 0:
            return np.nan

        acquisitions_with_data = acquisitions_per_channel[channels_with_data]
        offsets = np.concatenate(([0], np.cumsum(acquisitions_with_data)))

        channel_means = {}
        channel_counts = {}

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

            channel_means[label] = float(np.mean(values))
            channel_counts[label] = int(values.size)

        _, selected_mean = choose_tc_channel(channel_means, channel_counts, run_globals)
        return selected_mean


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


def get_shot_temperature(h5_path):
    run = lyse.Run(h5_path, no_write=True)

    try:
        return float(run.get_result('adwin_mean_voltage', 'shot_mean_temperature_C'))
    except Exception:
        pass

    try:
        voltage_v = float(run.get_result('adwin_mean_voltage', 'shot_mean_voltage_V'))
        return voltage_to_k_type_temperature_c(voltage_v, run.get_globals())
    except Exception:
        return np.nan


def main():
    df = lyse.data()
    if df is None or len(df) == 0:
        print('No shots available in lyse dataframe')
        return

    run_times = []
    temperatures_c = []
    num_missing = 0

    for idx, h5_path in enumerate(df.filepath.tolist()):
        temp_c = get_shot_temperature(h5_path)
        if np.isfinite(temp_c):
            run_times.append(parse_run_datetime(h5_path))
            temperatures_c.append(temp_c)
        else:
            num_missing += 1

    if not temperatures_c:
        print(
            'No ADwin thermocouple temperatures available for plotting '
            f'(checked {len(df)} shots; {num_missing} missing/invalid).'
        )
        return

    temperatures_c = np.asarray(temperatures_c, dtype=float)

    order = np.argsort(np.asarray(run_times, dtype='datetime64[ns]'))
    run_times = [run_times[i] for i in order]
    temperatures_c = temperatures_c[order]
    t_ref = run_times[0]
    elapsed_s = np.asarray([(rt - t_ref).total_seconds() for rt in run_times], dtype=float)

    fit_results = []
    if ENABLE_OFFSET_EXP_FITS and FIT_WINDOWS_SECONDS:
        fit_results = fit_offset_exp_windows(elapsed_s, temperatures_c, FIT_WINDOWS_SECONDS)

    plt.figure()
    plt.clf()
    plt.plot(run_times, temperatures_c, 'o-', linewidth=1.5, markersize=4, label='Data')

    for fit in fit_results:
        mask = fit['mask']
        t_window = elapsed_s[mask]
        if len(t_window) < 2:
            continue

        t_line = np.linspace(float(t_window[0]), float(t_window[-1]), 200)
        y_line = offset_exponential_decay(t_line - fit['t0'], fit['offset'], fit['amplitude'], fit['tau_s'])
        time_line = [t_ref + timedelta(seconds=float(ts)) for ts in t_line]

        tau_s = fit['tau_s']
        slope_inv_s = -1.0 / tau_s if tau_s > 0 else np.nan
        label = f"Fit {fit['index']}"
        plt.plot(time_line, y_line, '--', linewidth=2.0, label=label)

        print(
            f"[fit {fit['index']}] bounds_s={fit['bounds']}, N={int(np.count_nonzero(mask))}, "
            f"offset={fit['offset']:.6g}, amp={fit['amplitude']:.6g}, "
            f"tau_s={fit['tau_s']:.6g}, slope_1_per_s={slope_inv_s:.6g}, R2={fit['r2']:.5f}"
        )
    plt.xlabel('Run time')
    plt.ylabel('Temperature (degC)')
    plt.title(f'K-type thermocouple temperature per shot (N={len(temperatures_c)})')
    ax = plt.gca()
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
    plt.gcf().autofmt_xdate()
    plt.grid(True, alpha=0.3)
    if fit_results:
        fit_text = format_fit_parameters_text(fit_results)
        ax.text(
            0.02,
            0.98,
            fit_text,
            transform=ax.transAxes,
            va='top',
            ha='left',
            fontsize=8,
            bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.75, edgecolor='0.7'),
        )
        plt.legend(loc='best', fontsize=8)
    plt.tight_layout()
    plt.show()


if __name__ == '__main__':
    main()
