# -*- coding: utf-8 -*-
"""
Utilities for loading data from combined shot files created by single_shot_combine.py

This module provides functions to detect and work with combined HDF5 files that
aggregate results from multiple individual shot files. It allows data extractors
to load analysis results directly from these combined files instead of individual
shot files, reducing disk I/O and allowing shared data analysis.

@author: Assistant
"""

import os
import h5py
import json
import numpy as np
import logging

# Set up logging
logger = logging.getLogger(__name__)


def find_combined_file(h5_path, search_depth=3, verbose=False):
    """
    Find a combined file that contains data for the given shot file.
    
    Searches parent directories for combined .h5 files created by single_shot_combine.py
    that contain the shot's data.
    
    Parameters
    ----------
    h5_path : str
        Path to the individual shot file
    search_depth : int
        Number of directory levels to search upward (default: 3)
    verbose : bool
        If True, logs search progress and found files
    
    Returns
    -------
    str or None
        Path to combined file if found, None otherwise
    """
    if not isinstance(h5_path, str):
        return None
        
    shot_dir = os.path.dirname(h5_path)
    shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
    
    current_dir = shot_dir
    for depth_level in range(search_depth):
        parent_dir = os.path.dirname(current_dir)
        if parent_dir == current_dir:  # Reached filesystem root
            break
        
        if verbose:
            logger.debug(f"Searching for combined file in: {parent_dir}")
        
        # Look for .h5 files in parent directory
        try:
            for filename in os.listdir(parent_dir):
                if not filename.lower().endswith('.h5'):
                    continue
                combined_path = os.path.join(parent_dir, filename)
                
                # Check if file exists and is readable
                if not os.path.exists(combined_path):
                    continue
                
                # Check if this combined file contains our shot
                try:
                    with h5py.File(combined_path, 'r') as f:
                        if 'All Runs' in f and shot_basename in f['All Runs']:
                            if verbose:
                                logger.debug(f"Found combined file: {combined_path}")
                            return combined_path
                except Exception as e:
                    if verbose:
                        logger.debug(f"Could not read {combined_path}: {e}")
                    continue
        except Exception as e:
            if verbose:
                logger.debug(f"Error listing directory {parent_dir}: {e}")
        
        current_dir = parent_dir
    
    if verbose:
        logger.debug(f"No combined file found for {h5_path}")
    return None


def is_combined_file(h5_file):
    """
    Check if an HDF5 file is a combined file from single_shot_combine.py
    
    Parameters
    ----------
    h5_file : h5py.File or str
        HDF5 file object or path
    
    Returns
    -------
    bool
        True if file has 'All Runs' group structure
    """
    if isinstance(h5_file, str):
        try:
            with h5py.File(h5_file, 'r') as f:
                return 'All Runs' in f
        except Exception:
            return False
    else:
        return 'All Runs' in h5_file


def get_combined_file_result(h5_file, shot_basename, run_name, group_name, result_name):
    """
    Extract a result value from a combined file's dataset attributes.
    
    In combined files, results are stored as attributes on the dataset using the format:
    {group_name}/{result_name}
    
    Parameters
    ----------
    h5_file : h5py.File
        Open HDF5 file object
    shot_basename : str
        Name of the shot without extension (e.g., "2022-03-15_0001")
    run_name : str
        Run name used in the combined file (from globals)
    group_name : str
        Analysis group name (e.g., "fluo_imaging")
    result_name : str
        Name of the result (e.g., "MOT_Counting_Natoms")
    
    Returns
    -------
    scalar or None
        The result value if found, None otherwise
    """
    try:
        all_runs = h5_file['All Runs']
        if shot_basename not in all_runs:
            logger.debug(f"Shot {shot_basename} not found in combined file All Runs group")
            return None
        
        shot_group = all_runs[shot_basename]
        dataset_name = f"{run_name}.dat"
        
        if dataset_name not in shot_group:
            available_datasets = [k for k in shot_group.keys() if k.endswith('.dat')]
            logger.debug(f"Dataset {dataset_name} not found in {shot_basename}. Available: {available_datasets}")
            return None
        
        ds = shot_group[dataset_name]
        attr_name = f"{group_name}/{result_name}"
        
        if attr_name not in ds.attrs:
            logger.debug(f"Attribute {attr_name} not found in {dataset_name} for {shot_basename}")
            return None
        
        val = ds.attrs[attr_name]
        
        # Parse JSON if needed
        if isinstance(val, (str, bytes)):
            if isinstance(val, bytes):
                val = val.decode('utf-8')
            if val.startswith('{') or val.startswith('['):
                try:
                    return json.loads(val)
                except Exception:
                    return val
            logger.debug(f"Exception in get_combined_file_result for {shot_basename}/{group_name}/{result_name}", exc_info=True)
        return val
    except Exception:
        return None


