import lyse
import numpy as np
import h5py
from pathlib import Path

try:
    from scipy.ndimage import uniform_filter
except ImportError:
    uniform_filter = None

_ASSET_DIR = Path(__file__).parent / 'background_images'
_ASSET_DIR.mkdir(exist_ok=True)

# ── Per-pixel sensor calibration (gain / offset map) ───────────────────────────
# Mirrors ExperimentImages.pixel_to_photon_number in
#   15-HQA/Data_Evaluation/ExperimentImages.py
# The calibration is stored as an .npz with keys:
#   'offsets'      -> per-pixel offset (bias) map, in ADU               -> offset map
#   'spacings'     -> per-pixel gain map, in ADU per photon             -> gain map
#   'pixels_failed'-> bool mask of pixels whose calibration failed
# Photon number is then  photons = (raw - offset) / gain (not clipped, so the
# noise floor / negative fluctuations are preserved for later analysis).
# Failed pixels fall back to the scalar defaults below.
DEFAULT_OFFSET = 200.0   # ADU        (ExperimentImages.DEFAULT_OFFSET)
DEFAULT_GAIN   = 8.5     # ADU/photon (ExperimentImages.DEFAULT_SPACING)

_calib_npz   = _ASSET_DIR / 'orca_calibration.npz'   # keys offsets/spacings/pixels_failed
_offset_file = _ASSET_DIR / 'orca_offset_map.npy'    # alt: separate maps
_gain_file   = _ASSET_DIR / 'orca_gain_map.npy'
_failed_file = _ASSET_DIR / 'orca_pixels_failed.npy'


def _roi_slice(roi):
    """Return (y_slice, x_slice) for a dict with x_center/y_center/width/height."""
    xs = int(roi['x_center'] - roi['width']  / 2)
    xe = int(roi['x_center'] + roi['width']  / 2)
    ys = int(roi['y_center'] - roi['height'] / 2)
    ye = int(roi['y_center'] + roi['height'] / 2)
    return slice(ys, ye), slice(xs, xe)


def _load_calibration(run_globals):
    """Load the per-pixel gain/offset calibration maps.

    Search order:
      1. path in the ``orca_calibration_path`` global — an .npz with keys
         ``offsets``/``spacings``/``pixels_failed`` (e.g. the lab
         ``OrcaQuestCalibration.npz`` on the network share),
      2. a local ``orca_calibration.npz`` in the asset dir (same keys),
      3. separate ``orca_offset_map.npy`` + ``orca_gain_map.npy`` (+ optional
         ``orca_pixels_failed.npy``) in the asset dir.

    Returns ``(offset_map, gain_map, pixels_failed)``; any element may be None.
    """
    npz_path = run_globals.get('orca_calibration_path')
    if not npz_path and _calib_npz.exists():
        npz_path = _calib_npz
    if npz_path and Path(npz_path).exists():
        try:
            calib = np.load(npz_path)
            offset_map    = calib['offsets']
            gain_map      = calib['spacings']
            pixels_failed = calib['pixels_failed'] if 'pixels_failed' in calib.files else None
            return offset_map, gain_map, pixels_failed
        except Exception as e:
            print(f'orca_image_analysis: could not load calibration npz "{npz_path}": {e}')

    offset_map    = np.load(_offset_file) if _offset_file.exists() else None
    gain_map      = np.load(_gain_file)   if _gain_file.exists()   else None
    pixels_failed = np.load(_failed_file) if _failed_file.exists() else None
    return offset_map, gain_map, pixels_failed


def _match_map_to_image(m, img_shape, subarray_offset=None):
    """Crop a full-sensor calibration map to the camera subarray if needed.

    Returns a map matching ``img_shape``, or None if it cannot be matched
    (missing map, or shape mismatch with no usable subarray offset).
    """
    if m is None:
        return None
    if m.shape == img_shape:
        return m
    if subarray_offset is not None:
        try:
            x0, y0 = int(subarray_offset[0]), int(subarray_offset[1])
            h, w = img_shape
            cropped = m[y0:y0 + h, x0:x0 + w]
            if cropped.shape == img_shape:
                return cropped
        except Exception:
            pass
    return None


