"""
Single-atom detection on ORCA Quest frames, for the analysis plot panel.

Built like ``orca_image_analysis.py``: it walks every image whose camera label
starts with "orca", converts the raw ADU frame to photon numbers with the
per-pixel gain/offset calibration named by the ``orca_calibration_path`` shot
global, and writes the results the plot panel reads back.  On top of that it

  * subtracts a dark frame recorded to disk, in the style of
    ``fluo_background_analysis.py`` (see "Recording a dark frame" below),
  * runs one of the interchangeable finders from
    ``Data_Evaluation.Modules.AtomFinders`` on the processed image and saves the
    detected atom positions.

The "Orca Atom Finder" dock then shows three views of the selected frame:

    raw (ADU)  |  photons, dark subtracted  |  the same with the atoms circled

The overlay is drawn as vector markers on top of the processed image, so the
detection positions never touch the pixel data.

Recording a dark frame
----------------------
1. Take a shot under dark conditions (same exposure/subarray as the signal).
2. Set ``orca_af_record_dark = True`` in the globals and run this routine.  The
   frame is stored per camera label / image name under ``background_images/``.
   While the flag stays True further shots are accumulated into a running mean
   (as a sum + count, so the disk usage does not grow with the number of
   shots); atom finding is skipped for those shots.
3. Set ``orca_af_record_dark = False`` again.  That clears the accumulator, so
   the next recording session starts fresh, and normal analysis resumes.

Note that the per-pixel offset map already removes the sensor bias, so the dark
frame only takes out what is left: dark current and stray light.  Without a
dark frame the routine still runs and just reports
``<prefix>_dark_subtracted = False``.

Calibrating the finder on single atoms
--------------------------------------
The PSF and the photons an atom delivers are properties of the apparatus, and a
per-shot routine cannot measure them: it sees one frame per call, and one frame
holds a handful of photons in a few pixels.  So they are measured once, over a
run of shots that each contain an atom, and stored next to the dark frame:

1. Record a dark frame first (above).  The calibration is measured on
   dark-subtracted frames, and the dark run is itself part of what
   ``poisson_llr_calibrated`` is told.
2. Take shots with a single atom present, set ``orca_af_record_atoms = True``
   and let the routine run over them.  These are ordinary shots, so they are
   still analysed and plotted as usual.
3. Set ``orca_af_record_atoms = False``.  From then on every shot is analysed
   with the measured PSF and photon number.
4. ``orca_af_atom_cal_reset = True`` throws the recording away and starts over
   - after realignment, a change of exposure, or a different subarray.

``orca_af_atom_cal_mode`` decides how the atom is located, and the two modes
answer different questions about the apparatus:

``'mean'`` (default)
    The frames are accumulated and the atom is located *once*, in their mean.
    This is the mode for a tweezer: the atom is at the same place every shot, so
    averaging first and looking afterwards does the locating at sqrt(N) times
    the signal-to-noise of a shot, and the spot in the mean image is the largest
    thing in the window rather than something to dig out of the photon noise.
    The template that comes out is also the *sampled* PSF at the sub-pixel
    position the atom really has, which is what the detector will see on every
    later shot.  No finder is involved at all.
``'peak'``
    The configured finder locates the brightest candidate in each shot and the
    cutouts are averaged - shift-and-add.  The mode for an atom that does not
    return to the same pixel, and the price is paid twice: each cutout is
    centred on an integer pixel of a frame with a handful of photons in it, so
    the average is smeared by up to half a pixel of centring error, and a shot
    that held no atom still contributes its brightest noise peak.

What is measured either way - the shape of the spot and the photons it carries -
describes the apparatus and not the atom's whereabouts, so a calibration taken
with atoms at one position stays valid for shots taken at another.  The
*position* is recorded too, but only reported (in the .json beside the .npz, and
in the lyse output), and no finder is given a positional prior: an atom in free
space is wherever it flew to, and a detector that already knows where to look is
one that will not find an atom anywhere else.

Two numbers come with the calibration and are worth reading:

``psf_sigma_x/y_px``  the rms width of the measured spot.  The focus check, and
    in ``'mean'`` mode the position-stability check as well - an atom that moves
    between shots smears the mean image, and a width well above the diffraction
    limit is what that looks like.
``loading_fraction``  ``'mean'`` mode only, and the one thing a mean image
    cannot see by itself: if only a fraction of the calibration shots held an
    atom, the mean holds that fraction of the PSF.  The shape is untouched, the
    photon number is not.  It is estimated from the excess variance of the same
    pixels (see ``_loading_fraction``), needs 100 shots before it is reported at
    all, and is warned about below 0.85 - never silently divided out.

``poisson_llr_calibrated`` does get the two things it exists to use and that no
global has to supply: the dark run, added back and modelled as a rate rather
than subtracted, and the per-pixel read noise from the comb contrast of
``orca_calibration_path``.  Anything set in ``orca_af_finder_params`` overrules
all of it.

Shot globals
------------
``orca_calibration_path``    .npz with ``offsets``/``spacings``/``pixels_failed``
                             (same global as orca_image_analysis).
``orca_subarray_offset``     [x0, y0] to crop a full-sensor calibration map onto
                             the frame.
``orca_af_record_dark``      True to record/accumulate the dark frame instead of
                             analysing (default False).
``orca_af_dark_average``     True (default) to average over all shots recorded
                             in one session; False to keep only the last one.
``orca_af_roi_center``       [x, y] optional analysis window centre (pixels).
``orca_af_roi_size``         [width, height] of that window.  With both set,
                             everything - the saved images, the search and the
                             detection coordinates - is restricted to it, which
                             is the cheap way to keep full-sensor shots small.
``orca_af_record_atoms``     True to add each shot to the atom calibration (see
                             "Calibrating the finder on single atoms").
``orca_af_atom_cal_mode``    'mean' (default) to measure the PSF on the mean of
                             the calibration shots, 'peak' to shift-and-add on
                             each shot's brightest candidate.
``orca_af_atom_cal_reset``   True to discard that calibration and start over.
``orca_af_finder``           finder name from AtomFinders.FINDERS
                             ('matched_filter' (default), 'top_hat',
                             'empirical_psf', 'log_blob', 'low_pass',
                             'poisson_llr', 'poisson_llr_calibrated',
                             'fixed_site').
``orca_af_finder_params``    keyword arguments for that finder.  Globals are
                             stored as hdf5 attributes and a dict is not a valid
                             attribute value, so write it as a *string*:
                             ``"{'psf_sigma': 1.3, 'threshold_nsigma': 5}"``.
                             The keys are the finder's constructor keywords -
                             the same ones its label prints, inherited ones
                             included.  A key the finder does not take is
                             dropped and reported (with the list of accepted
                             keywords) in ``orca_af_finder_notes``; the finder
                             that was asked for still runs.  See the finder's
                             docstring in AtomFinders.py for what each means.
``orca_af_threshold``        score cut (photons in the aperture for most
                             finders, low-pass amplitude for 'low_pass').
                             Leave the global out to keep every candidate.
``orca_af_sites``            [(x, y), ...] known tweezer positions, in the same
                             coordinates as the analysis window.  Required by
                             'fixed_site', used as the template centres by
                             'empirical_psf'.
``orca_af_max_detections``   cap on the number of saved detections (default 500,
                             brightest first).

Results (group ``orca_atom_finder``)
------------------------------------
``orca_af_frames``           'orientation|label|image_name' entries, comma
                             separated - the index the panel iterates over.
``<prefix>_photons``         float32 photon image, dark subtracted, cropped.
``<prefix>_detections``      (N, 5) array of [x, y, photons, score, snr] in the
                             coordinates of the saved image (snr is NaN for
                             finders that do not report one).
``<prefix>_crop``            [y0, x0, height, width] of the analysis window in
                             full-frame coordinates.
``<prefix>_roi_metadata``    (N, 4) array of [x, y, width, height] for the
                             ``orca_roi_center_1/2`` ROI boxes, shifted into the
                             coordinates of the saved image.  The panel draws
                             them when "ROIs" is ticked.
``<prefix>_n_atoms``, ``<prefix>_photons_sum``, ``<prefix>_atom_photons_sum``,
``<prefix>_dark_subtracted``, ``<prefix>_dark_shots``
``orca_af_threshold``, ``orca_af_aperture_radius``

``orca_af_finder_label``     short name(params) of the finder that ran.
``orca_af_finder_settings``  the same finder with *every* effective setting
                             spelled out, including the defaults that were
                             never written in the globals.
``orca_af_finder_requested`` what the globals asked for, verbatim.
``orca_af_finder_notes``     ' | '-joined reasons the two differ - an unknown
                             finder name, unparseable parameters, a fit that
                             could not be done.  Empty when the shot was
                             analysed exactly as configured.  The panel shows
                             these as a warning, because a fallback otherwise
                             produces a perfectly ordinary-looking result.

where ``<prefix>`` is ``f'{label}_{image_name}'``.
"""

