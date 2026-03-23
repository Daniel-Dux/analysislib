#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Diagnostic tool for checking combined file structure and data availability

Usage:
    python check_combined_file.py <combined_file.h5>
    
or in Python:
    from check_combined_file_diagnostic import check_combined_file
    check_combined_file('path/to/experiment.h5')
"""

import h5py
import os
import sys


def check_combined_file(combined_path):
    """
    Check if a combined file has the expected structure and data.
    
    Parameters
    ----------
    combined_path : str
        Path to the combined HDF5 file
    """
    print("\n" + "="*70)
    print(f"Checking combined file: {combined_path}")
    print("="*70)
    
    if not os.path.exists(combined_path):
        print(f"❌ ERROR: File does not exist: {combined_path}")
        return False
    
    try:
        with h5py.File(combined_path, 'r') as f:
            # Check for All Runs group
            if 'All Runs' not in f:
                print("❌ ERROR: 'All Runs' group not found in combined file")
                return False
            
            all_runs = f['All Runs']
            num_shots = len(all_runs)
            
            print(f"\n✓ Found 'All Runs' group with {num_shots} shots")
            print("\nShots in combined file:")
            print("-" * 70)
            
            for shot_name in sorted(all_runs.keys())[:10]:  # Show first 10
                shot_group = all_runs[shot_name]
                
                # Check for .dat dataset
                dat_files = [k for k in shot_group.keys() if k.endswith('.dat')]
                images_exist = 'Images' in shot_group
                
                # List image cameras
                cameras = []
                if images_exist:
                    cameras = list(shot_group['Images'].keys())
                
                # Count images per camera
                image_counts = {}
                if images_exist:
                    for cam in cameras:
                        cam_group = shot_group['Images'][cam]
                        image_counts[cam] = len(cam_group)
                
                dat_status = "✓" if dat_files else "✗"
                img_status = "✓" if images_exist else "✗"
                
                print(f"\n  {shot_name}")
                print(f"    {dat_status} Metadata (.dat): {len(dat_files)} files")
                if dat_files:
                    for dat in dat_files:
                        print(f"       - {dat}")
                print(f"    {img_status} Images: {', '.join(f'{cam}({image_counts[cam]})' for cam in cameras) if cameras else 'None'}")
            
            if num_shots > 10:
                print(f"\n  ... and {num_shots - 10} more shots")
            
            # Detailed check for first shot
            print("\n" + "="*70)
            if num_shots > 0:
                first_shot = list(all_runs.keys())[0]
                shot_group = all_runs[first_shot]
                
                print(f"Detailed check of first shot: {first_shot}")
                print("="*70)
                
                # Check metadata
                for dat_name in shot_group.keys():
                    if dat_name.endswith('.dat'):
                        dat_ds = shot_group[dat_name]
                        print(f"\nMetadata dataset: {dat_name}")
                        print(f"  Attributes ({len(dat_ds.attrs)} total):")
                        
                        # Show first 10 imaging results
                        imaging_results = [k for k in dat_ds.attrs.keys() if k.startswith('fluo_imaging')]
                        if imaging_results:
                            print(f"    Fluo imaging results ({len(imaging_results)}):")
                            for k in sorted(imaging_results)[:10]:
                                val = dat_ds.attrs[k]
                                print(f"      ✓ {k}: {str(val)[:50]}")
                            if len(imaging_results) > 10:
                                print(f"      ... and {len(imaging_results) - 10} more")
                        
                        absorption_results = [k for k in dat_ds.attrs.keys() if k.startswith('absorption_imaging')]
                        if absorption_results:
                            print(f"    Absorption imaging results ({len(absorption_results)}):")
                            for k in sorted(absorption_results)[:10]:
                                val = dat_ds.attrs[k]
                                print(f"      ✓ {k}: {str(val)[:50]}")
                            if len(absorption_results) > 10:
                                print(f"      ... and {len(absorption_results) - 10} more")
                
                # Check images
                if 'Images' in shot_group:
                    images_group = shot_group['Images']
                    print(f"\nImages group:")
                    for cam_name in images_group.keys():
                        cam_group = images_group[cam_name]
                        print(f"  Camera: {cam_name} ({len(cam_group)} images)")
                        for img_name in cam_group.keys():
                            img_ds = cam_group[img_name]
                            shape = img_ds.shape if hasattr(img_ds, 'shape') else 'unknown'
                            print(f"    ✓ {img_name}: {shape}")
            
            print("\n" + "="*70)
            print("✓ Combined file structure looks valid!")
            print("="*70 + "\n")
            return True
            
    except Exception as e:
        print(f"\n❌ ERROR reading file: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_combined_files(search_dir):
    """Find all combined files in a directory tree"""
    print(f"\nSearching for combined files in: {search_dir}")
    print("-" * 70)
    
    combined_files = []
    for root, dirs, files in os.walk(search_dir):
        for fname in files:
            if fname.endswith('.h5'):
                fpath = os.path.join(root, fname)
                try:
                    with h5py.File(fpath, 'r') as f:
                        if 'All Runs' in f:
                            num_shots = len(f['All Runs'])
                            combined_files.append((fpath, num_shots))
                            print(f"✓ {fpath}")
                            print(f"  → Contains {num_shots} shots")
                except Exception:
                    pass
    
    if not combined_files:
        print("No combined files found")
    
    return combined_files


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python check_combined_file_diagnostic.py <combined_file.h5>")
        print("   or: python check_combined_file_diagnostic.py --find <search_directory>")
        sys.exit(1)
    
    if sys.argv[1] == '--find':
        if len(sys.argv) < 3:
            search_dir = os.getcwd()
        else:
            search_dir = sys.argv[2]
        find_combined_files(search_dir)
    else:
        check_combined_file(sys.argv[1])