def counts_to_photons(img, offset_map=None, gain_map=None, pixels_failed=None,
                      default_offset=DEFAULT_OFFSET, default_gain=DEFAULT_GAIN):
    """Convert raw sensor counts to photon numbers via a per-pixel gain/offset map.

        photons = (raw - offset_map) / gain_map      (not clipped)

    Parameters
    ----------
    img : np.ndarray            Raw 2-D image (ADU).
    offset_map : np.ndarray | None  Per-pixel offset/bias (ADU), same shape as img.
    gain_map : np.ndarray | None    Per-pixel gain (ADU/photon), same shape as img.
    pixels_failed : np.ndarray | None  Bool mask; failed pixels use the scalar defaults.

    Falls back to the scalar ``default_offset``/``default_gain`` for the whole
    frame when no map matching the image shape is available.
    """
    img = img.astype(float)
    have_map = (offset_map is not None and gain_map is not None
                and offset_map.shape == img.shape and gain_map.shape == img.shape)
    if have_map:
        offsets = offset_map.astype(float).copy()
        gains   = gain_map.astype(float).copy()
        if pixels_failed is not None and pixels_failed.shape == img.shape:
            mask = pixels_failed.astype(bool)
            offsets[mask] = default_offset
            gains[mask]   = default_gain
    else:
        offsets = np.full(img.shape, default_offset, dtype=float)
        gains   = np.full(img.shape, default_gain,   dtype=float)

    # Avoid divide-by-zero on any zero-gain pixels.
    gains = np.where(gains == 0, default_gain, gains)
    return (img - offsets) / gains


def photons_to_integer(photons, clip_negative=False):
    """Round a photon-number image to whole photons.

    Photon numbers are physically discrete, so this rounds to the nearest
    integer and returns an ``int32`` array. Negative values (noise floor /
    downward fluctuations below the offset) are kept by default so the
    statistics stay unbiased; pass ``clip_negative=True`` to floor them at 0.
    """
    ints = np.rint(photons).astype(np.int32)
    if clip_negative:
        np.clip(ints, 0, None, out=ints)
    return ints


def apply_lowpass(photons, window):
    """Box (moving-average) low-pass filter with an integer window size (pixels).

    Smooths the photon-number image with a ``window x window`` uniform kernel,
    using ``mode='nearest'`` at the borders. A ``window`` of None or <= 1 is a
    no-op (returns the input unchanged), as is a missing SciPy install.
    """
    if window is None:
        return photons
    try:
        w = int(window)
    except (TypeError, ValueError):
        print(f'orca_image_analysis: invalid low-pass window {window!r} — skipping filter.')
        return photons
    if w <= 1:
        return photons
    if uniform_filter is None:
        print('orca_image_analysis: SciPy not available — skipping low-pass filter.')
        return photons
    return uniform_filter(photons, size=w, mode='nearest')


def analyse_orca_image(img, run, group, label, image_name,
                       offset_map=None, gain_map=None, pixels_failed=None,
                       rois=None, roi_analysis_fn=None, lowpass_window=None,
                       clip_negative_photons=False):
    """
    Process a single ORCA image and save results.

    The raw frame is preserved (saved separately as ``<label>_<image>_image``);
    here we additionally save the photon-number image obtained by applying the
    per-pixel gain/offset map (``<prefix>_photons``, float) plus the same image
    rounded to whole photons (``<prefix>_photons_int``, int32), and run ROI
    analysis on the (float) photon image.

    Parameters
    ----------
    img : np.ndarray          Raw 2-D image array (ADU).
    run : lyse.Run            Current run, used to save results.
    group : str               HDF5 results group name.
    label : str               Camera label (used to prefix result keys).
    image_name : str          Image name within the label.
    offset_map, gain_map : np.ndarray | None
        Per-pixel offset (ADU) and gain (ADU/photon) maps, already cropped to
        the image shape. If missing, scalar defaults are used.
    pixels_failed : np.ndarray | None
        Bool mask of pixels whose calibration failed (use defaults for those).
    rois : list[dict] | None
        Up to two ROI dicts, each with keys
        ``x_center``, ``y_center``, ``width``, ``height`` (pixels).
    roi_analysis_fn : callable | None
        ``f(roi_img: np.ndarray, roi_name: str) -> dict``
        Called for each ROI on the photon-number image. Every key→value in the
        returned dict is saved as ``f'{label}_{image_name}_{roi_name}_{key}'``.
    lowpass_window : int | None
        If given and > 1, smooth the photon-number image with a
        ``window x window`` box (moving-average) low-pass filter before ROI
        analysis. The unfiltered ``<prefix>_photons`` is still saved; the
        smoothed image is saved separately as ``<prefix>_photons_filtered``
        and is what the ROI analysis runs on.
    clip_negative_photons : bool
        If True, the integer photon image ``<prefix>_photons_int`` is floored
        at 0. Default False keeps negative (sub-offset) values so the noise
        statistics stay unbiased.
    """
    prefix = f'{label}_{image_name}'

    # Raw counts → photon numbers via the per-pixel gain/offset map ─────────────
    photons = counts_to_photons(img, offset_map, gain_map, pixels_failed)
    run.save_result_array(f'{prefix}_photons', photons, group='results/' + group)

    # Same image rounded to whole photons (int32) ──────────────────────────────
    photons_int = photons_to_integer(photons, clip_negative=clip_negative_photons)
    run.save_result_array(f'{prefix}_photons_int',
                          photons_int,
                          group='results/' + group)

    # Optional low-pass (box) filter; window size comes from a shot global ───────
    photons_analysis = photons # apply_lowpass(photons, lowpass_window)
    if photons_analysis is not photons:
        run.save_result_array(f'{prefix}_photons_filtered', photons_analysis, group='results/' + group)
        run.save_result(f'{prefix}_lowpass_window', int(lowpass_window), group='results/' + group)

    # ROI analysis (on the photon-number image) ────────────────────────────────
    if rois:
        roi_photon_total = 0.0       # running total of photons over all ROIs
        for i, roi in enumerate(rois[:2]):          # hard cap at 2 ROIs
            roi_name = roi.get('name', f'roi{i + 1}')
            y_sl, x_sl = _roi_slice(roi)
            roi_img = photons_analysis[y_sl, x_sl]

            # Total photon number within this ROI (summed across the combined result)
            roi_photon_total += float(roi_img.sum())

            # roi_analysis_fn is responsible for all per-ROI results
            if roi_analysis_fn is not None:
                try:
                    results = roi_analysis_fn(roi_img, roi_name)
                    for key, val in (results or {}).items():
                        run.save_result(f'{prefix}_{roi_name}_{key}', val, group='results/' + group)
                except Exception as e:
                    print(f'analyse_orca_image: roi_analysis_fn failed for '
                          f'{roi_name}: {e}')

        # Combined total photon number summed over all ROIs
        # run.save_result(f'{prefix}_roi_photons_sum', roi_photon_total, group='results/' + group)

        # Save ROI positions so the analysis plot panel can draw overlays
        roi_array = np.array([[r['x_center'], r['y_center'], r['width'], r['height']]
                               for r in rois[:2]], dtype=float)
        run.save_result_array(f'{prefix}_roi_metadata', roi_array, group='results/' + group)