import ast
import inspect
import json
import sys
from pathlib import Path

import lyse
import numpy as np
import h5py

try:
    from scipy import ndimage as _ndimage
except Exception:                                        # pragma: no cover - import guard
    _ndimage = None      # _smooth() falls back to a 3x3 box mean

_ASSET_DIR = Path(__file__).parent / 'background_images'
_ASSET_DIR.mkdir(exist_ok=True)

# ── Per-pixel sensor calibration (gain / offset map) ───────────────────────────
# Same convention as orca_image_analysis.py / ExperimentImages.pixel_to_photon_number:
#   photons = (raw - offset) / gain, not clipped, so the noise floor and the
# negative fluctuations survive for the finders to work with.
DEFAULT_OFFSET = 200.0   # ADU        (ExperimentImages.DEFAULT_OFFSET)
DEFAULT_GAIN   = 8.5     # ADU/photon (ExperimentImages.DEFAULT_SPACING)

_calib_npz   = _ASSET_DIR / 'orca_calibration.npz'   # keys offsets/spacings/pixels_failed
_offset_file = _ASSET_DIR / 'orca_offset_map.npy'    # alt: separate maps
_gain_file   = _ASSET_DIR / 'orca_gain_map.npy'
_failed_file = _ASSET_DIR / 'orca_pixels_failed.npy'

GROUP = 'orca_atom_finder'


# ──────────────────────────────────────────────────────────────────────────────
# Making Data_Evaluation.Modules.AtomFinders importable
# ──────────────────────────────────────────────────────────────────────────────

def _find_data_evaluation_root(start):
    """Directory to put on sys.path so ``Data_Evaluation`` can be imported.

    Walks up from this file looking for the 15-HQA checkout (the directory that
    holds ``Data_Evaluation/Modules/AtomFinders.py``), so the routine keeps
    working if the analysislib tree is moved or renamed.
    """
    marker = Path('Data_Evaluation') / 'Modules' / 'AtomFinders.py'
    for parent in [start, *start.parents]:
        if (parent / marker).exists():
            return parent
        for child in sorted(parent.glob('*HQA*')):
            if (child / marker).exists():
                return child
    return None


_de_root = _find_data_evaluation_root(Path(__file__).resolve().parent)
if _de_root is not None and str(_de_root) not in sys.path:
    sys.path.insert(0, str(_de_root))

try:
    from Data_Evaluation.Modules.AtomFinders import (FINDERS, make_finder,
                                                     position_prior, read_noise_map)
except Exception as _e:                                  # pragma: no cover - import guard
    FINDERS, make_finder = {}, None
    position_prior = read_noise_map = None
    print('orca_atom_finder_analysis: could not import '
          f'Data_Evaluation.Modules.AtomFinders ({_e!r}).')
    print(f'orca_atom_finder_analysis: searched upwards from {Path(__file__).parent}, '
          f'root found: {_de_root}. Images will be saved without detections.')


