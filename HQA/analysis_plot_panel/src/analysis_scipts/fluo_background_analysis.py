"""
Fluorescence Analysis with Weighted Background Subtraction

This script analyzes fluorescence images with the following capabilities:
- Load a single signal image per shot
- Use a persistent background image stored on disk
- Record new background images via record_background=True in globals
- Weighted background subtraction based on background ROI
- ROI-based signal summation
- Compatible with the analysis plot panel

The background subtraction algorithm:
1. Load persistent background image from disk
2. Calculate sum in background ROI for both the signal image and background image
   (excluding pixels that overlap with the signal ROI)
3. Weight the background image so the background ROI sums match
4. Subtract the weighted background image from the signal image
5. Sum the signal in the signal ROI

Recording a new background:
1. Take an image without atoms (background conditions)
2. Set record_background=True in your experiment globals
3. Run this script once to save the background
4. Set record_background=False for normal analysis

Author: Analysis Plot Panel
Date: 2026-02-23
"""

import lyse
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import patches
from scipy.ndimage import gaussian_filter
from uncertainties import ufloat
import h5py
from pathlib import Path

#################################################################
# Load h5
#################################################################

# Is this script being run from within an interactive lyse session?
# Check by trying to access lyse.path
try:
    h5_path = lyse.path
except AttributeError:
    # If not in spinning top mode, get the filepath of the last shot of the lyse DataFrame
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

# Instantiate a lyse.Run object for this shot
run = lyse.Run(h5_path)

# Get a dictionary of the global variables used in this shot
run_globals = run.get_globals()

#################################################################
# Configuration
#################################################################

# Debug mode - set to True to show debug plots
debug = False

# Camera configuration
# Specify which camera to analyze
camera_name = 'MOT_Counting'  # Change this to your camera name

# ROI Configuration (in pixels)
# Signal ROI - region where you expect your signal (atoms, etc.)
signal_roi = {
    'x_center': 300,  # Center x position in pixels
    'y_center': 300,  # Center y position in pixels
    'width': 100,     # Width in pixels
    'height': 100     # Height in pixels
}

# Background ROI - region for background normalization
# This should be a region without signal but with similar background
background_roi = {
    'x_center': 100,  # Center x position in pixels
    'y_center': 100,  # Center y position in pixels
    'width': 50,      # Width in pixels
    'height': 50      # Height in pixels
}

# Try to load ROI settings from run_globals if available
try:
    if 'fluo_signal_roi_center' in run_globals:
        signal_roi['x_center'] = run_globals['fluo_signal_roi_center'][0]
        signal_roi['y_center'] = run_globals['fluo_signal_roi_center'][1]
    if 'fluo_signal_roi_size' in run_globals:
        signal_roi['width'] = run_globals['fluo_signal_roi_size'][0]
        signal_roi['height'] = run_globals['fluo_signal_roi_size'][1]
    if 'fluo_bg_roi_center' in run_globals:
        background_roi['x_center'] = run_globals['fluo_bg_roi_center'][0]
        background_roi['y_center'] = run_globals['fluo_bg_roi_center'][1]
    if 'fluo_bg_roi_size' in run_globals:
        background_roi['width'] = run_globals['fluo_bg_roi_size'][0]
        background_roi['height'] = run_globals['fluo_bg_roi_size'][1]
except Exception as e:
    print(f"Could not load ROI settings from globals, using defaults: {e}")

# Smoothing sigma for filtered images (set to 0 to disable)
smooth_sigma = 0

# Signal ROI masking in background calculation
# Set to True to exclude signal ROI pixels from background weight calculation
# Set to False to use the original behavior (all background ROI pixels)
# IMPORTANT: If your background ROI is separate from signal ROI, set this to False
# If your background ROI surrounds the signal ROI, set this to True
exclude_signal_from_background = run_globals.get('exclude_signal_from_background', True)

# Background recording mode
# Set 'record_background=True' in your experiment globals to record a new background
record_background = run_globals.get('record_background', False)

# Path for storing the persistent background image
# Stored in the same directory as the userlib
background_dir = Path(__file__).parent / 'background_images'
background_dir.mkdir(exist_ok=True)
background_file = background_dir / f'{camera_name}_background.npy'

