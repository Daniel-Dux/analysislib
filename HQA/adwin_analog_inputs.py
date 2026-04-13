"""
ADwin Analog Inputs Display Script for Lyse

This script extracts and displays all analog inputs recorded during the experiment
sequence. It reads the raw analog input data from the ADwin device, converts it to
voltages, and plots the values for each analog input channel.

Usage:
    Run this script in lyse after an experiment has been executed.
    It will generate plots showing all analog input traces.
"""

import lyse
import h5py
import numpy as np
import matplotlib.pyplot as plt
from functools import partial
from matplotlib.gridspec import GridSpec
from labscript_utils import properties
from user_devices.ADwinProII.ADwin_utils import DAC


def get_analog_inputs(h5_path):
    """
    Extract analog input data from the shot file.
    Only returns channels that actually have data measurements.
    
    Parameters
    ----------
    h5_path : str
        Path to the shot HDF5 file
        
    Returns
    -------
    dict
        Dictionary mapping input names to (times, values) tuples
    """
    analog_inputs = {}
    
    with h5py.File(h5_path, 'r') as f:
        # Check if ADwin device exists
        if 'devices/ADwin' not in f:
            print("Warning: ADwin device not found in the shot file")
            return analog_inputs
        
        adwin_group = f['devices/ADwin']
        
        # Check if analog input data exists
        if 'ANALOG_IN/TIMES' not in adwin_group:
            print("Warning: No ANALOG_IN/TIMES found")
            return analog_inputs
        
        if 'data/traces/ADwinAnalogIn_DATA' not in f:
            print("Warning: No data/traces/ADwinAnalogIn_DATA found")
            return analog_inputs
        
        times_table = adwin_group['ANALOG_IN/TIMES'][:]
        raw_data = f['data/traces/ADwinAnalogIn_DATA']
        ain_attrs = dict(adwin_group['ANALOG_IN'].attrs)
        
        # Get properties to calculate clock rate
        props = properties.get(f, 'ADwin', 'connection_table_properties')
        from user_devices.ADwinProII import CLOCK_T12
        clock_rate = CLOCK_T12 / props["PROCESSDELAY"]
        
        # Calculate which channels have data and split indices
        acquisitions_per_channel = times_table["stop_time"] - times_table["start_time"]
        channels_with_data = np.where(acquisitions_per_channel > 0)[0]
        
        if len(channels_with_data) == 0:
            print("Warning: No channels have data")
            return analog_inputs
        
        # Calculate split indices only for channels with data
        acquisitions_with_data = acquisitions_per_channel[channels_with_data]
        offsets = np.concatenate(([0], np.cumsum(acquisitions_with_data)))
        
        # Extract data for each channel with measurements
        for idx, channel_idx in enumerate(channels_with_data):
            start_idx = int(offsets[idx])
            stop_idx = int(offsets[idx + 1])
            if stop_idx <= start_idx:
                continue
            data_array = raw_data[start_idx:stop_idx]
            
            if not data_array.size:
                continue
            
            # Get channel label from attributes if it exists
            label_key = str(channel_idx + 1)
            if label_key in ain_attrs and isinstance(ain_attrs[label_key], (str, bytes)):
                label = ain_attrs[label_key]
                if isinstance(label, bytes):
                    label = label.decode('utf-8')
            else:
                label = f"AIN_{channel_idx + 1}"
            
            # Create time array for this channel
            start_time = times_table["start_time"][channel_idx]
            stop_time = times_table["stop_time"][channel_idx]
            times = np.arange(start_time, stop_time) / clock_rate
            
            # Get ADwin module properties for voltage conversion
            # ADwinAI8 has resolution_bits=16, min_V=-10, max_V=10
            resolution_bits = 16
            min_V = -10
            max_V = 10
            
            # Convert from digital values to voltages using DAC
            values = DAC(data_array, resolution=resolution_bits, min_V=min_V, max_V=max_V)
            
            # Apply gain mode correction if present
            if "gain_mode" in times_table.dtype.names:
                gain_mode = times_table["gain_mode"][channel_idx]
                values = values / (2 ** gain_mode)
            
            analog_inputs[label] = (times, values)
    
    return analog_inputs