# ──────────────────────────────────────────────────────────────────────────────
# Calibration (identical convention to orca_image_analysis.py)
# ──────────────────────────────────────────────────────────────────────────────

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
            print(f'orca_atom_finder_analysis: could not load calibration npz "{npz_path}": {e}')

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

    Falls back to the scalar ``default_offset``/``default_gain`` for the whole
    frame when no map matching the image shape is available; pixels flagged in
    ``pixels_failed`` use the scalar defaults too.
    """
    img = np.asarray(img, dtype=float)
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


# ──────────────────────────────────────────────────────────────────────────────
# Dark frames on disk (one per camera label / image name)
# ──────────────────────────────────────────────────────────────────────────────

def _safe_name(text):
    return ''.join(c if (c.isalnum() or c in '-_') else '_' for c in str(text))


def _dark_paths(label, image_name):
    """(dark .npy, accumulator .npz, metadata .json) for one camera frame."""
    stem = f'orca_dark_{_safe_name(label)}_{_safe_name(image_name)}'
    return (_ASSET_DIR / f'{stem}.npy',
            _ASSET_DIR / f'{stem}_accum.npz',
            _ASSET_DIR / f'{stem}.json')


def record_dark(raw, label, image_name, average=True, source=''):
    """Add ``raw`` to the stored dark frame for this camera frame.

    The running mean is kept as a (sum, count) pair rather than a stack of
    frames: an ORCA Quest frame is ~75 MB as float64, so buffering the frames
    themselves would put gigabytes on disk over a recording session.

    Returns ``(dark, n_shots)``.
    """
    dark_file, accum_file, meta_file = _dark_paths(label, image_name)
    raw = np.asarray(raw, dtype=float)

    total, n = raw.copy(), 1
    if average and accum_file.exists():
        try:
            with np.load(accum_file) as acc:
                prev_sum, prev_n = acc['sum'], int(acc['n'])
            if prev_sum.shape == raw.shape:
                total, n = prev_sum + raw, prev_n + 1
            else:
                print(f'orca_atom_finder_analysis: dark frame shape changed '
                      f'({prev_sum.shape} -> {raw.shape}) for "{label}/{image_name}" — '
                      'restarting the accumulation.')
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not read dark accumulator '
                  f'"{accum_file}": {e} — restarting the accumulation.')

    dark = total / n
    if average:
        np.savez(accum_file, sum=total, n=n)
    elif accum_file.exists():
        accum_file.unlink()
    np.save(dark_file, dark)

    try:
        with open(meta_file, 'w') as f:
            json.dump({'label': label,
                       'image_name': image_name,
                       'shape': list(dark.shape),
                       'n_shots': int(n),
                       'mean': float(np.mean(dark)),
                       'std': float(np.std(dark)),
                       'recorded_from': str(source)}, f, indent=2)
    except Exception as e:
        print(f'orca_atom_finder_analysis: could not write dark metadata: {e}')

    return dark, n


def load_dark(label, image_name, img_shape):
    """Stored dark frame (raw ADU) for this camera frame, or None.

    Returns ``(dark, n_shots)``; ``dark`` is None when there is no file or its
    shape does not match the current frame.
    """
    dark_file, _, meta_file = _dark_paths(label, image_name)
    if not dark_file.exists():
        return None, 0
    try:
        dark = np.load(dark_file)
    except Exception as e:
        print(f'orca_atom_finder_analysis: could not load dark frame "{dark_file}": {e}')
        return None, 0
    if dark.shape != img_shape:
        print(f'orca_atom_finder_analysis: dark frame shape {dark.shape} does not match '
              f'image shape {img_shape} for "{label}/{image_name}" — not subtracting. '
              'Record a new dark with orca_af_record_dark=True.')
        return None, 0

    n_shots = 0
    if meta_file.exists():
        try:
            with open(meta_file) as f:
                n_shots = int(json.load(f).get('n_shots', 0))
        except Exception:
            n_shots = 0
    return dark, n_shots


def _as_float_or_none(value):
    return None if value is None else float(value)


def _atom_cal_paths(label, image_name):
    """(accumulator .npz, metadata .json) for one camera frame."""
    stem = f'orca_atomcal_{_safe_name(label)}_{_safe_name(image_name)}'
    return _ASSET_DIR / f'{stem}.npz', _ASSET_DIR / f'{stem}.json'


def _cutout_ring(radius):
    """Mask of the outer ring of a (2r+1, 2r+1) cutout - where the spot no longer is."""
    yy, xx = np.mgrid[-radius:radius + 1, -radius:radius + 1]
    return (yy ** 2 + xx ** 2) > (radius - 1) ** 2


def _smooth(image, sigma=1.0):
    """Light low-pass, so a single noisy pixel cannot win an argmax."""
    if _ndimage is not None:
        return _ndimage.gaussian_filter(image, sigma)
    padded = np.pad(image, 1, mode='edge')
    height, width = image.shape
    return sum(padded[i:i + height, j:j + width]
               for i in range(3) for j in range(3)) / 9.0


def _locate_in_mean(mean, radius):
    """(y, x) of the atom in a mean image, or (None, None) if it cannot be one.

    The brightest pixel of the smoothed mean, restricted to the pixels a full
    cutout fits around.  No fitting and no threshold: over a calibration run the
    mean image has sqrt(N) times the signal-to-noise of a shot, so the spot is
    the largest thing in the window by a wide margin and finding it is not the
    hard part - which is the whole reason for measuring on the mean.
    """
    if mean.shape[0] <= 2 * radius or mean.shape[1] <= 2 * radius:
        return None, None
    interior = _smooth(mean)[radius:-radius, radius:-radius]
    y, x = np.unravel_index(int(np.argmax(interior)), interior.shape)
    return int(y) + radius, int(x) + radius


def _template_width(signal, window_radius=None):
    """(sigma_x, sigma_y) of a background-subtracted cutout, from its second moments.

    A width readout rather than a fit: for a 2D Gaussian <x^2> = sigma^2 about
    the centroid, and the moments need no starting guess and cannot fail to
    converge.

    Measured on the *unclipped* signal, and only out to `window_radius`.  Both
    matter.  Clipping first would leave the positive half of the noise in every
    wing pixel, and second moments weight those by r^2 - on a 200-shot
    simulation that alone read a sigma=1.30 spot as 1.56.  Not windowing would
    keep the moments unbiased but let the same r^2 amplify the noise instead.

    The window has a bias of its own and it is the smaller one: truncating a
    sigma=1.30 spot at radius 4 reads about 5% low (1.22 on the same
    simulation), part from the truncation and part from the cutout being
    centred on a pixel rather than on the atom.  It is a diagnostic, and one
    that is read for gross broadening and for changes between calibrations, so
    a few percent of scale error costs nothing and the factor of four in
    scatter is worth having.  Nothing downstream uses this number - the finders
    get the template itself.

    Read it as the focus check the calibration comes with, and - in 'mean' mode
    - as the position-stability check too: an atom that moves between shots
    smears the mean image, and a width well above the diffraction limit is what
    that looks like.
    """
    weights = np.asarray(signal, dtype=float)
    r = (weights.shape[0] - 1) // 2
    window = (r - 1) if window_radius is None else int(window_radius)
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    inside = (yy ** 2 + xx ** 2) <= window ** 2

    # The centroid comes from the clipped signal: it is a ratio, and a
    # denominator that noise can take through zero is not worth the unbiasedness.
    positive = np.clip(weights, 0, None) * inside
    if positive.sum() <= 0:
        return None, None
    x_mean = float((positive * xx).sum() / positive.sum())
    y_mean = float((positive * yy).sum() / positive.sum())

    windowed = weights * inside
    total = float(windowed.sum())
    if total <= 0:
        return None, None
    var_x = float((windowed * (xx - x_mean) ** 2).sum() / total)
    var_y = float((windowed * (yy - y_mean) ** 2).sum() / total)
    if var_x <= 0 or var_y <= 0:
        return None, None
    return float(np.sqrt(var_x)), float(np.sqrt(var_y))


def _template_from_cutout(cutout, radius, n_sigma=3.0):
    """(template, photons, (sigma_x, sigma_y)) from a mean cutout around an atom.

    The template is background-subtracted on its outer ring and left
    *unnormalised*, because its sum is the photon number the finder needs.  What
    it is not is ``clip(cutout - background, 0)``, which is the obvious way to
    build it and biases both numbers the calibration exists to produce.

    The empty pixels of a dark-subtracted mean scatter symmetrically about zero,
    so clipping deletes the negative half and leaves the positive one.  What
    survives is sigma/sqrt(2 pi) per pixel - small, but there are ~100 empty
    pixels in an 11x11 cutout and only ~10 that hold the atom.  On the 200-shot
    simulation that is +0.80 photons on 7.35, an 11% overestimate of the one
    number the likelihood finders weight photons with, and it grows as the
    calibration gets *longer* relative to the signal it is measuring.  (The same
    trap as the clip term in Calculations/Orca_Quest/orca_dark_background.py,
    and the reason PoissonLikelihoodFinder.fit does not clip either.)

    So the two jobs are separated. The photon number is the sum of the unclipped
    signal, where the noise cancels instead of accumulating. The shape is
    clipped - the finders divide by it and take a log, so it has to be
    non-negative - but only inside the support the measured width says the spot
    occupies; outside it the template is exactly zero rather than clipped noise,
    which is also what stops the wings from diluting the matched filter. The
    shape is then rescaled to carry the unbiased photon number, so no flux is
    lost to the masking.

    Returns photons <= 0 when there is no flux to work with; the caller reports.
    """
    cutout = np.asarray(cutout, dtype=float)
    r = int(radius)
    ring = _cutout_ring(r)
    background = float(np.median(cutout[ring]))
    signal = cutout - background

    photons = float(signal.sum())
    sigma_x, sigma_y = _template_width(signal)
    if photons <= 0 or sigma_x is None:
        return np.clip(signal, 0, None), photons, (sigma_x, sigma_y)

    support = int(np.clip(np.ceil(n_sigma * max(sigma_x, sigma_y)), 2, r))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    template = np.clip(signal, 0, None) * ((yy ** 2 + xx ** 2) <= support ** 2)
    total = float(template.sum())
    if total <= 0:
        return template, 0.0, (sigma_x, sigma_y)
    return template * (photons / total), photons, (sigma_x, sigma_y)


def _loading_fraction(mean_cutout, var_cutout, background, ring, min_signal=0.4):
    """Fraction of the calibration shots that actually held an atom, or None.

    The one thing a mean image cannot tell you by itself.  If an atom is present
    in only a fraction p of the shots, the mean holds p times the PSF - the
    *shape* is untouched, which is why the template is still right, but the
    photon number is low by exactly p, and that number is what the likelihood
    finders weight photons with.

    The variance says what the mean cannot.  Per pixel, with the atom present
    with probability p and delivering s photons on a background b read with
    noise sigma,

        E[x]   = b + p s
        Var[x] = (b + p s) + sigma^2 + p (1 - p) s^2

    so subtracting the variance of the ring - which is b + sigma^2, the same
    pixels the background comes from - and then the background-subtracted mean
    m = p s leaves p (1 - p) s^2.  Divided by m^2 that is (1 - p) / p, a
    constant across pixels, which makes every bright pixel an estimate of the
    same number.

    They are combined as sum(excess) / sum(m^2) over the bright pixels rather
    than as an average of the per-pixel ratios, which is not a detail: m is
    itself measured, dividing by its square before averaging means averaging
    1/m^2, and E[1/m^2] runs above 1/E[m]^2 by three times the relative variance
    of m. On a 120-shot run that read a fully loaded run as 0.89 loaded. Summing
    first puts the noisy quantity in the numerator, where it averages down
    instead of blowing up, and weights each pixel by the m^2 it contributes -
    which is the weighting that says the brightest pixels know the most.

    It needs shots.  Simulated at 7.35 photons on this sensor, over 20 runs per
    point, the estimate of a truly half-loaded run reads

        30 shots   0.70 +- 0.19      200 shots   0.505 +- 0.07
        50 shots   0.66 +- 0.16      400 shots   0.502 +- 0.04
       100 shots   0.52 +- 0.12      800 shots   0.493 +- 0.03

    - biased high below ~100 shots, where the clamp at 1.0 is doing most of the
    work, and unbiased with a scatter of roughly 0.5/sqrt(N) above it.  Hence
    the 100-shot floor in _mean_image_calibration(); a number that reads 0.7
    when the truth is 0.5 is worse than no number.

    Returns None when there are too few shots for a variance to mean anything;
    returns 1.0 when the excess variance is consistent with zero, which is what
    a run where every shot held an atom looks like.
    """
    signal = np.asarray(mean_cutout, dtype=float) - background
    excess = np.asarray(var_cutout, dtype=float) - float(np.median(var_cutout[ring])) - signal
    bright = signal > min_signal * signal.max()
    if not bright.any():
        return None
    weight = float((signal[bright] ** 2).sum())
    if weight <= 0:
        return None
    ratio = float(excess[bright].sum()) / weight
    if not np.isfinite(ratio):
        return None
    return float(min(1.0, 1.0 / (1.0 + max(ratio, 0.0))))


def record_atom_shot(photons, label, image_name, origin, finder=None,
                     template_radius=5, mode='mean'):
    """Add one single-atom shot to the atom calibration for this camera frame.

    What a per-shot routine cannot do is measure the PSF or the photon number:
    it sees one frame per call, and one frame at these rates holds a handful of
    photons in a few pixels.  Those are properties of the *apparatus*, so they
    are measured once over a run of shots that each contain an atom, and this
    accumulates that run.  Two ways, and they differ in where the atom is
    located:

    'mean'  Accumulate the frames themselves and locate the atom once, at the
            end, in their mean.  Correct when the atom sits at the same place
            every shot, and then strictly better than the alternative: the
            locating is done at sqrt(N) times the signal-to-noise, the sampled
            PSF keeps the sub-pixel phase the atom really has instead of being
            smeared over the pixel by per-shot rounding, and a shot that held no
            atom contributes its background rather than a noise peak.  No finder
            is needed or used.
    'peak'  Locate the brightest candidate in each shot with the configured
            finder and average the cutouts around it - shift-and-add.  The mode
            for an atom that moves between shots, at the cost of centring each
            cutout on an integer pixel of a frame with a handful of photons in
            it.

    Stored the way the dark frame is - running sums plus a count - rather than
    as a stack of frames.  It keeps the disk usage flat in the number of shots,
    and it means the calibration is finished the moment the last shot lands
    instead of needing a separate pass.  'mean' keeps the sum of the squares as
    well, which costs one more array and buys the loading fraction; see
    _loading_fraction().

    Positions go in *full-frame* coordinates, so a later change of
    ``orca_af_roi_center`` / ``orca_af_roi_size`` does not silently move the
    measured position with respect to the sensor.

    Returns ``(n_shots, message)``; n_shots is None when the shot contributed
    nothing.
    """
    r = int(template_radius)
    if mode == 'mean':
        n_shots, message = _accumulate_mean_frame(photons, label, image_name, origin, r)
    else:
        n_shots, message = _accumulate_peak_cutout(photons, label, image_name, origin,
                                                   finder, r)
    if n_shots is not None:
        _write_atom_cal_metadata(label, image_name, r)
    return n_shots, message


def _accumulate_mean_frame(photons, label, image_name, origin, radius):
    """'mean' mode: add the whole analysis window to the running mean and variance."""
    accum_file, _meta = _atom_cal_paths(label, image_name)
    frame = np.asarray(photons, dtype=float)
    origin = tuple(int(v) for v in origin)

    frame_sum, frame_sqsum, n_frames = frame.copy(), frame ** 2, 1
    if accum_file.exists():
        try:
            with np.load(accum_file) as acc:
                previous = str(acc['mode']) if 'mode' in acc.files else 'peak'
                if previous != 'mean':
                    print(f'orca_atom_finder_analysis: the atom calibration for '
                          f'"{label}/{image_name}" was recorded in {previous!r} mode - '
                          'starting it over in "mean" mode.')
                elif acc['frame_sum'].shape != frame.shape:
                    print(f'orca_atom_finder_analysis: analysis window changed '
                          f'({acc["frame_sum"].shape} -> {frame.shape}) for '
                          f'"{label}/{image_name}" - starting the atom calibration over.')
                elif tuple(np.asarray(acc['origin']).ravel()) != origin:
                    # A window of the same size somewhere else on the sensor is a
                    # different set of pixels, and averaging the two would average
                    # two different parts of the PSF on top of each other.
                    print(f'orca_atom_finder_analysis: analysis window moved for '
                          f'"{label}/{image_name}" - starting the atom calibration over.')
                else:
                    frame_sum = acc['frame_sum'] + frame
                    frame_sqsum = acc['frame_sqsum'] + frame ** 2
                    n_frames = int(acc['n_frames']) + 1
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not read atom calibration '
                  f'"{accum_file}": {e} - starting it over.')

    np.savez(accum_file, mode='mean', frame_sum=frame_sum, frame_sqsum=frame_sqsum,
             n_frames=n_frames, origin=np.asarray(origin, dtype=int),
             template_radius=int(radius))
    return n_frames, 'frame added to the mean'


def _accumulate_peak_cutout(photons, label, image_name, origin, finder, radius):
    """'peak' mode: locate the atom in this shot and add the cutout around it."""
    accum_file, _meta = _atom_cal_paths(label, image_name)
    r = int(radius)
    y0, x0 = origin

    if finder is None:
        return None, 'no finder available to locate the atom in this shot'
    try:
        candidates = finder.find(photons, None)
    except Exception as e:
        return None, f'the finder failed on this shot ({e})'
    if not candidates:
        return None, 'no candidate found in this shot'
    best = max(candidates, key=lambda c: c['score'])
    y, x = int(best['y']), int(best['x'])

    if not (r <= y < photons.shape[0] - r and r <= x < photons.shape[1] - r):
        # The same rule psf_template() applies: a cutout that runs off the
        # frame would average a clipped spot into the template.
        return None, (f'the brightest candidate sits at ({x}, {y}), closer than '
                      f'{r} px to the edge of the analysis window - not usable for '
                      f'the template')

    cutout = np.asarray(photons[y - r:y + r + 1, x - r:x + r + 1], dtype=float)
    row = np.array([[x + x0, y + y0, float(best['score'])]], dtype=float)

    template_sum, n_template, peaks = cutout, 1, row
    if accum_file.exists():
        try:
            with np.load(accum_file) as acc:
                previous = str(acc['mode']) if 'mode' in acc.files else 'peak'
                if previous != 'peak':
                    print(f'orca_atom_finder_analysis: the atom calibration for '
                          f'"{label}/{image_name}" was recorded in {previous!r} mode - '
                          'starting it over in "peak" mode.')
                elif int(acc['template_radius']) == r and acc['template_sum'].shape == cutout.shape:
                    template_sum = acc['template_sum'] + cutout
                    n_template = int(acc['n_template']) + 1
                    peaks = np.vstack([acc['peaks'], row])
                else:
                    print(f'orca_atom_finder_analysis: template radius changed for '
                          f'"{label}/{image_name}" - starting the atom calibration over.')
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not read atom calibration '
                  f'"{accum_file}": {e} - starting it over.')

    np.savez(accum_file, mode='peak', template_sum=template_sum, n_template=n_template,
             template_radius=r, peaks=peaks)
    return n_template, f'atom at ({x + x0}, {y + y0}), score {best["score"]:.1f}'


def _write_atom_cal_metadata(label, image_name, radius):
    """Mirror what the accumulator now says into the .json beside it."""
    _accum, meta_file = _atom_cal_paths(label, image_name)
    calibration = atom_calibration(label, image_name)
    if calibration is None:
        return
    # The position summary stays None until there are enough shots to measure
    # it, so the metadata has to survive a half-done calibration.
    center = calibration['position_center']
    sigma_x, sigma_y = calibration['psf_sigma']
    try:
        with open(meta_file, 'w') as f:
            json.dump({'label': label,
                       'image_name': image_name,
                       'mode': calibration['mode'],
                       'n_shots': int(calibration['n_shots']),
                       'photons': float(calibration['photons']),
                       # Diagnostics only - see atom_calibration().
                       'position_center_full': None if center is None else list(center),
                       'position_spread_px':
                           _as_float_or_none(calibration['position_spread']),
                       'psf_sigma_x_px': _as_float_or_none(sigma_x),
                       'psf_sigma_y_px': _as_float_or_none(sigma_y),
                       'loading_fraction': _as_float_or_none(calibration['loading']),
                       'template_radius': int(radius)}, f, indent=2)
    except Exception as e:
        print(f'orca_atom_finder_analysis: could not write atom calibration '
              f'metadata: {e}')


def atom_calibration(label, image_name, prior_quantile=0.3):
    """The measured PSF and photon number, plus where the atoms sat, or None.

    Derived from the accumulator every time rather than stored: the shots keep
    arriving, and a stored answer would go stale the moment one more lands.

    Both modes end at the same place - one mean cutout around the atom, turned
    into a template by _template_from_cutout(), which is where the background
    subtraction and the photon number live.  They differ only in how the atom
    was located; see record_atom_shot().

    Returns a dict with the template, its photon number, the measured width, the
    position and - in 'mean' mode - the loading fraction, or None when there is
    nothing recorded yet.
    """
    accum_file, _meta = _atom_cal_paths(label, image_name)
    if not accum_file.exists():
        return None
    try:
        with np.load(accum_file) as acc:
            stored = {key: acc[key] for key in acc.files}
    except Exception as e:
        print(f'orca_atom_finder_analysis: could not read atom calibration '
              f'"{accum_file}": {e}')
        return None

    mode = str(stored['mode']) if 'mode' in stored else 'peak'
    if mode == 'mean':
        return _mean_image_calibration(stored, label, image_name)
    return _shift_and_add_calibration(stored, label, image_name, prior_quantile)


def _mean_image_calibration(stored, label, image_name):
    """The PSF read off the mean of the calibration shots."""
    n_shots = int(stored.get('n_frames', 0))
    if n_shots <= 0:
        return None
    r = int(stored['template_radius'])
    mean = np.asarray(stored['frame_sum'], dtype=float) / n_shots
    y0, x0 = (int(v) for v in np.asarray(stored['origin']).ravel())

    y, x = _locate_in_mean(mean, r)
    if y is None:
        print(f'orca_atom_finder_analysis: the analysis window for '
              f'"{label}/{image_name}" is too small for a {2 * r + 1} px template.')
        return None

    cutout = mean[y - r:y + r + 1, x - r:x + r + 1]
    template, photons, sigma = _template_from_cutout(cutout, r)
    if photons <= 0:
        print(f'orca_atom_finder_analysis: the atom calibration for '
              f'"{label}/{image_name}" holds no flux - record it again.')
        return None

    loading = None
    if 'frame_sqsum' in stored and n_shots >= 100:      # see _loading_fraction()
        # Bessel-corrected, though at these shot counts it changes nothing; the
        # point is that the variance is an estimate and should be named as one.
        variance = (np.asarray(stored['frame_sqsum'], dtype=float) / n_shots
                    - mean ** 2) * (n_shots / (n_shots - 1.0))
        ring = _cutout_ring(r)
        loading = _loading_fraction(cutout, variance[y - r:y + r + 1, x - r:x + r + 1],
                                    float(np.median(cutout[ring])), ring)

    return {'template': template,
            'photons': photons,
            'template_radius': r,
            'n_shots': n_shots,
            'mode': 'mean',
            # One position, measured once, so there is no spread to report - the
            # width of the spot carries that information instead.
            'position_center': (float(x + x0), float(y + y0)),
            'position_spread': None,
            'psf_sigma': sigma,
            'loading': loading}


def _shift_and_add_calibration(stored, label, image_name, prior_quantile):
    """The PSF averaged over per-shot cutouts, each centred on its own atom."""
    n_shots = int(stored.get('n_template', 0))
    if n_shots <= 0:
        return None
    r = int(stored['template_radius'])
    cutout = np.asarray(stored['template_sum'], dtype=float) / n_shots
    peaks = np.asarray(stored['peaks'], dtype=float).reshape(-1, 3)

    template, photons, sigma = _template_from_cutout(cutout, r)
    if photons <= 0:
        print(f'orca_atom_finder_analysis: the atom calibration for '
              f'"{label}/{image_name}" holds no flux - record it again.')
        return None

    # Where the atoms sat, in full-frame coordinates. Reported, not applied:
    # nothing in this routine turns it into a position prior (see
    # build_finder), because a detector that already knows where to look is a
    # detector that will not find an atom anywhere else. It is worth reading,
    # though - it says whether the atoms move between shots at all, which is
    # exactly the question of whether 'mean' mode is the right one.
    center = spread = None
    if len(peaks) >= 30 and position_prior is not None:
        center, _floored, spread, _n = position_prior(
            peaks[:, 0], peaks[:, 1], peaks[:, 2],
            quantile=prior_quantile, min_sigma=0.0)

    return {'template': template,
            'photons': photons,
            'template_radius': r,
            'n_shots': n_shots,
            'mode': 'peak',
            'position_center': center,
            'position_spread': spread,
            'psf_sigma': sigma,
            # Every shot contributes its brightest candidate whether or not it
            # held an atom, so there is no empty class to measure against.
            'loading': None}


def clear_atom_calibration(label=None, image_name=None):
    """Drop the recorded atom calibration so the next run starts fresh."""
    if label is None:
        pattern = 'orca_atomcal_*'
        files = list(_ASSET_DIR.glob(f'{pattern}.npz')) + list(_ASSET_DIR.glob(f'{pattern}.json'))
    else:
        files = [p for p in _atom_cal_paths(label, image_name) if p.exists()]
    for path in files:
        try:
            path.unlink()
            print(f'orca_atom_finder_analysis: cleared atom calibration {path.name}')
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not clear "{path}": {e}')


def clear_dark_accumulators():
    """Drop every dark accumulator so the next recording session starts fresh."""
    for accum_file in _ASSET_DIR.glob('orca_dark_*_accum.npz'):
        try:
            accum_file.unlink()
            print(f'orca_atom_finder_analysis: cleared dark accumulator {accum_file.name}')
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not clear "{accum_file}": {e}')


# ──────────────────────────────────────────────────────────────────────────────
# Analysis window, ROI overlays and finder configuration
# ──────────────────────────────────────────────────────────────────────────────

def analysis_rois(run_globals, y0=0, x0=0):
    """ROI rectangles for the overlay, as an (N, 4) array of [x, y, width, height].

    Reads the very same ``orca_roi_center_1/2`` and ``orca_roi_size_1/2`` globals
    that ``orca_image_analysis.py`` uses, so the boxes in the "Orca Atom Finder"
    dock are the boxes in the "Orca Images" dock - both come from the globals
    rather than from each other.  Hard cap of 2 ROIs, matching that routine.

    The centres are shifted by the analysis window origin, so they are in the
    coordinates of the saved (cropped) image just like the detections are.  A
    ROI can therefore land outside the image, which simply puts the box out of
    view; it is kept rather than dropped so the overlay still tells you the ROI
    is not where you are looking.
    """
    rois = []
    for slot in (1, 2):
        center = run_globals.get(f'orca_roi_center_{slot}')
        size   = run_globals.get(f'orca_roi_size_{slot}')
        if center is None or size is None:
            continue
        try:
            rois.append([float(center[0]) - x0, float(center[1]) - y0,
                         float(size[0]), float(size[1])])
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not parse orca_roi_center_{slot}/'
                  f'orca_roi_size_{slot} ({e}) — skipping that ROI.')
    return np.array(rois, dtype=float) if rois else np.empty((0, 4), dtype=float)


def crop_window(run_globals, img_shape):
    """Analysis window as ``(y_slice, x_slice, y0, x0)``, clipped to the frame.

    Set by ``orca_af_roi_center`` / ``orca_af_roi_size``; the full frame is used
    when either is missing.
    """
    height, width = img_shape
    center = run_globals.get('orca_af_roi_center')
    size   = run_globals.get('orca_af_roi_size')
    if center is None or size is None:
        return slice(0, height), slice(0, width), 0, 0
    try:
        x0 = int(round(float(center[0]) - float(size[0]) / 2))
        x1 = int(round(float(center[0]) + float(size[0]) / 2))
        y0 = int(round(float(center[1]) - float(size[1]) / 2))
        y1 = int(round(float(center[1]) + float(size[1]) / 2))
    except Exception as e:
        print(f'orca_atom_finder_analysis: could not parse orca_af_roi_center/size ({e}) — '
              'using the full frame.')
        return slice(0, height), slice(0, width), 0, 0

    x0, x1 = max(0, min(x0, width)),  max(0, min(x1, width))
    y0, y1 = max(0, min(y0, height)), max(0, min(y1, height))
    if x1 <= x0 or y1 <= y0:
        print('orca_atom_finder_analysis: analysis window is empty after clipping to the '
              'frame — using the full frame.')
        return slice(0, height), slice(0, width), 0, 0
    return slice(y0, y1), slice(x0, x1), y0, x0


def _note(notes, text):
    """Record a reason the finder is not what the globals asked for, and say so."""
    print(f'orca_atom_finder_analysis: {text}')
    if notes is not None:
        notes.append(text)


def _as_dict(value, name, notes=None):
    """Coerce a global to a dict of keyword arguments."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, (str, bytes)):
        text = value.decode() if isinstance(value, bytes) else value
        try:
            parsed = ast.literal_eval(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    _note(notes, f'ignoring {name}={value!r} (expected a dict) - the finder runs on '
                 'its defaults instead')
    return {}


def _as_sites(value, notes=None):
    """Coerce a global to a list of (x, y) tuples, or None."""
    if value is None:
        return None
    if isinstance(value, (str, bytes)):
        text = value.decode() if isinstance(value, bytes) else value
        try:
            value = ast.literal_eval(text)
        except Exception:
            _note(notes, f'ignoring orca_af_sites={text!r} (not a valid literal)')
            return None
    try:
        sites = [(float(x), float(y)) for x, y in value]
    except Exception:
        _note(notes, f'ignoring orca_af_sites={value!r} (expected [(x, y), ...])')
        return None
    return sites or None


def accepted_keywords(name):
    """Every keyword the named finder's constructor takes, or None if unreadable.

    Walks the MRO instead of reading one signature.  The finders forward
    ``**kwargs`` to their parent - 'poisson_llr_calibrated' declares five
    keywords of its own and inherits eleven more - so a set built from its own
    signature alone would call `photons` and `aperture_radius` unsupported and
    throw away the keywords that work.  The walk stops at the first ``__init__``
    that does not forward, which is where the keywords actually run out.
    """
    cls = FINDERS.get(name)
    if cls is None:
        return None
    keywords = set()
    for klass in getattr(cls, '__mro__', ()):
        init = klass.__dict__.get('__init__')
        if init is None:
            continue
        try:
            parameters = inspect.signature(init).parameters
        except (TypeError, ValueError):
            return None      # cannot tell what it takes - do not filter anything
        keywords.update(p for p, spec in parameters.items()
                        if p != 'self' and spec.kind in (spec.POSITIONAL_OR_KEYWORD,
                                                         spec.KEYWORD_ONLY))
        if not any(spec.kind is spec.VAR_KEYWORD for spec in parameters.values()):
            break
    return keywords


def accepted_params(name):
    """', accepts: a, b, c' for the named finder, or '' if it cannot be read.

    A misspelled key in ``orca_af_finder_params`` is the easy mistake to make
    here - the finder labels print the constructor keywords, but the aperture
    is `aperture_radius` and not `aperture`, and a wrong one used to cost the
    whole configuration.  Listing what the finder does take turns that into a
    one-line fix.
    """
    keywords = accepted_keywords(name)
    return f', accepts: {", ".join(sorted(keywords))}' if keywords else ''


def requested_label(run_globals):
    """The finder the globals ask for, as written there.

    Kept beside the finder that actually ran: a fallback produces a perfectly
    ordinary-looking result, so without the request next to it there is no way
    to tell a shot analysed as configured from one where the configuration was
    dropped on the floor.
    """
    name = run_globals.get('orca_af_finder')
    text = str(name) if name else 'matched_filter (default)'
    params = run_globals.get('orca_af_finder_params')
    if isinstance(params, bytes):
        params = params.decode()
    return text if params in (None, '') else f'{text} {params}'


def build_finder(run_globals, images=None, sites=None, notes=None, calibration=None):
    """Instantiate the finder named by ``orca_af_finder``, fitted if it needs it.

    Every fallback taken on the way is appended to ``notes`` as well as
    printed, so it reaches the shot file and the plot panel rather than only
    the lyse output of the one run that happened to be watched.

    ``calibration`` is what this camera frame knows about itself: the dark run
    to model rather than subtract, the per-pixel read noise from the comb
    contrast, and the measured PSF.  A finder is handed only the parts it can
    use - the sensor terms go to 'poisson_llr_calibrated', which is the one
    that models them, and the PSF to any finder with a use_psf().  Anything set
    in ``orca_af_finder_params`` wins over all of it, so the globals stay the
    place to overrule a calibration you do not trust.

    What the calibration deliberately does *not* carry is where the atoms sat.
    None of the finders has a positional prior any more - see
    CalibratedPoissonFinder's docstring for why not - so the measured position
    is reported and nothing else.
    """
    calibration = calibration or {}
    if make_finder is None:
        _note(notes, 'AtomFinders could not be imported - no detection at all')
        return None

    name = run_globals.get('orca_af_finder') or 'matched_filter'
    name = str(name)
    if name not in FINDERS:
        _note(notes, f'unknown finder {name!r}, falling back to "matched_filter" '
                     f'(available: {sorted(FINDERS)})')
        name = 'matched_filter'

    params = _as_dict(run_globals.get('orca_af_finder_params'), 'orca_af_finder_params',
                      notes)
    if name == 'fixed_site' and 'sites' not in params and sites:
        params['sites'] = sites

    # The sensor terms mean something only to the finder that models them: the
    # parent's soft_counts() takes a scalar read noise and no dark image, so a
    # per-pixel map would break it rather than improve it.
    if name == 'poisson_llr_calibrated':
        for key in ('dark_image', 'n_dark_shots', 'read_noise'):
            if key not in params and calibration.get(key) is not None:
                params[key] = calibration[key]

    # A keyword the finder does not take is dropped with a note rather than
    # allowed to fail the construction. It used to fail it, and the fallback
    # that followed was the whole analysis: one stale key in the globals - a
    # 'prior_sigma' left over from a finder that no longer has a positional
    # prior, say - silently downgraded every shot to the default matched_filter,
    # which is a perfectly ordinary-looking result and not the one asked for.
    # Dropping the key runs the finder that was requested with the settings that
    # exist, and says which one it ignored.
    accepted = accepted_keywords(name)
    if accepted is not None:
        unknown = sorted(set(params) - accepted)
        if unknown:
            _note(notes, f'{name} does not take {", ".join(unknown)} - ignored'
                         f'{accepted_params(name)}')
            params = {key: value for key, value in params.items() if key in accepted}

    try:
        finder = make_finder(name, **params)
    except Exception as e:
        _note(notes, f'could not build finder {name!r} with {params!r}: {e}'
                     f'{accepted_params(name)} - falling back to the default '
                     'matched_filter')
        try:
            finder = make_finder('matched_filter')
        except Exception as e2:
            _note(notes, f'default finder failed too: {e2}')
            return None

    # Before the fit: fit() then sees that the PSF is already measured and says
    # so, instead of reporting a Gaussian fallback it did not fall back to.
    template = calibration.get('template')
    if template is not None and hasattr(finder, 'use_psf'):
        finder.use_psf(template, source=f'{calibration.get("n_shots", 0)}-shot calibration')

    if finder.needs_fit:
        try:
            finder.fit(images or [], sites)
        except Exception as e:
            _note(notes, f'{finder.name}.fit() failed: {e} - running unfitted')
    # The delivered background rate is the number this finder exists to get
    # right - its own docstring says too small a `b` makes single photons in
    # the wings look decisive - and it is floored rather than allowed to be
    # zero, so a dark run that comes out at or below zero fails quietly and
    # produces *more* false positives, not fewer. Say so.
    rate = getattr(finder, '_rate', None)
    floor = getattr(finder, 'background_floor', None)
    if images and rate is not None and floor is not None and rate <= floor:
        _note(notes, f'{finder.name}: the background rate came out at the floor '
                     f'({floor:g} photons/px) - the dark run says the sensor delivers '
                     f'{finder.background if finder.background is not None else 0.0:.4g}, '
                     f'which cannot be right. Re-record the dark frame; until then the '
                     f'log weights are far too credulous and the false positives will '
                     f'show it.')

    if getattr(finder, 'degraded', False) and notes is not None:
        # Only the fit fallbacks that void the point of the finder are raised
        # here. The rest - a poisson_llr searching with the Gaussian PSF it
        # documents, say - are still reported, in the settings string that
        # describe() builds, but they are configurations rather than
        # accidents and a shot is not flagged for them.
        notes.append(f'{finder.name}: {finder.fit_note}')
    return finder


def detections_array(detections, max_detections=500):
    """Detections as an (N, 5) array of [x, y, photons, score, snr], brightest first.

    ``snr`` is NaN for finders that do not report one; ``photons`` falls back to
    the score (LowPassFinder scores by amplitude but still reports photons).
    """
    rows = []
    for det in detections:
        rows.append([float(det['x']),
                     float(det['y']),
                     float(det.get('photons', det.get('score', np.nan))),
                     float(det.get('score', np.nan)),
                     float(det.get('snr', np.nan))])
    if not rows:
        return np.empty((0, 5), dtype=float)
    array = np.array(rows, dtype=float)
    array = array[np.argsort(array[:, 3])[::-1]]      # brightest score first
    return array[:int(max_detections)]


# ──────────────────────────────────────────────────────────────────────────────
# Shot
# ──────────────────────────────────────────────────────────────────────────────

try:
    h5_path = lyse.path
except AttributeError:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)
run_globals = run.get_globals()

