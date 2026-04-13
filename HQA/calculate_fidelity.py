import lyse
import h5py
import numpy as np
import matplotlib.pyplot as plt

from fewfermions.analysis.function import fit_single_atom_intensity

def main():
    df = lyse.data()
    
    if df is None or len(df) == 0:
        print('No shots available in lyse dataframe')
        return
    
    print(df['fluo_background_analysis']['fluo_background_MOT_Counting_signal_sum'])
    
if __name__ == "__main__":
    main()