def get_combined_file_result_array(h5_file, shot_basename, run_name, group_name, result_name):
    """
    Extract a result array from a combined file.
    
    Looks for array data in the Results group structure created by single_shot_combine.py.
    
    Parameters
    ----------
    h5_file : h5py.File
        Open HDF5 file object
    shot_basename : str
        Shot name without extension
    run_name : str
        Run name
    group_name : str
        Analysis group name
    result_name : str
        Name of the result
    
    Returns
    -------
    ndarray or None
        The array if available, None otherwise
    """
    try:
        all_runs = h5_file['All Runs']
        if shot_basename not in all_runs:
            return None
        
        shot_group = all_runs[shot_basename]
        
        # Check if Results group exists with the array data
        if 'Results' not in shot_group:
            return None
        
        results_group = shot_group['Results']
        if group_name not in results_group:
            return None
        
        grp_results = results_group[group_name]
        if result_name not in grp_results:
            return None
        
        array_ds = grp_results[result_name]
        if isinstance(array_ds, h5py.Dataset):
            return array_ds[()]
        
        return None
    except Exception:
        return None


def get_combined_file_image(h5_file, shot_basename, camera_name, image_name):
    """
    Extract an image dataset from a combined file.
    
    Parameters
    ----------
    h5_file : h5py.File
        Open HDF5 file object
    shot_basename : str
        Shot name without extension
    camera_name : str
        Camera or label name (e.g., "MOT_Counting")
    image_name : str
        Image name (e.g., "diff_image")
    
    Returns
    -------
    ndarray or None
        The image data if found, None otherwise
    """
    try:
        all_runs = h5_file['All Runs']
        if shot_basename not in all_runs:
            return None
        
        shot_group = all_runs[shot_basename]
        if 'Images' not in shot_group:
            return None
        
        images_group = shot_group['Images']
        if camera_name not in images_group:
            return None
        
        cam_group = images_group[camera_name]
        if image_name not in cam_group:
            return None
        
        return cam_group[image_name][:]
    except Exception:
        return None


def extract_from_combined_or_individual(h5_path, extract_func):
    """
    Wrapper function that tries to extract data from combined file first, then falls
    back to individual shot file.
    
    Parameters
    ----------
    h5_path : str
        Path to shot file
    extract_func : callable
        Function that takes (h5_file_path, is_combined) and returns extracted data.
        If is_combined=True, h5_file_path is a tuple (combined_file_path, shot_basename)
    
    Returns
    -------
    extracted data from extract_func, or None if both methods fail
    """
    shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
    
    # Try to find and use combined file
    combined_path = find_combined_file(h5_path)
    if combined_path:
        try:
            with h5py.File(combined_path, 'r') as f:
                if is_combined_file(f):
                    # Get run_name from shot globals or combined file
                    run_name = shot_basename
                    if 'All Runs' in f and shot_basename in f['All Runs']:
                        shot_group = f['All Runs'][shot_basename]
                        # Try to find the .dat dataset to get run_name
                        for name in shot_group.keys():
                            if name.endswith('.dat'):
                                run_name = name[:-4]  # Remove .dat extension
                                break
                    
                    result = extract_func(combined_path, shot_basename, run_name, True)
                    if result is not None:
                        return result
        except Exception:
            pass
    
    # Fallback to individual file
    return extract_func(h5_path, None, None, False)