try:
    all_labels = run.get_all_image_labels()
except Exception as e:
    print(f'orca_atom_finder_analysis: could not get image labels: {e}')
    all_labels = {}

# ── Collect every raw frame from a camera label starting with "orca" ───────────
collected = {}  # {(orientation, label, image_name): raw array}
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
                for image_name, item in label_group.items():
                    if not isinstance(item, h5py.Dataset):
                        continue
                    try:
                        raw = np.array(item, dtype='float')
                        collected[(orientation, label, image_name)] = raw[0] if raw.ndim == 3 else raw
                    except Exception as e:
                        print(f'orca_atom_finder_analysis: error reading image "{image_name}" '
                              f'in label "{label}": {e}')
except Exception as e:
    print(f'orca_atom_finder_analysis: error reading h5 file: {e}')

if not collected:
    print('orca_atom_finder_analysis: no images found with labels starting with "orca"')

# ── Calibration maps ──────────────────────────────────────────────────────────
orca_offset_map, orca_gain_map, orca_pixels_failed = _load_calibration(run_globals)
if orca_gain_map is None or orca_offset_map is None:
    print('orca_atom_finder_analysis: no gain/offset calibration found — falling back to '
          f'scalar defaults (offset={DEFAULT_OFFSET}, gain={DEFAULT_GAIN} ADU/photon).')