def orca_roi_analysis(roi_img, roi_name):
    """Per-ROI analysis. Return a dict; every key is saved as a result.

    ``roi_img`` is in photon numbers. Add any extra analysis you need here –
    e.g. Gaussian fits, atom-number counting, etc.
    """
    return {
        'sum': float(roi_img.sum()),   # total photons in ROI
    }



try:
    h5_path = lyse.path
except AttributeError:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

run_globals = run.get_globals()

group = 'orca_image_analysis'

orca_found = []

try:
    all_labels = run.get_all_image_labels()
except Exception as e:
    print(f'orca_image_analysis: could not get image labels: {e}')
    all_labels = {}

collected = {}  # {(orientation, label, image_name): array}

try:
    with h5py.File(h5_path, 'r') as f:
        images_group = f.get('images', {})
        for orientation in list(all_labels.keys()):
            if orientation not in images_group:
                continue
            ori_group = images_group[orientation]
            for label in all_labels.get(orientation, []):
                if not label.lower().startswith('orca'):
                    continue
                if label not in ori_group:
                    continue
                label_group = ori_group[label]
                image_names = [k for k, v in label_group.items() if isinstance(v, h5py.Dataset)]
                for image_name in image_names:
                    try:
                        raw = np.array(label_group[image_name], dtype='float')
                        img = raw[0] if raw.ndim == 3 else raw
                        collected[(orientation, label, image_name)] = img
                    except Exception as e:
                        print(f'orca_image_analysis: error processing image "{image_name}" in label "{label}": {e}')
except Exception as e:
    print(f'orca_image_analysis: error reading h5 file: {e}')


# ── Load per-pixel gain/offset calibration maps ────────────────────────────────
orca_offset_map, orca_gain_map, orca_pixels_failed = _load_calibration(run_globals)
if orca_gain_map is None or orca_offset_map is None:
    print('orca_image_analysis: no gain/offset calibration found — falling back to '
          f'scalar defaults (offset={DEFAULT_OFFSET}, gain={DEFAULT_GAIN} ADU/photon).')

# Optional subarray offset [x0, y0] to crop a full-sensor map onto the frame.
_subarray_offset = run_globals.get('orca_subarray_offset')

# ── Background recording (record with orca_record_background=True in globals) ──
# Kept as a standalone maintenance feature; it builds a running-average dark
# frame in the asset dir. The photon conversion above uses the offset map for
# per-pixel bias removal, so this background is not subtracted automatically.
_bg_file  = _ASSET_DIR / 'orca_background.npy'
_buf_file = _ASSET_DIR / 'orca_background_buffer.npy'

record_background = run_globals.get('orca_record_background', False)
orca_background   = np.load(_bg_file) if _bg_file.exists() else None

