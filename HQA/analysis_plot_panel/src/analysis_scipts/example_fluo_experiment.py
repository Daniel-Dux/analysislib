"""
Example Experiment Script for Fluorescence Analysis with Background Subtraction

This demonstrates how to set up your labscript experiment to work with
the fluo_background_analysis.py script.

Key points:
1. Define ROI positions in globals
2. Take a single signal image per shot
3. Use record_background=True to record a new persistent background image
4. Use record_background=False (or omit) for normal analysis

Two modes:
A) Background Recording Mode: Record a new background image (one-time setup)
B) Normal Analysis Mode: Take signal images (standard operation)
"""

from labscript import *
from labscript_utils import import_or_reload

# Import your connection table
import_or_reload('labscriptlib.HQA.connection_table')

#################################################################
# Define Globals for ROI Configuration
#################################################################

# Signal ROI - where you expect your fluorescence signal (e.g., atom cloud)
fluo_signal_roi_center = [300, 300]  # [x, y] position in pixels
fluo_signal_roi_size = [100, 100]    # [width, height] in pixels

# Background ROI - region for background normalization (no signal)
fluo_bg_roi_center = [100, 100]      # [x, y] position in pixels
fluo_bg_roi_size = [50, 50]          # [width, height] in pixels

# Camera settings
MOT_fluo = True
MOT_fluo_exposure = 100e-3  # Exposure time in seconds

#################################################################
# Background Recording or Normal Analysis
#################################################################

# MODE A: Set to True to RECORD a new background image (one-time)
# MODE B: Set to False (or omit) for NORMAL analysis
record_background = False

#################################################################
# Experimental Sequence
#################################################################

start()

# Your experimental sequence here...
# Load atoms, cool, trap, etc.

t_image = 5.0  # Time when to take the image

#-----------------------------------------------------------------
# MODE A: Recording a Background Image
#-----------------------------------------------------------------
if record_background:
    """
    When recording a background:
    - Take image WITHOUT atoms
    - Ensure same light conditions as normal signal images
    - The analysis script will save this as the persistent background
    - After recording, set record_background=False for normal operation
    """
    
    # IMPORTANT: Remove/blast atoms before taking background
    # blast_beam.constant(t_image - 100e-3, power=1.0)
    # wait(50e-3)
    # blast_beam.constant(t_image - 50e-3, power=0.0)
    
    # Turn on fluorescence light (same settings as for signal!)
    # RedMOT_repump.constant(t_image, power=1.0)
    # RedMOT_cool.constant(t_image, power=0.5)
    
    # Take background image
    MOT_Counting.expose(
        t=t_image,
        name='signal',  # Use 'signal' as name even for background recording
        trigger_duration=MOT_fluo_exposure
    )
    
    print("=" * 60)
    print("BACKGROUND RECORDING MODE")
    print("After this shot completes:")
    print("1. Check lyse output to verify background was saved")
    print("2. Set record_background=False in this script")
    print("3. Continue with normal measurements")
    print("=" * 60)

#-----------------------------------------------------------------
# MODE B: Normal Analysis (with atoms)
#-----------------------------------------------------------------
else:
    """
    Normal operation:
    - Take image WITH atoms
    - The analysis script will load the saved background
    - Weighted background subtraction is applied automatically
    """
    
    # Atoms should be present at this point
    
    # Turn on fluorescence light
    # RedMOT_repump.constant(t_image, power=1.0)
    # RedMOT_cool.constant(t_image, power=0.5)
    
    # Take signal image
    MOT_Counting.expose(
        t=t_image,
        name='signal',
        trigger_duration=MOT_fluo_exposure
    )

# Turn off light
t_end = t_image + MOT_fluo_exposure + 10e-3

#-----------------------------------------------------------------
# End sequence
#-----------------------------------------------------------------

stop(t_end + 100e-3)

#################################################################
# Notes
#################################################################

"""
Important Considerations:

1. BACKGROUND RECORDING (record_background=True):
   - Take image WITHOUT atoms, but WITH fluorescence light on
   - Use IDENTICAL light conditions as your signal measurements
   - Same exposure time, power, detuning, etc.
   - The image is saved to: 
     analysislib/HQA/analysis_plot_panel/src/analysis_scipts/background_images/
   - Only needs to be done once (or when conditions change)

2. NORMAL ANALYSIS (record_background=False):
   - Take image WITH atoms
   - The saved background is automatically loaded
   - Fast operation - only one image per shot needed

3. WHEN TO RECORD A NEW BACKGROUND:
   - Initial setup
   - After changing light intensity
   - After changing camera settings (exposure, gain)
   - After optical realignment
   - If background has drifted over time
   - When using a different camera or ROI

4. IMAGE NAMING:
   - Always use name='signal' for the expose() call
   - The script handles both background recording and normal analysis
   - Alternative: name='atoms' also works

5. ROI SELECTION:
   - Signal ROI: Should cover entire region where signal might appear
   - Background ROI: Should be in a region with:
     * Similar illumination to signal region
     * No signal (no atoms)
     * Representative background intensity
     * Not too close to edges (avoid vignetting)

6. TESTING:
   - First record a background with record_background=True
   - Then run a test shot with record_background=False
   - Check in lyse with debug=True to verify ROI positions
   - Check that background weight factor is reasonable (typically 0.8 - 1.2)

7. WORKFLOW SUMMARY:
   
   INITIAL SETUP:
   a) Set record_background=True
   b) Run experiment WITHOUT atoms
   c) Check lyse confirms background saved
   d) Set record_background=False
   
   DAILY USE:
   e) Keep record_background=False
   f) Run normal experiments WITH atoms
   g) Analysis uses saved background automatically
   
   UPDATE BACKGROUND:
   h) Set record_background=True when needed
   i) Run one shot without atoms
   j) Set record_background=False
   k) Continue normal operation
"""