_subarray_offset = run_globals.get('orca_subarray_offset')

# ── Dark recording mode ───────────────────────────────────────────────────────
record_dark_mode = bool(run_globals.get('orca_af_record_dark', False))
dark_average     = bool(run_globals.get('orca_af_dark_average', True))

if record_dark_mode and collected:
    print('=' * 60)
    print('RECORDING ORCA DARK FRAME(S)')
    print('=' * 60)
    for (orientation, label, image_name), raw in collected.items():
        try:
            dark, n_shots = record_dark(raw, label, image_name,
                                        average=dark_average, source=h5_path)
            print(f'  {label}/{image_name}: dark updated over {n_shots} shot(s), '
                  f'mean {np.mean(dark):.1f} ADU')
            prefix = f'{label}_{image_name}'
            run.save_result(f'{prefix}_dark_recorded', True, group='results/' + GROUP)
            run.save_result(f'{prefix}_dark_shots', int(n_shots), group='results/' + GROUP)
        except Exception as e:
            print(f'orca_atom_finder_analysis: could not record dark for '
                  f'"{label}/{image_name}": {e}')
    print('Set orca_af_record_dark=False in the globals for normal analysis.')
    # Nothing else to do: the frames of a dark shot hold no atoms.
    collected = {}
elif not record_dark_mode:
    clear_dark_accumulators()