#################################################################
# Helper Functions
#################################################################

def create_roi_slice(roi_dict):
    """
    Create slice objects for a ROI dictionary
    
    Args:
        roi_dict: Dictionary with 'x_center', 'y_center', 'width', 'height'
        
    Returns:
        tuple: (y_slice, x_slice) for array indexing
    """
    x_start = int(roi_dict['x_center'] - roi_dict['width'] / 2)
    x_end = int(roi_dict['x_center'] + roi_dict['width'] / 2)
    y_start = int(roi_dict['y_center'] - roi_dict['height'] / 2)
    y_end = int(roi_dict['y_center'] + roi_dict['height'] / 2)
    
    return slice(y_start, y_end), slice(x_start, x_end)

def roi_sum(image, roi_dict):
    """
    Calculate the sum of pixel values in a ROI
    
    Args:
        image: 2D numpy array
        roi_dict: Dictionary with 'x_center', 'y_center', 'width', 'height'
        
    Returns:
        float: Sum of pixel values in ROI
    """
    y_slice, x_slice = create_roi_slice(roi_dict)
    return np.sum(image[y_slice, x_slice])

def average_images(images):
    """
    Average a list of images
    
    Args:
        images: List of 2D numpy arrays
        
    Returns:
        numpy.ndarray: Averaged image
    """
    if len(images) == 0:
        return None
    
    images_array = np.array(images, dtype='float')
    return np.mean(images_array, axis=0)

def weighted_background_subtraction(signal_img, background_img, bg_roi_dict, signal_roi_dict=None):
    """
    Subtract background with weighting based on background ROI
    
    The background image is weighted so that the sum in the background ROI
    of the background image equals the sum in the background ROI of the signal image.
    
    If a signal_roi_dict is provided, pixels within the signal ROI are excluded
    from the background ROI sum calculation to avoid contamination from signal.
    
    Args:
        signal_img: 2D numpy array of signal image
        background_img: 2D numpy array of background image
        bg_roi_dict: Dictionary defining the background ROI
        signal_roi_dict: Optional dictionary defining the signal ROI.
                        If provided, pixels in this ROI are excluded from
                        the background weight calculation.
        
    Returns:
        tuple: (corrected_image, weight_factor)
    """
    # Create mask for background ROI calculation
    if signal_roi_dict is not None:
        # Create a mask that excludes signal ROI pixels from background ROI
        mask = np.ones_like(signal_img, dtype=bool)
        
        # Set signal ROI pixels to False in the mask
        sig_y_slice, sig_x_slice = create_roi_slice(signal_roi_dict)
        mask[sig_y_slice, sig_x_slice] = False
        
        # Get background ROI slices
        bg_y_slice, bg_x_slice = create_roi_slice(bg_roi_dict)
        
        # Extract background ROI region and apply mask
        signal_bg_region = signal_img[bg_y_slice, bg_x_slice]
        background_region = background_img[bg_y_slice, bg_x_slice]
        mask_region = mask[bg_y_slice, bg_x_slice]
        
        # Check if enough pixels remain after masking
        n_excluded = np.sum(~mask_region)
        n_total_bg_roi = np.prod(signal_bg_region.shape)
        n_used = np.sum(mask_region)
        
        # print(f"Background weight calculation details:")
        # print(f"  Background ROI total pixels: {n_total_bg_roi}")
        # print(f"  Pixels excluded (signal ROI overlap): {n_excluded}")
        # print(f"  Pixels used for calculation: {n_used}")
        
        # Require at least 10% of pixels to remain for stable calculation
        min_pixels_required = max(100, int(0.1 * n_total_bg_roi))
        if n_used < min_pixels_required:
            print(f"WARNING: Only {n_used} pixels remain after excluding signal ROI.")
            print(f"         This may lead to unstable weight calculation.")
            print(f"         Consider using a background ROI that does not overlap with signal ROI.")
            print(f"         Falling back to using all background ROI pixels (no masking).")
            
            # Fall back to no masking if too few pixels remain
            signal_bg_sum = np.sum(signal_bg_region)
            background_sum = np.sum(background_region)
        else:
            # Calculate sums only for unmasked pixels
            signal_bg_sum = np.sum(signal_bg_region[mask_region])
            background_sum = np.sum(background_region[mask_region])
        
        # print(f"  Signal image background ROI sum: {signal_bg_sum:.1f}")
        # print(f"  Background image background ROI sum: {background_sum:.1f}")
        
        # For comparison, calculate what it would have been without masking
        if n_used >= min_pixels_required:
            signal_bg_sum_nomask = np.sum(signal_bg_region)
            background_sum_nomask = np.sum(background_region)
            weight_nomask = signal_bg_sum_nomask / background_sum_nomask if background_sum_nomask != 0 else 0
            # print(f"  (Without masking: signal_sum={signal_bg_sum_nomask:.1f}, "
            #       f"bg_sum={background_sum_nomask:.1f}, weight={weight_nomask:.4f})")
    else:
        # Original behavior: use all pixels in background ROI
        signal_bg_sum = roi_sum(signal_img, bg_roi_dict)
        background_sum = roi_sum(background_img, bg_roi_dict)
    
    # Calculate weight factor
    if background_sum != 0:
        weight = signal_bg_sum / background_sum
    else:
        weight = 0
        print("Warning: Background sum is zero, setting weight to 0")
    
    # Apply weighted subtraction
    corrected = signal_img - weight * background_img
    
    return corrected, weight