try:
    if 'orca_record_background' in run_globals:
        record_background = run_globals['orca_record_background']
        if record_background and collected:
            # Accumulate images into a buffer and save the running average
            first_img = next(iter(collected.values()))
            if _buf_file.exists():
                buf = np.load(_buf_file)
                buf = np.concatenate([buf, first_img[np.newaxis]], axis=0)
            else:
                buf = first_img[np.newaxis]
            np.save(_buf_file, buf)
            mean_bg = buf.mean(axis=0)
            np.save(_bg_file, mean_bg)
            orca_background = mean_bg
            run.save_result('orca_background_recorded', True, group='results/' + group)
            run.save_result('orca_background_n_shots', int(buf.shape[0]), group='results/' + group)
            print(f'analyse_orca_image: background updated (averaged over {buf.shape[0]} shot(s))')
        elif not record_background:
            # Recording stopped – clear the buffer so the next session starts fresh
            if _buf_file.exists():
                _buf_file.unlink()
                print('analyse_orca_image: background buffer cleared')
except Exception as e:
    print(f'analyse_orca_image: error checking record_background flag: {e}')

rois = None
if 'orca_roi_center_1' in run_globals and 'orca_roi_size_1' in run_globals:
    try:
        x_c = run_globals['orca_roi_center_1'][0]
        y_c = run_globals['orca_roi_center_1'][1]
        w   = run_globals['orca_roi_size_1'][0]
        h   = run_globals['orca_roi_size_1'][1]
        roi1 = {'x_center': x_c, 'y_center': y_c, 'width': w, 'height': h,
                'name': run_globals.get('orca_roi_1_name', 'roi1')}
        rois = [roi1]
    except Exception as e:
        print(f'analyse_orca_image: error parsing ROI globals: {e}')
        rois = None
if 'orca_roi_center_2' in run_globals and 'orca_roi_size_2' in run_globals:
    try:
        x_c = run_globals['orca_roi_center_2'][0]
        y_c = run_globals['orca_roi_center_2'][1]
        w   = run_globals['orca_roi_size_2'][0]
        h   = run_globals['orca_roi_size_2'][1]
        roi2 = {'x_center': x_c, 'y_center': y_c, 'width': w, 'height': h,
                'name': run_globals.get('orca_roi_2_name', 'roi2')}
        rois = rois + [roi2] if rois else [roi2]
    except Exception as e:
        print(f'analyse_orca_image: error parsing ROI globals: {e}')

# Optional low-pass filter window (pixels); set via the `orca_lowpass_window`
# shot global. Absent or <= 1 disables filtering.
orca_lowpass_window = run_globals.get('orca_lowpass_window')

# Set the `orca_photons_int_clip` global to True to floor the integer photon
# image at 0; by default negative (sub-offset) values are kept.
orca_photons_int_clip = bool(run_globals.get('orca_photons_int_clip', False))

for (orientation, label, image_name), img in collected.items():
    try:
        # Save the raw frame unchanged
        result_key = f'{label}_{image_name}_image'
        run.save_result_array(result_key, img, group='results/' + group)

        # Match the calibration maps to this frame's shape (crop if full-sensor)
        offset_map = _match_map_to_image(orca_offset_map, img.shape, _subarray_offset)
        gain_map   = _match_map_to_image(orca_gain_map,   img.shape, _subarray_offset)
        failed_map = _match_map_to_image(orca_pixels_failed, img.shape, _subarray_offset)
        if orca_gain_map is not None and gain_map is None:
            print(f'orca_image_analysis: calibration shape {orca_gain_map.shape} does not '
                  f'match image shape {img.shape} for "{label}/{image_name}" and no usable '
                  f'subarray offset was given — using scalar defaults for this frame.')

        analyse_orca_image(
            img, run, group, label, image_name,
            offset_map=offset_map,
            gain_map=gain_map,
            pixels_failed=failed_map,
            rois=rois,
            roi_analysis_fn=orca_roi_analysis,
            lowpass_window=orca_lowpass_window,
            clip_negative_photons=orca_photons_int_clip,
        )

        orca_found.append((orientation, label, image_name))
    except Exception as e:
        print(f'orca_image_analysis: error saving result for "{orientation}/{label}/{image_name}": {e}')

# Advertise the saved image keys to the plot panel. Include the low-pass
# filtered image only when filtering was actually applied this shot.
_lowpass_active = bool(orca_lowpass_window) and int(orca_lowpass_window) > 1


def _image_keys_for(label, image_name):
    keys = [f'{label}_{image_name}_image',
            f'{label}_{image_name}_photons',
            f'{label}_{image_name}_photons_int']
    if _lowpass_active:
        keys.append(f'{label}_{image_name}_photons_filtered')
    return keys


run.save_result('orca_image_keys', ','.join(
    key
    for (_, label, image_name) in collected.keys()
    for key in _image_keys_for(label, image_name)
))

if not orca_found:
    print('orca_image_analysis: no images found with labels starting with "orca"')
