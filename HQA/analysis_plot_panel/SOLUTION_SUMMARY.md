# Summary of Changes: Combined File Support

## Problem Statement
You wanted to make the analysis_plot_panel compatible with `single_shot_combine.py` so that:
- Data is not saved in individual files
- All data is loaded from a shared combined file
- This reduces disk usage and improves performance

## Solution Implemented

A complete solution has been implemented with three main components:

### 1. New Utility Module: `combined_file_utils.py`
Located: `analysislib/HQA/analysis_plot_panel/src/analysis_plot_panel/combined_file_utils.py`

This module provides:
- **`find_combined_file(h5_path)`** - Automatically finds the combined file for a shot by searching parent directories
- **`is_combined_file(h5_file)`** - Checks if an HDF5 file is a combined file (has 'All Runs' group)
- **`get_combined_file_result()`** - Extracts scalar results from the combined file's dataset attributes
- **`get_combined_file_image()`** - Extracts image data from the combined file's hierarchy
- **`extract_from_combined_or_individual()`** - Wrapper function for flexible extraction

### 2. Updated Data Extractors: `user_data_extractors.py`
Modified: `analysislib/HQA/analysis_plot_panel/src/analysis_plot_panel/user_data_extractors.py`

Changes:
- **`FluoDataExtractor`** - Now attempts to load from combined file first, falls back to individual file
- **`AbsorptionDataExtractor`** - Same improvements as FluoDataExtractor
- Added `_extract_from_combined()` helper method to both extractors
- Completely backward compatible - existing code continues to work

### 3. Documentation Files

Three comprehensive guides created:

#### INSTALLATION.md
- Explains what was changed
- Installation instructions (just copy files)
- Configuration options
- Troubleshooting

#### COMBINED_FILE_SUPPORT.md
- Technical overview
- Data structure explanation
- How the system works
- Performance considerations
- Future enhancement ideas

#### COMBINED_FILE_USAGE.md
- Practical usage examples
- Step-by-step workflow
- Debug monitoring code
- Performance tips

## How It Works

### Automatic Detection
When analyzing a shot, the system:
1. Extracts the shot basename from the file path
2. Searches parent directories (up to 2 levels) for combined files
3. Checks if any combined file contains the current shot
4. If found, loads data from combined file
5. If not found or loading fails, falls back to individual file

### Data Storage Structure
The combined file created by `single_shot_combine.py` has this structure:
```
combined_file.h5
└── All Runs/
    └── <shot_basename>/
        ├── <run_name>.dat          (metadata dataset)
        └── Images/
            └── <camera>/
                ├── diff_image
                ├── OD_image
                ├── xsum
                ├── etc...
```

Results are stored as attributes on the datasets using the format:
- `{group_name}/{result_name}` → scalar value or JSON-encoded data

### Fallback Mechanism
If the combined file:
- Cannot be found
- Doesn't contain the shot  
- Doesn't have the requested data
- Encounters any loading error

...the system automatically falls back to loading from the individual shot file using `lyse.Run()`, ensuring backward compatibility.

## Usage

### No Action Required!
The system works automatically:
1. Just copy the new files to your workspace
2. Continue using the analysis_plot_panel normally
3. Create combined files with `single_shot_combine.py`
4. The panel will automatically detect and use them

### Optional Monitoring
To see if combined file loading is active:
```python
from analysislib.HQA.analysis_plot_panel.src.analysis_plot_panel.combined_file_utils import find_combined_file
combined = find_combined_file(h5_path)
if combined:
    print(f"Using combined file: {combined}")
```

## Benefits

1. **Automatic** - No configuration needed
2. **Flexible** - Can load from combined files or individual files
3. **Safe** - Graceful fallback if combined file not available
4. **Efficient** - Better I/O performance for batch analysis
5. **Compatible** - Works with existing code without changes

## Files Modified/Created

Created:
- ✅ `combined_file_utils.py` - New utility module (~268 lines)
- ✅ `INSTALLATION.md` - Installation guide
- ✅ `COMBINED_FILE_SUPPORT.md` - Technical documentation  
- ✅ `COMBINED_FILE_USAGE.md` - Usage examples

Modified:
- ✅ `user_data_extractors.py` - Updated FluoDataExtractor and AbsorptionDataExtractor (added ~120 lines, kept all original functionality)

## Key Design Decisions

1. **Non-intrusive**: Original code paths preserved, combined file loading added as optional layer
2. **Search-based**: No configuration required, automatically finds combined files
3. **Attribute-based results**: Uses HDF5 attributes (fast, simple) instead of creating new datasets
4. **Graceful degradation**: Always works, even without combined files
5. **Extensible**: Pattern can be applied to other data extractors

## Extending to Other Extractors

To add combined file support to other extractors (e.g., SpectrumDataExtractor):

```python
def _extract_from_combined(self, combined_path, shot_basename, run_name):
    """Similar pattern to FluoDataExtractor..."""
    try:
        with h5py.File(combined_path, 'r') as h5_file:
            # Extract results from attributes
            result1 = get_combined_file_result(h5_file, shot_basename, run_name, group, name)
            # ... build return data ...
            return result_tuple
    except Exception:
        return None

def extract_data(self, h5_path, h5_file=None):
    # Try combined file first
    combined_path = find_combined_file(h5_path)
    if combined_path:
        # ... attempt extraction from combined file ...
    
    # Fall back to individual file (existing code)
    # ... original extraction logic ...
```

## Testing Recommendations

1. **Without combined file** - Verify fallback works with existing individual files
2. **With combined file** - Verify data loads correctly from combined file
3. **Mixed scenario** - Some shots in combined file, some only individual
4. **Edge cases** - Missing data, corrupt combined file, etc.

## Future Enhancements

Potential improvements for later:
- Cache combined file lookups for faster subsequent access
- Support for array-type results (currently only scalars from attributes)
- Expand to more data extractors
- Memory-mapped access for very large images
- Automatic combined file creation from configuration

## Support

For issues or questions:
1. Check the documentation files (INSTALLATION.md, COMBINED_FILE_SUPPORT.md)
2. Inspect combined file structure with h5py:
   ```python
   import h5py
   with h5py.File('experiment.h5', 'r') as f:
       print(list(f['All Runs'].keys()))
   ```
3. Enable debug output in your analysis routine
4. Review the utility functions for expected data format