def draw_roi_rectangle(ax, roi_dict, color='r', label=None):
    """
    Draw a rectangle representing the ROI on a matplotlib axis
    
    Args:
        ax: Matplotlib axis
        roi_dict: Dictionary with 'x_center', 'y_center', 'width', 'height'
        color: Color of the rectangle
        label: Label for the rectangle
    """
    x_start = roi_dict['x_center'] - roi_dict['width'] / 2
    y_start = roi_dict['y_center'] - roi_dict['height'] / 2
    
    rect = patches.Rectangle(
        (x_start, y_start),
        roi_dict['width'],
        roi_dict['height'],
        linewidth=2,
        edgecolor=color,
        facecolor='none',
        label=label
    )
    ax.add_patch(rect)

#################################################################
# Image Loading
#################################################################

# print(f"Analyzing fluorescence data from camera: {camera_name}")
# print(f"Record background mode: {record_background}")

# Get all available image labels
try:
    all_labels = run.get_all_image_labels()  # No arguments!
    # print(f"\nAvailable orientations and labels in HDF5 file:")
    # for orientation, labels in all_labels.items():
    #     print(f"  Orientation '{orientation}': {labels}")
    # print(f"\nLooking for images from camera: '{camera_name}'")
except Exception as e:
    print(f"Warning: Could not get image labels: {e}")
    all_labels = {}

# Load signal image (single image per shot)
# Try different orientations and labels automatically
# The structure is: /images/orientation/label/image_name
# For run.get_images(orientation, label, *image_names)
signal_image = None
found_orientation = None
found_label = None
found_image_name = None
background_avg = None
background_std = None

# List of possible image names to try (the actual image identifier)
possible_image_names = [camera_name, 'signal', 'atoms', 'image', '0']

# First, try to use the discovered labels from get_all_image_labels()
# and discover what image names are available
if all_labels:
    # print("\nDiscovering available image names in HDF5 structure...")
    try:
        with h5py.File(h5_path, 'r') as f:
            if 'images' in f:
                images_group = f['images']
                for orientation in list(all_labels.keys()):
                    if orientation in images_group:
                        ori_group = images_group[orientation]
                        for label in all_labels.get(orientation, []):
                            if label in ori_group:
                                label_group = ori_group[label]
                                available_image_names = [key for key in label_group.keys() 
                                                        if isinstance(label_group[key], h5py.Dataset)]
                                if available_image_names:
                                    # print(f"  {orientation}/{label}: images = {available_image_names}")
                                    # Try to load from the available images
                                    for image_name in available_image_names:
                                        try:
                                            # print(f"Trying: orientation='{orientation}', label='{label}', image_name='{image_name}'")
                                            signal_image = run.get_images(orientation, label, image_name)[0]
                                            signal_image = np.array(signal_image, dtype='float')
                                            found_orientation = orientation
                                            found_label = label
                                            found_image_name = image_name
                                            # print(f"✓ Successfully loaded image!")
                                            # print(f"  Orientation: '{found_orientation}'")
                                            # print(f"  Label: '{found_label}'")
                                            # print(f"  Image name: '{found_image_name}'")
                                            # print(f"  Shape: {signal_image.shape}")
                                            break
                                        except Exception as e:
                                            print(f"  × Failed: {e}")
                                            continue
                                    if signal_image is not None:
                                        break
                        if signal_image is not None:
                            break
                    if signal_image is not None:
                        break
    except Exception as e:
        print(f"Warning: Could not discover image names via h5py: {e}")