# ── Per-pixel read noise, from the comb contrast of the calibration ───────────
# Only 'poisson_llr_calibrated' can use it; loaded once here because it is a
# property of the sensor, not of the frame, and cropped per frame below.
orca_read_noise = None
_calibration_path = run_globals.get('orca_calibration_path') or (
    _calib_npz if _calib_npz.exists() else None)
if read_noise_map is not None and _calibration_path and Path(_calibration_path).exists():
    try:
        orca_read_noise = read_noise_map(_calibration_path)
    except Exception as e:
        print(f'orca_atom_finder_analysis: could not build the read-noise map from '
              f'"{_calibration_path}": {e} — the scalar read noise will be used.')

# ── Photon conversion and dark subtraction ────────────────────────────────────
# The offset map already removes the sensor bias; the dark frame takes out what
# is left (dark current, stray light). Both are converted with the same
# calibration, so subtracting in photon space is the same as subtracting the
# ADU frames and dividing by the gain.
#
# The dark is kept in photon units beside the corrected frame, not thrown away:
# 'poisson_llr_calibrated' adds it back and models it as a rate instead, since
# subtracting it takes the level but leaves the shot noise it caused.
processed = {}   # {(orientation, label, image_name): dict, see below}
for (orientation, label, image_name), raw in collected.items():
    try:
        offset_map = _match_map_to_image(orca_offset_map, raw.shape, _subarray_offset)
        gain_map   = _match_map_to_image(orca_gain_map,   raw.shape, _subarray_offset)
        failed_map = _match_map_to_image(orca_pixels_failed, raw.shape, _subarray_offset)
        if orca_gain_map is not None and gain_map is None:
            print(f'orca_atom_finder_analysis: calibration shape {orca_gain_map.shape} does '
                  f'not match image shape {raw.shape} for "{label}/{image_name}" and no '
                  'usable subarray offset was given — using scalar defaults for this frame.')

        photons = counts_to_photons(raw, offset_map, gain_map, failed_map)

        dark, n_dark = load_dark(label, image_name, raw.shape)
        dark_photons = None
        if dark is not None:
            dark_photons = counts_to_photons(dark, offset_map, gain_map, failed_map)
            photons = photons - dark_photons
        else:
            if not _dark_paths(label, image_name)[0].exists():
                print(f'orca_atom_finder_analysis: no dark frame for "{label}/{image_name}" — '
                      'analysing without dark subtraction (record one with '
                      'orca_af_record_dark=True).')
            n_dark = 0

        y_sl, x_sl, y0, x0 = crop_window(run_globals, photons.shape)
        read_noise = _match_map_to_image(orca_read_noise, raw.shape, _subarray_offset)
        processed[(orientation, label, image_name)] = {
            'photons': np.ascontiguousarray(photons[y_sl, x_sl]),
            'dark_photons': (None if dark_photons is None
                             else np.ascontiguousarray(dark_photons[y_sl, x_sl])),
            'read_noise': None if read_noise is None else read_noise[y_sl, x_sl],
            'dark_subtracted': dark is not None,
            'n_dark': n_dark,
            'origin': (y0, x0),
        }
    except Exception as e:
        print(f'orca_atom_finder_analysis: error processing '
              f'"{orientation}/{label}/{image_name}": {e}')


