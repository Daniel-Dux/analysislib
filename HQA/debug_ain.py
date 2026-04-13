"""Debug script to check ADwin analog input data structure"""

import h5py
import sys

h5_path = sys.argv[1] if len(sys.argv) > 1 else None

if not h5_path:
    print("Usage: python debug_ain.py <path_to_h5_file>")
    sys.exit(1)

with h5py.File(h5_path, 'r') as f:
    print(f"Root keys: {list(f.keys())}")
    
    if 'devices' in f:
        print(f"\ndevices keys: {list(f['devices'].keys())}")
        
        if 'ADwin' in f['devices']:
            adwin = f['devices/ADwin']
            print(f"\nADwin keys: {list(adwin.keys())}")
            print(f"ADwin attributes: {dict(adwin.attrs)}")
            
            if 'ANALOG_IN' in adwin:
                ain = adwin['ANALOG_IN']
                print(f"\nANALOG_IN keys: {list(ain.keys())}")
                print(f"ANALOG_IN attributes: {dict(ain.attrs)}")
                
                if 'TIMES' in ain:
                    print(f"\nANALOG_IN/TIMES shape: {ain['TIMES'].shape}")
                    print(f"ANALOG_IN/TIMES dtype: {ain['TIMES'].dtype}")
                    print(f"ANALOG_IN/TIMES first row: {ain['TIMES'][0]}")
    
    if 'data' in f:
        print(f"\ndata keys: {list(f['data'].keys())}")
        
        if 'traces' in f['data']:
            traces = f['data/traces']
            print(f"data/traces keys: {list(traces.keys())}")
            
            for key in traces.keys():
                print(f"  {key}: shape={traces[key].shape if hasattr(traces[key], 'shape') else 'N/A'}")
        
        if 'ANALOG_IN' in f['data']:
            print(f"\ndata/ANALOG_IN shape: {f['data/ANALOG_IN'].shape}")
            print(f"data/ANALOG_IN dtype: {f['data/ANALOG_IN'].dtype}")