# If discovery didn't work, try using the possible names
if signal_image is None:
    # print("\nTrying with standard image names...")
    for orientation, labels in all_labels.items():
        if labels:  # If there are any labels for this orientation
            for label in labels:
                # Try the possible image names
                for image_name in possible_image_names:
                    try:
                        # print(f"Trying: orientation='{orientation}', label='{label}', image_name='{image_name}'")
                        signal_image = run.get_images(orientation, label, image_name)[0]
                        signal_image = np.array(signal_image, dtype='float')
                        found_orientation = orientation
                        found_label = label
                        found_image_name = image_name
                        # print(f"✓ Successfully loaded image!")
                        # print(f"  Orientation: '{found_orientation}'")
                        # print(f"  Label: '{found_label}'")
                        # print(f"  Image name: '{found_image_name}'")
                        # print(f"  Shape: {signal_image.shape}")
                        break
                    except Exception as e:
                        # Suppress verbose error messages during standard attempts
                        continue
                if signal_image is not None:
                    break
        if signal_image is not None:
            break

# If that didn't work, try common combinations manually
if signal_image is None:
    # print("\nTrying common combinations with standard orientations...")
    # Common orientations that might exist
    common_orientations = ['PoC6', camera_name, 'fluorescence', 'MOT_Counting']
    common_labels = [camera_name, 'signal', 'atoms', 'exposure', 'image']
    
    for orientation in common_orientations:
        for label in common_labels:
            for image_name in possible_image_names:
                try:
                    # print(f"Trying: orientation='{orientation}', label='{label}', image='{image_name}'")
                    signal_image = run.get_images(orientation, label, image_name)[0]
                    signal_image = np.array(signal_image, dtype='float')
                    found_orientation = orientation
                    found_label = label
                    found_image_name = image_name
                    # print(f"✓ Successfully loaded image!")
                    # print(f"  Orientation: '{found_orientation}'")
                    # print(f"  Label: '{found_label}'")
                    # print(f"  Image name: '{found_image_name}'")
                    # print(f"  Shape: {signal_image.shape}")
                    break
                except Exception as e:
                    # Only print if it's not the generic "not found" error
                    if "orientation" not in str(e).lower() or orientation in str(e):
                        pass  # Skip printing every single attempt
                    continue
            if signal_image is not None:
                break
        if signal_image is not None:
            break