def frame_calibration(label, image_name, frame):
    """Everything build_finder() can tell this camera frame's finder about itself.

    The sensor half (dark run, read noise) comes from the frame that was just
    processed; the atom half (the PSF and the photon number it carries) from
    the calibration run recorded with ``orca_af_record_atoms``.

    All of it describes the apparatus and none of it says where an atom is,
    which is what makes a calibration recorded at one position safe to use on
    shots taken at another.  The measured position is deliberately left out -
    it is a diagnostic and nothing reads it; see build_finder().
    """
    calibration = {'dark_image': frame['dark_photons'],
                   'n_dark_shots': frame['n_dark'] or None,
                   'read_noise': frame['read_noise']}

    measured = atom_calibration(label, image_name)
    if measured is not None:
        calibration['template'] = measured['template']
        calibration['n_shots'] = measured['n_shots']
    return calibration

# ── Finder configuration from the globals ─────────────────────────────────────
finder_notes = []
sites = _as_sites(run_globals.get('orca_af_sites'), finder_notes)
threshold = run_globals.get('orca_af_threshold')
threshold = None if threshold is None else float(threshold)
max_detections = int(run_globals.get('orca_af_max_detections', 500))

# ── Atom calibration recording ────────────────────────────────────────────────
# Unlike the dark run these are ordinary shots, so they are analysed as usual
# afterwards; recording only adds this shot to what the finders are told about
# the atom - the PSF and the photons it carries, neither of which depends on
# where the atom was when it was measured.
if bool(run_globals.get('orca_af_atom_cal_reset', False)):
    clear_atom_calibration()

