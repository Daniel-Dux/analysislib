# Troubleshooting: Deleted Shots Not Loading from Combined File

## Problem
After using `single_shot_combine.py` with `delete_shots=True`, deleted shots no longer display data in the analysis panel.

## Root Causes

1. **Combined file not found** - The search only goes up 2-3 directory levels
2. **Images not stored** - `single_shot_combine.py` may not have copied images properly
3. **Data structure mismatch** - Camera names or image names don't match expectations
4. **Incomplete combined file** - File was created before analysis finished

## How to Diagnose

### Step 1: Find and Inspect the Combined File

Run the diagnostic tool:

```powershell
cd C:\Users\ultracold\labscript-suite\userlib\analysislib\HQA\analysis_plot_panel\src\analysis_plot_panel

# Check a specific combined file
python check_combined_file_diagnostic.py "C:\path\to\experiment.h5"

# Or search a directory for all combined files
python check_combined_file_diagnostic.py --find "C:\Experiments\HQA\hqa_sequence\2026\03\18"
```

### Step 2: Check the Output

The diagnostic tool shows:

✓ **What you want to see:**
```
✓ Found 'All Runs' group with 150 shots
✓ Metadata (.dat): 1 files
✓ Images: MOT_Counting(7), etc.
```

✗ **Problems to fix:**
```
❌ 'All Runs' group not found  → File is not a combined file
✗ Metadata (.dat): 0 files    → Data wasn't stored
✗ Images: None                → Images weren't copied
```

### Step 3: Check Combined File Location

The analysis panel searches for combined files up to 3 directory levels above the shot:

```
Experiment folder (searched at level 3)
│
└─── 2026/                   (level 2)
     │
     └─── 03/                (level 1)  
          │
          └─── 18/           (level 0 - shot folder)
               └─── 2026-03-18_0032_hqa_sequence_0_rep00105.h5
```

**If your combined file is farther away**, you may need to move it or extend the search.

## Common Issues and Fixes

### Issue 1: "No combined file found"

**Check:**
```bash
# List your combined files
Get-ChildItem "C:\Experiments\HQA" -Filter "*.h5" -Recurse | where {$_.Name -notmatch "^[0-9]"}
```

**Fix:**
- Move combined file to parent of date folder: `C:\Experiments\HQA\hqa_sequence\2026\03\experiment.h5`
- Or move to experiment level: `C:\Experiments\HQA\hqa_sequence\experiment.h5`
- Or edit search depth in `combined_file_utils.py` line 20 (increase from 3)

### Issue 2: "Images not in combined file"

**Check:**
```powershell
python check_combined_file_diagnostic.py "C:\path\to\experiment.h5"
# Look for: "✗ Images: None"
```

**Fix:**
- Ensure `single_shot_combine.py` includes image copying (it should by default)
- Run `single_shot_combine.py` AFTER all analysis is complete
- Check that shot files had images before being combined

**Verify in the code:**
```python
# In single_shot_combine.py, check this section:
if 'images' in src:
    images_root = shot_group.require_group('Images')
    # Should see images being copied
```

### Issue 3: "Camera name mismatch"

**Check the diagnostic output:**
```
Camera: MOT_Counting (7 images)
```

**Compare with extractor:**
In `user_data_extractors.py`, line 67:
```python
if not plot_name in fm.ap.plots:
    ip = ImagingPlot(plot_name)
    fm.ap.add_plot_dock(plot_name, ip, FluoDataExtractor('fluo_imaging', 'MOT_Counting'))
                                                           imaging ^           camera ^
```

**The camera name must match!**

## Enable Logging for Debugging

Add this to your analysis routine to see detailed logging:

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('analysis_plot_panel.combined_file_utils')
logger.setLevel(logging.DEBUG)
logger.info("Combined file loading enabled with debug output")
```

Then watch the lyse console for messages like:
- "Loaded ... data from combined file"
- "No combined file found"
- "Error loading from combined file"

## Python Script to Check Everything

```python
from analysislib.HQA.analysis_plot_panel.src.analysis_plot_panel.combined_file_utils import find_combined_file
from analysislib.HQA.analysis_plot_panel.src.analysis_plot_panel.check_combined_file_diagnostic import check_combined_file

# Path to a shot that was deleted
shot_path = r"C:\Experiments\HQA\hqa_sequence\2026\03\18\0032\2026-03-18_0032_hqa_sequence_0_rep00105.h5"

print(f"Shot exists: {os.path.exists(shot_path)}")
print(f"Looking for combined file...")

combined = find_combined_file(shot_path)
if combined:
    print(f"Found: {combined}")
    check_combined_file(combined)
else:
    print("No combined file found!")
```

## Quick Checklist

- [ ] Shot file was deleted by `single_shot_combine.py`
- [ ] Combined file exists and has 'All Runs' group
- [ ] Combined file contains the shot (shows in diagnostic tool)
- [ ] Combined file has images stored (not just metadata)
- [ ] Camera names match between code and combined file
- [ ] Combined file is in a searchable location (3 levels above shot folder)
- [ ] Analysis completed before combining

## If Nothing Works

1. **Disable combined file loading temporarily:**
   ```python
   # In FluoDataExtractor.extract_data(), comment out the combined file section
   # This will only use individual files
   ```

2. **Save images to combined file explicitly:**
   ```python
   # Make sure single_shot_combine.py has this section active
   if 'images' in src:
       images_root = shot_group.require_group('Images')
       # ... copying code ...
   ```

3. **Recreate combined files:**
   - Delete the combined file
   - Restore a backup of individual shot files (if available)
   - Run `single_shot_combine.py` again with verbose output

## Support Documents

- `SOLUTION_SUMMARY.md` - How combined file support was implemented
- `COMBINED_FILE_SUPPORT.md` - Technical details
- `COMBINED_FILE_USAGE.md` - Usage examples
