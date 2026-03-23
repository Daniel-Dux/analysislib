# Analysis Plot Panel - Combined File Support

## Overview

The analysis plot panel now supports loading data from combined HDF5 files created by `single_shot_combine.py`. This allows you to:

- **Reduce disk I/O**: Load analysis results from a single combined file instead of individual shot files
- **Improve performance**: Shared data loading for batch analysis
- **Simplify workflows**: No need to keep individual shot files if you have the combined file

## How It Works

The system automatically detects when a combined file is available and loads data from it. If loading from the combined file fails for any reason, it gracefully falls back to loading from the individual shot file.

### Detection and Search

When analyzing a shot, the system:
1. Looks for a combined file in parent directories (up to 2 levels up)
2. Checks if the combined file contains the current shot's data
3. Extracts results and images from the combined file if found
4. Falls back to the individual shot file if the combined file is not found or doesn't contain the data

### Data Storage in Combined Files

Combined files have this structure:
```
combined_file.h5
├── All Runs/
│   └── <shot_basename>/
│       ├── <run_name>.dat          (placeholder dataset with results as attributes)
│       └── Images/
│           └── <camera>/
│               ├── diff_image
│               ├── OD_image
│               ├── xsum
│               ├── ysum
│               ├── xfit
│               ├── yfit
│               ├── xgrid
│               └── ygrid
```

## Requirements

No configuration needed! The system works automatically. Just make sure:

1. `single_shot_combine.py` is run after your analysis to create the combined file
2. The combined file is placed in a parent directory of the shot files
3. The image data is stored in the combined file (handled by `single_shot_combine.py`)

## Implementation Details

### Modified Extractors

The following data extractors have been updated to support combined files:
- `FluoDataExtractor` - Fluorescence imaging data
- `AbsorptionDataExtractor` - Absorption imaging data

Other extractors (spectrum, scope, background, ADwin) can be updated similarly if needed.

### Utility Module

A new `combined_file_utils.py` module provides helper functions:

- `find_combined_file(h5_path)` - Locate combined file for a shot
- `is_combined_file(h5_file)` - Check if file is a combined file
- `get_combined_file_result()` - Extract scalar results from attributes
- `get_combined_file_image()` - Extract image data from combined file

### Fallback Mechanism

If the combined file:
- Cannot be found
- Doesn't contain the shot
- Doesn't have the requested data
- Fails to load for any reason

...the system automatically falls back to loading from the individual shot file using `lyse.Run()`.

## Performance Considerations

- **First load**: Minimal overhead (quick directory search)
- **Subsequent loads**: Same speed as before (data cached by DataExtractor)
- **Combined file benefit**: Larger when analyzing many sequentially numbered shots from the same run

## Troubleshooting

### Images not loading from combined file
The combined file structure must have images stored under `All Runs/<shot_id>/Images/<camera>/<image_name>`. Verify that `single_shot_combine.py` is copying images correctly.

### Results not found in combined file
Check that:
1. The combined file was created after analysis (analysis scripts must run first)
2. Result names match what the extractors are looking for
3. The attributes are stored correctly in the `.dat` dataset

### Performance hasn't improved
Combined files only benefit if:
- You're analyzing many shots in sequence
- The combined file is cached by the OS
- Images are actually stored in the combined file

## Future Enhancements

Possible improvements:
- Support for array-type results (currently only scalars from attributes)
- Caching of combined file lookups
- Support for additional data extractors (spectrum, scope, background)
- Memory-mapped access for very large images