atom_cal_mode = str(run_globals.get('orca_af_atom_cal_mode', 'mean')).strip().lower()
if atom_cal_mode not in ('mean', 'peak'):
    print(f'orca_atom_finder_analysis: unknown orca_af_atom_cal_mode={atom_cal_mode!r} '
          "- using 'mean' (the other option is 'peak').")
    atom_cal_mode = 'mean'

if bool(run_globals.get('orca_af_record_atoms', False)) and processed:
    print('=' * 60)
    print(f'RECORDING ORCA ATOM CALIBRATION ({atom_cal_mode} mode)')
    print('=' * 60)
    for (_orientation, label, image_name), frame in processed.items():
        # 'mean' mode locates the atom once, in the accumulated mean, so there is
        # nothing to locate per shot and no finder to build.
        locator = None
        if atom_cal_mode == 'peak':
            locator = build_finder(run_globals,
                                   images=[frame['photons']],
                                   sites=sites,
                                   calibration=frame_calibration(label, image_name, frame))
            if locator is None:
                print('  no finder available - cannot locate the atom to calibrate on.')
                break
        n_shots, message = record_atom_shot(frame['photons'], label, image_name,
                                            frame['origin'], locator,
                                            mode=atom_cal_mode)
        if n_shots is None:
            print(f'  {label}/{image_name}: skipped - {message}')
            continue

        summary = atom_calibration(label, image_name)
        detail = ''
        if summary is not None:
            detail = f', photons={summary["photons"]:.2f}'
            sigma_x, sigma_y = summary['psf_sigma']
            if sigma_x is not None:
                detail += f', sigma=({sigma_x:.2f}, {sigma_y:.2f}) px'
            if summary['position_center'] is not None:
                detail += (f', at (x={summary["position_center"][0]:.0f}, '
                           f'y={summary["position_center"][1]:.0f})')
            if summary['position_spread'] is not None:
                detail += f' within {summary["position_spread"]:.1f} px'
            if summary['loading'] is not None:
                detail += f', loading={summary["loading"]:.2f}'
        print(f'  {label}/{image_name}: {message}; {n_shots} shot(s) recorded{detail}')

        # The one way the mean image can mislead: a run in which only some shots
        # held an atom averages to that fraction of the PSF. The shape survives
        # it, the photon number does not, and photons is what the likelihood
        # finders weight with - so say it rather than quietly hand over a number
        # that is too small by a factor nobody knows.
        #
        # 0.85 rather than 0.9 because the estimate scatters: at the 100-shot
        # floor a fully loaded run reads 0.97 +- 0.05, so a 0.9 line would cry
        # wolf on about one calibration in twelve. The number itself is printed
        # either way, so nothing is hidden by not warning about it.
        if summary is not None and summary['loading'] is not None and summary['loading'] < 0.85:
            print(f'    !! the variance says only {summary["loading"]:.0%} of these shots '
                  f'held an atom, so photons={summary["photons"]:.2f} is that fraction of '
                  f'what one atom delivers (about '
                  f'{summary["photons"] / summary["loading"]:.2f}). Record on shots that '
                  f'each contain an atom, or scale the finder\'s photons yourself.')
    print('Set orca_af_record_atoms=False in the globals when the run is done.')

# One finder per frame: the dark run, the read-noise map and the measured PSF
# all belong to a particular camera frame, and a shot can hold more than one.
requested = requested_label(run_globals)
finders = {}
for key, frame in processed.items():
    _orientation, label, image_name = key
    finders[key] = build_finder(run_globals,
                                images=[frame['photons']],
                                sites=sites,
                                notes=finder_notes,
                                calibration=frame_calibration(label, image_name, frame))
# No frames means a dark-recording shot: there is nothing to configure a finder
# against, and building one anyway would report a fit that never had any data.
finder = next(iter(finders.values()), None)
threshold_text = 'none' if threshold is None else f'{threshold:g}'

if processed:
    print('-' * 60)
    print(f'orca_atom_finder_analysis: requested  {requested}')
    if finder is None:
        print('orca_atom_finder_analysis: in use      nothing - images saved without '
              'detections')
    else:
        print(f'orca_atom_finder_analysis: in use      {finder.describe()}')
        print(f'orca_atom_finder_analysis: threshold   {threshold_text} '
              f'({finder.score_label})')
    for note in dict.fromkeys(finder_notes):      # one line per distinct note
        print(f'orca_atom_finder_analysis: !!          {note}')
    print('-' * 60)

# ── Detection and results ─────────────────────────────────────────────────────
saved_frames = []
for key, frame in processed.items():
    orientation, label, image_name = key
    photons = frame['photons']
    dark_subtracted, n_dark = frame['dark_subtracted'], frame['n_dark']
    y0, x0 = frame['origin']
    frame_finder = finders.get(key, finder)
    prefix = f'{label}_{image_name}'
    try:
        atoms = np.empty((0, 5), dtype=float)
        if frame_finder is not None:
            try:
                atoms = detections_array(frame_finder.find(photons, threshold),
                                         max_detections)
            except Exception as e:
                print(f'orca_atom_finder_analysis: {frame_finder.name}.find() failed for '
                      f'"{prefix}": {e}')

        run.save_result_array(f'{prefix}_photons', photons.astype(np.float32),
                              group='results/' + GROUP)
        run.save_result_array(f'{prefix}_detections', atoms, group='results/' + GROUP)
        run.save_result_array(f'{prefix}_crop',
                              np.array([y0, x0, photons.shape[0], photons.shape[1]],
                                       dtype=float),
                              group='results/' + GROUP)
        run.save_result_array(f'{prefix}_roi_metadata', analysis_rois(run_globals, y0, x0),
                              group='results/' + GROUP)

        run.save_result(f'{prefix}_n_atoms', int(atoms.shape[0]), group='results/' + GROUP)
        run.save_result(f'{prefix}_photons_sum', float(photons.sum()),
                        group='results/' + GROUP)
        run.save_result(f'{prefix}_atom_photons_sum',
                        float(np.nansum(atoms[:, 2])) if atoms.size else 0.0,
                        group='results/' + GROUP)
        run.save_result(f'{prefix}_dark_subtracted', bool(dark_subtracted),
                        group='results/' + GROUP)
        run.save_result(f'{prefix}_dark_shots', int(n_dark), group='results/' + GROUP)

        saved_frames.append(f'{orientation}|{label}|{image_name}')
        print(f'orca_atom_finder_analysis: {prefix}: {atoms.shape[0]} atom(s) found'
              + (f', dark averaged over {n_dark} shot(s)' if dark_subtracted else
                 ', no dark subtracted'))
    except Exception as e:
        print(f'orca_atom_finder_analysis: error saving results for "{prefix}": {e}')

# Index and finder configuration for the plot panel.
run.save_result('orca_af_frames', ','.join(saved_frames), group='results/' + GROUP)
run.save_result('orca_af_finder_label',
                finder.label() if finder is not None else 'unavailable',
                group='results/' + GROUP)
run.save_result('orca_af_finder_settings',
                finder.describe() if finder is not None else 'unavailable',
                group='results/' + GROUP)
run.save_result('orca_af_finder_requested', requested, group='results/' + GROUP)
run.save_result('orca_af_finder_notes', ' | '.join(finder_notes),
                group='results/' + GROUP)
run.save_result('orca_af_score_label',
                finder.score_label if finder is not None else '',
                group='results/' + GROUP)
run.save_result('orca_af_threshold',
                np.nan if threshold is None else threshold,
                group='results/' + GROUP)
run.save_result('orca_af_aperture_radius',
                int(getattr(finder, 'aperture_radius', 0)) if finder is not None else 0,
                group='results/' + GROUP)