def plot_analog_inputs(analog_inputs, output_path=None, max_points=5000):
    """
    Create a plot showing all analog inputs that have actual data.
    
    Parameters
    ----------
    analog_inputs : dict
        Dictionary mapping input names to (times, values) tuples
    output_path : str, optional
        Path to save the figure. If None, figure is not saved.
        
    Returns
    -------
    fig : matplotlib.figure.Figure
        The created figure object
    """
    if not analog_inputs:
        print("No analog input data to plot")
        return None
    
    num_channels = len(analog_inputs)
    num_cols = 2
    num_rows = (num_channels + num_cols - 1) // num_cols
    
    fig = plt.figure(figsize=(14, 3 * num_rows))
    gs = GridSpec(num_rows, num_cols, figure=fig, hspace=0.4, wspace=0.3)
    
    def update_line(ax, line, times_full, values_full):
        x_min, x_max = ax.get_xlim()
        if x_max <= x_min:
            return
        left = np.searchsorted(times_full, x_min, side='left')
        right = np.searchsorted(times_full, x_max, side='right')
        if right <= left:
            return
        times_view = times_full[left:right]
        values_view = values_full[left:right]
        if len(values_view) > max_points:
            stride = int(np.ceil(len(values_view) / max_points))
            times_view = times_view[::stride]
            values_view = values_view[::stride]
        line.set_data(times_view, values_view)
        ax.figure.canvas.draw_idle()

    for idx, (channel_name, (times, values)) in enumerate(sorted(analog_inputs.items())):
        row = idx // num_cols
        col = idx % num_cols
        ax = fig.add_subplot(gs[row, col])

        # Initial downsample for faster plotting/zooming
        if len(values) > max_points:
            stride = int(np.ceil(len(values) / max_points))
            times_plot = times[::stride]
            values_plot = values[::stride]
        else:
            times_plot = times
            values_plot = values

        # Plot the actual measurement values (no markers for speed)
        line = ax.plot(times_plot, values_plot, 'b-', linewidth=0.8, alpha=0.8)[0]
        line.set_rasterized(True)
        ax.set_xlabel('Time (s)')
        ax.set_ylabel('Value (V)')
        if len(values) > max_points:
            ax.set_title(f'{channel_name} ({len(values)} samples, decimated)')
        else:
            ax.set_title(f'{channel_name} ({len(values)} samples)')
        ax.grid(True, alpha=0.3)
        ax.callbacks.connect('xlim_changed', partial(update_line, line=line, times_full=times, values_full=values))
    
    fig.suptitle(f'ADwin Analog Inputs - {num_channels} channels', fontsize=16, fontweight='bold')
    
    if output_path:
        fig.savefig(output_path, dpi=150, bbox_inches='tight')
        print(f"Figure saved to: {output_path}")
    
    return fig


def main():
    """
    Main function to be called by lyse.
    """
    # Get the current shot file path
    try:
        h5_path = lyse.path
    except AttributeError:
        # If not in spinning top mode, get the filepath of the last shot
        df = lyse.data()
        h5_path = df.filepath.iloc[-1]
    
    print(f"Processing shot: {h5_path}")
    
    # Extract analog inputs
    analog_inputs = get_analog_inputs(h5_path)
    
    if analog_inputs:
        print(f"\nFound {len(analog_inputs)} analog input channels:")
        for channel_name in sorted(analog_inputs.keys()):
            times, values = analog_inputs[channel_name]
            print(f"  {channel_name}: sampled from {times[0]:.4f}s to {times[-1]:.4f}s")
        
        # Create and display plot
        fig = plot_analog_inputs(analog_inputs)
        plt.show()
    else:
        print("No analog input data found in the shot file")


if __name__ == "__main__":
    main()
