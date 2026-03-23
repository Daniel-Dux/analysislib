# Combined File Support - Usage Example

## Setup Instructions

The combined file support is **automatically enabled** - no configuration is needed!

## Example Workflow

### 1. Run Your Experiment
Run your experiment normally with the analysis routines. The individual shot files are created with all their analysis results.

```
2026-03-18/
├── 0001_experiment.h5
├── 0002_experiment.h5
├── 0003_experiment.h5
└── ... (more shots)
```

### 2. Create Combined File
After your experiment, run `single_shot_combine.py` to aggregate data:

```python
# In lyse or as a standalone script
from analysislib.HQA.combine_shots.single_shot_combine import main
combined_path = main()
print(f"Combined file created: {combined_path}")
```

This creates a combined file in the parent directory:

```
2026-03/
├── experiment.h5       (combined file with all shots)
2026-03-18/
├── 0001_experiment.h5
├── 0002_experiment.h5
├── 0003_experiment.h5
```

### 3. Load Analysis in Plot Panel
The analysis plot panel will automatically detect and use the combined file:

```python
# In analysis_plot_panel_lyse_routine.py
# No changes needed - just use normally!
fm.ap.add_plot_dock(plot_name, ip, FluoDataExtractor('fluo_imaging', 'MOT_Counting'))
```

When the panel loads data:
1. ✓ Checks for combined file in parent directories
2. ✓ Loads results and images from combined file if found
3. ✓ Falls back to individual file if needed

## What Gets Loaded from Combined File?

### Results (Attributes)
All scalar analysis results are stored as dataset attributes:
- Atom counts and uncertainties
- Trap parameters (sx, sy, cx, cy)
- Axis calibration
- Warning messages

### Images
All image data is stored in the Images hierarchy:
- Difference images
- OD (optical density) images
- Summed projections (xsum, ysum)
- Fit data (xfit, yfit)
- Grid coordinates (xgrid, ygrid)

## When Combined File Loading Helps

**Significant performance improvement when:**
- Analyzing sequences of 50+ shots
- Combined file is stored on fast storage
- Multiple analysis panels open simultaneously
- Working with high-resolution images

**Minimal benefit when:**
- Only analyzing individual shots
- Individual files are already cached
- Data rarely accessed from same run

## Monitoring / Debugging

To see if combined file loading is working, you can add this to your analysis routine:

```python
import os
from analysislib.HQA.analysis_plot_panel.src.analysis_plot_panel.combined_file_utils import find_combined_file

h5_path = lyse.path if hasattr(lyse, 'path') else lyse.data().filepath.iloc[-1]
combined = find_combined_file(h5_path)

if combined:
    print(f"✓ Using combined file: {combined}")
else:
    print(f"✗ No combined file found, using individual file: {h5_path}")
```

## Disabling Combined File Loading

If you need to force loading from individual files only, you can:

1. **Temporarily**: Delete the combined file
2. **Permanently**: Remove the import and calls to `find_combined_file()` in the extractors

## Troubleshooting

### "No images in combined file"
Check that `single_shot_combine.py` is:
- Being run AFTER analysis is complete
- Actually copying images (should see `Images/` group in combined file)

Use h5py to inspect:
```python
import h5py
with h5py.File('experiment.h5', 'r') as f:
    print(f['All Runs/0001_experiment/Images'].keys())  # Should show cameras
```

### "Results not matching"
Ensure:
- Combined file attribute names match what extractors expect
- Result naming convention is `{group_name}/{result_name}` in `single_shot_combine.py`
- Single_shot_combine.py was modified if you changed result names

### Performance not improved
Common reasons:
- Combined file on slow storage (network drive)
- Images not actually stored in combined file
- OS file cache already has individual files
- Too few shots to benefit from shared I/O

Try:
- Moving combined file to fast local storage
- Clearing OS file cache
- Accessing many shots in sequence