# Check if we successfully loaded an image
if signal_image is None:
    print("\n" + "="*60)
    print("ERROR: Could not load signal image")
    print("="*60)
    print(f"Camera name: '{camera_name}'")
    print("\nHDF5 structure is: /images/orientation/label/image_name")
    print("\nAvailable orientations and labels:")
    if all_labels:
        for orientation, labels in all_labels.items():
            print(f"  Orientation '{orientation}' has labels: {labels}")
    else:
        print("  Could not retrieve available labels")
    
    # Try to provide more detailed debugging by inspecting actual HDF5 structure
    print("\nDetailed HDF5 structure inspection:")
    try:
        with h5py.File(h5_path, 'r') as f:
            if 'images' in f:
                images_group = f['images']
                for orientation in images_group.keys():
                    print(f"  /images/{orientation}/")
                    ori_group = images_group[orientation]
                    for label in ori_group.keys():
                        print(f"    /images/{orientation}/{label}/")
                        label_group = ori_group[label]
                        image_names = list(label_group.keys())
                        if image_names:
                            print(f"      Image names: {image_names}")
                        else:
                            print(f"      (No image datasets found)")
                            # Check if there are subgroups
                            for subkey in label_group.keys():
                                subitem = label_group[subkey]
                                print(f"        └─ {subkey} ({type(subitem).__name__})")
            else:
                print("  No '/images' group found in HDF5 file")
    except Exception as e:
        print(f"  Could not inspect HDF5 structure: {e}")
    
    print("\nPlease check:")
    print("1. Camera name in script matches the camera in your experiment")
    print("2. Images were actually taken during the experiment")
    print("3. Check the HDF5 file structure with HDFView or h5py")
    print("\nTo debug, try this in Python:")
    print("  import lyse")
    print("  run = lyse.Run('your_file.h5')")
    print("  print(run.get_all_image_labels())")
    print("  import h5py")
    print("  with h5py.File('your_file.h5', 'r') as f:")
    print("      print(f['images'].keys())")
    print("="*60)
    
    # Raise exception instead of sys.exit() to allow proper error handling
    raise RuntimeError("Could not load signal image from HDF5 file")

#################################################################
# Background Recording or Loading
#################################################################

# Flag to track if we should continue with analysis
skip_analysis = False
save_zero_results = False
skip_reason = None

if record_background:
    # Record new background mode: Save current image as background
    print("\n" + "="*60)
    print("RECORDING NEW BACKGROUND IMAGE")
    print("="*60)
    
    background_avg = signal_image.copy()
    
    # Save background to file
    try:
        np.save(background_file, background_avg)
        # print(f"Saved new background image to: {background_file}")
        # print(f"Background image shape: {background_avg.shape}")
        # print(f"Background image mean: {np.mean(background_avg):.2f}")
        # print(f"Background image std: {np.std(background_avg):.2f}")
        
        # Save metadata
        metadata_file = background_file.with_suffix('.json')
        metadata = {
            'camera_name': camera_name,
            'orientation': found_orientation,
            'label': found_label,
            'image_name': found_image_name,
            'shape': list(background_avg.shape),
            'mean': float(np.mean(background_avg)),
            'std': float(np.std(background_avg)),
            'recorded_from': h5_path,
            'timestamp': str(Path(h5_path).stat().st_mtime)
        }
        import json
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        print(f"Saved metadata to: {metadata_file}")
        
        # Save result flag
        run.save_result('fluo_background_'+f'{camera_name}_background_recorded', True)
        run.save_result('fluo_background_'+f'{camera_name}_background_mean', np.mean(background_avg))
        
        # print("\n" + "="*60)
        # print("Background recording complete!")
        # print("Set record_background=False in globals for normal analysis.")
        # print("="*60)
        
        # Skip further analysis after recording background
        skip_analysis = True
        
    except Exception as e:
        print(f"ERROR: Failed to save background image: {e}")
        raise RuntimeError(f"Failed to save background image: {e}")
        
else:
    # Normal mode: Load existing background from file
    # print(f"\nLoading background image from: {background_file}")
    
    if background_file.exists():
        try:
            background_avg = np.load(background_file)
            # print(f"Loaded background image, shape: {background_avg.shape}")
            
            # Load and display metadata if available
            metadata_file = background_file.with_suffix('.json')
            if metadata_file.exists():
                import json
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                # print(f"Background info:")
                # print(f"  Recorded from: {Path(metadata['recorded_from']).name}")
                # print(f"  Orientation: '{metadata.get('orientation', 'unknown')}'")
                # print(f"  Label: '{metadata.get('label', 'unknown')}'")
                # print(f"  Image name: '{metadata.get('image_name', 'unknown')}'")
                # print(f"  Mean value: {metadata['mean']:.2f}")
                # print(f"  Std dev: {metadata.get('std', 0):.2f}")
            
            # Check if shapes match
            if background_avg.shape != signal_image.shape:
                print(f"WARNING: Background shape {background_avg.shape} does not match signal shape {signal_image.shape}")
                print("Please record a new background image with record_background=True")
                if signal_image.size == 0 or signal_image.ndim < 2:
                    skip_reason = (
                        f"Invalid signal image shape {signal_image.shape}; "
                        "ignoring shot and writing zero-valued results"
                    )
                    print(f"WARNING: {skip_reason}")
                    save_zero_results = True
                    skip_analysis = True
                else:
                    raise RuntimeError(f"Background shape {background_avg.shape} does not match signal shape {signal_image.shape}")
            
            background_std = None  # No std available from single stored background
            
        except Exception as e:
            print(f"ERROR: Failed to load background image: {e}")
            if signal_image is not None and (signal_image.size == 0 or signal_image.ndim < 2):
                skip_reason = f"Failed to load compatible background for invalid signal image shape {signal_image.shape}"
                print(f"WARNING: {skip_reason}")
                print("Ignoring this shot and writing zero-valued results")
                save_zero_results = True
                skip_analysis = True
            else:
                print("Please record a background image first by setting record_background=True in globals")
                raise RuntimeError(f"Failed to load background image: {e}")
    else:
        print(f"ERROR: Background file not found: {background_file}")
        print("Please record a background image first by setting record_background=True in globals")
        print("\nTo record a background:")
        print("1. Take an image without atoms (same conditions as signal)")
        print("2. Set record_background=True in your experiment globals")
        print("3. Run this analysis script once")
        print("4. Set record_background=False for normal analysis")
        raise RuntimeError(f"Background file not found. Please record a background image first.")

if save_zero_results:
    print("\nSaving zero-valued fallback results for ignored shot...")
    zero_shape = (10, 10)
    if isinstance(background_avg, np.ndarray) and background_avg.ndim == 2 and background_avg.size > 0:
        zero_shape = background_avg.shape
    elif isinstance(signal_image, np.ndarray) and signal_image.ndim == 2 and signal_image.size > 0:
        zero_shape = signal_image.shape

    corrected_image = np.zeros(zero_shape, dtype=float)
    background_avg = np.zeros(zero_shape, dtype=float)

    run.save_result('fluo_background_'+f'{camera_name}_signal_sum', 0.0)
    run.save_result('fluo_background_'+f'{camera_name}_signal_uncertainty', 0.0)
    run.save_result('fluo_background_'+f'{camera_name}_signal_sum_smooth', 0.0)
    run.save_result('fluo_background_'+f'{camera_name}_bg_weight_factor', 0.0)
    run.save_result('fluo_background_'+f'{camera_name}_Natoms', 0.0)
    run.save_result('fluo_background_'+f'{camera_name}_Natoms_err', 0.0)
    run.save_result('fluo_background_'+f'{camera_name}_single_atom_intensity', 0.0)

    run.save_result('fluo_background_'+f'{camera_name}_orientation', found_orientation or '')
    run.save_result('fluo_background_'+f'{camera_name}_label', found_label or '')
    run.save_result('fluo_background_'+f'{camera_name}_image_name', found_image_name or '')
    run.save_result('fluo_background_'+f'{camera_name}_shot_ignored', True)
    run.save_result('fluo_background_'+f'{camera_name}_ignored_reason', skip_reason or 'unknown')

    run.save_result_array('fluo_background_'+f'{camera_name}_corrected_image', corrected_image)
    run.save_result_array('fluo_background_'+f'{camera_name}_background_avg', background_avg)

    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_x', signal_roi['x_center'])
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_y', signal_roi['y_center'])
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_width', signal_roi['width'])
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_height', signal_roi['height'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_x', background_roi['x_center'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_y', background_roi['y_center'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_width', background_roi['width'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_height', background_roi['height'])

    print("Saved zero-valued results and skipped analysis for this shot.")

# Only continue with analysis if not just recording background
if not skip_analysis:
    if background_avg is None:
        raise RuntimeError("Background image is not available for analysis")

    #################################################################
    # Weighted Background Subtraction
    #################################################################

    # print("\nPerforming weighted background subtraction...")
    # print(f"Background ROI: center=({background_roi['x_center']}, {background_roi['y_center']}), "
    #       f"size=({background_roi['width']}x{background_roi['height']})")
    # print(f"Exclude signal ROI from background calculation: {exclude_signal_from_background}")

    corrected_image, weight_factor = weighted_background_subtraction(
        signal_image, 
        background_avg, 
        background_roi,
        signal_roi if exclude_signal_from_background else None
    )

    # print(f"Background weight factor: {weight_factor:.4f}")

    #################################################################
    # Signal Extraction from ROI
    #################################################################

    # print(f"\nExtracting signal from ROI...")
    # print(f"Signal ROI: center=({signal_roi['x_center']}, {signal_roi['y_center']}), "
    #       f"size=({signal_roi['width']}x{signal_roi['height']})")

    # Calculate signal sum in the signal ROI
    signal_sum = roi_sum(corrected_image, signal_roi)

    # Estimate uncertainty from background variation
    if background_std is not None:
        # Propagate uncertainty from background variation
        y_slice, x_slice = create_roi_slice(signal_roi)
        bg_uncertainty = np.sqrt(np.sum(background_std[y_slice, x_slice]**2))
    else:
        # Estimate from shot noise in background ROI
        bg_roi_y, bg_roi_x = create_roi_slice(background_roi)
        bg_variance = np.var(corrected_image[bg_roi_y, bg_roi_x])
        # Scale by ROI size
        n_pixels_signal = signal_roi['width'] * signal_roi['height']
        bg_uncertainty = np.sqrt(bg_variance * n_pixels_signal)

    signal_sum_ufloat = ufloat(signal_sum, bg_uncertainty)

    # print(f"Signal sum: {signal_sum_ufloat}")

    #################################################################
    # Calculate atom number from signal
    #################################################################
    
    # Get single atom intensity from globals
    if 'single_atom_intensity' in run_globals:
        single_atom_intensity = run_globals['single_atom_intensity']
        # print(f"\nSingle atom intensity: {single_atom_intensity}")
        
        # Calculate atom number with uncertainty propagation
        N_atoms = signal_sum_ufloat / single_atom_intensity
        
        print(f"Calculated atom number: {N_atoms}")
    else:
        print("\nWarning: 'single_atom_intensity' not found in globals. Atom number not calculated.")
        N_atoms = None
        single_atom_intensity = None

    #################################################################
    # Optional: Apply smoothing filter
    #################################################################

    if smooth_sigma > 0:
        corrected_smooth = gaussian_filter(corrected_image, sigma=smooth_sigma)
        signal_sum_smooth = roi_sum(corrected_smooth, signal_roi)
    else:
        corrected_smooth = corrected_image
        signal_sum_smooth = signal_sum

    #################################################################
    # Save Results
    #################################################################

    print("\nSaving results...")

    # Save main results
    run.save_result('fluo_background_'+f'{camera_name}_signal_sum', float(signal_sum))
    run.save_result('fluo_background_'+f'{camera_name}_signal_uncertainty', bg_uncertainty)
    run.save_result('fluo_background_'+f'{camera_name}_signal_sum_smooth', signal_sum_smooth)
    run.save_result('fluo_background_'+f'{camera_name}_bg_weight_factor', weight_factor)
    
    # Save atom number if calculated
    if N_atoms is not None:
        run.save_result('fluo_background_'+f'{camera_name}_Natoms', N_atoms.n)
        run.save_result('fluo_background_'+f'{camera_name}_Natoms_err', N_atoms.std_dev)
        run.save_result('fluo_background_'+f'{camera_name}_single_atom_intensity', single_atom_intensity)

    # Save image acquisition info
    run.save_result('fluo_background_'+f'{camera_name}_orientation', found_orientation)
    run.save_result('fluo_background_'+f'{camera_name}_label', found_label)
    run.save_result('fluo_background_'+f'{camera_name}_image_name', found_image_name)

    # Save processed images
    run.save_result_array('fluo_background_'+f'{camera_name}_corrected_image', corrected_image)
    run.save_result_array('fluo_background_'+f'{camera_name}_background_avg', background_avg)

    if smooth_sigma > 0:
        run.save_result_array('fluo_background_'+f'{camera_name}_corrected_smooth', corrected_smooth)

    # Save ROI information
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_x', signal_roi['x_center'])
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_y', signal_roi['y_center'])
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_width', signal_roi['width'])
    run.save_result('fluo_background_'+f'{camera_name}_signal_roi_height', signal_roi['height'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_x', background_roi['x_center'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_y', background_roi['y_center'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_width', background_roi['width'])
    run.save_result('fluo_background_'+f'{camera_name}_bg_roi_height', background_roi['height'])

    print("Results saved successfully!")

    #################################################################
    # Debug Visualization
    #################################################################

    if debug:
        print("\nGenerating debug plots...")
        
        # Create figure with subplots
        fig, axes = plt.subplots(2, 3, figsize=(15, 10))
        fig.suptitle(f'Fluorescence Analysis Debug - {camera_name}', fontsize=16)
        
        # 1. Raw signal image
        ax = axes[0, 0]
        im = ax.imshow(signal_image, cmap='viridis')
        ax.set_title('Raw Signal Image')
        draw_roi_rectangle(ax, signal_roi, 'r', 'Signal ROI')
        draw_roi_rectangle(ax, background_roi, 'b', 'Background ROI')
        ax.legend()
        plt.colorbar(im, ax=ax)
        
        # 2. Averaged background
        ax = axes[0, 1]
        im = ax.imshow(background_avg, cmap='viridis')
        ax.set_title('Background Image (from file)')
        draw_roi_rectangle(ax, signal_roi, 'r', 'Signal ROI')
        draw_roi_rectangle(ax, background_roi, 'b', 'Background ROI')
        plt.colorbar(im, ax=ax)
        
        # 3. Weighted background
        ax = axes[0, 2]
        im = ax.imshow(background_avg * weight_factor, cmap='viridis')
        ax.set_title(f'Weighted Background (×{weight_factor:.3f})')
        draw_roi_rectangle(ax, background_roi, 'b', 'Background ROI')
        plt.colorbar(im, ax=ax)
        
        # 4. Corrected image
        ax = axes[1, 0]
        im = ax.imshow(corrected_image, cmap='viridis')
        ax.set_title('Background-Subtracted Image')
        draw_roi_rectangle(ax, signal_roi, 'r', 'Signal ROI')
        ax.legend()
        plt.colorbar(im, ax=ax)
        
        # 5. Smoothed corrected image
        ax = axes[1, 1]
        im = ax.imshow(corrected_smooth, cmap='viridis')
        ax.set_title(f'Smoothed (σ={smooth_sigma})')
        draw_roi_rectangle(ax, signal_roi, 'r', 'Signal ROI')
        plt.colorbar(im, ax=ax)
        
        # 6. Signal ROI zoom
        ax = axes[1, 2]
        y_slice, x_slice = create_roi_slice(signal_roi)
        im = ax.imshow(corrected_image[y_slice, x_slice], cmap='viridis')
        ax.set_title(f'Signal ROI (sum={signal_sum:.1f})')
        plt.colorbar(im, ax=ax)
        
        plt.tight_layout()
        plt.show()
        
        # Additional plot: 1D profiles
        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        fig.suptitle('1D Profiles through Signal ROI', fontsize=14)
        
        y_slice, x_slice = create_roi_slice(signal_roi)
        roi_data = corrected_image[y_slice, x_slice]
        
        # Horizontal profile (average over vertical)
        ax = axes[0]
        profile_x = np.mean(roi_data, axis=0)
        ax.plot(profile_x)
        ax.set_xlabel('X pixel')
        ax.set_ylabel('Average counts')
        ax.set_title('Horizontal Profile')
        ax.grid(True)
        
        # Vertical profile (average over horizontal)
        ax = axes[1]
        profile_y = np.mean(roi_data, axis=1)
        ax.plot(profile_y)
        ax.set_xlabel('Y pixel')
        ax.set_ylabel('Average counts')
        ax.set_title('Vertical Profile')
        ax.grid(True)
        
        plt.tight_layout()
        plt.show()
        
        print("Debug plots displayed")

    print("\n" + "="*60)
    print("Fluorescence analysis complete!")
    print("="*60)

else:
    # Background recording mode - just exit gracefully
    print("\n" + "="*60)
    print("Fluorescence analysis complete!")
    print("="*60)
