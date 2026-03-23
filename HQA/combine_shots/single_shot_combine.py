import lyse
import numpy as np
import h5py as h5
import os
import json
import time
import datetime

def create_dataset_auto(group, name, data, compression, compression_opts, shuffle):
    arr = np.asarray(data)
    if arr.shape == ():  # skalar
        return group.create_dataset(name, data=data)
    return group.create_dataset(
        name,
        data=data,
        compression=compression,
        compression_opts=compression_opts,
        shuffle=shuffle,
        chunks=True,
    )

def main():
    
    compression = 'gzip'
    compression_opts = 4
    shuffle = True
    chunks = False
    
    # Check if running in real-time (spinning top) mode by checking if lyse.path is set
    try:
        h5_path = lyse.path
    except AttributeError:
        # If not in spinning top mode, get the filepath of the last shot of the lyse DataFrame
        df = lyse.data()
        h5_path = df.filepath.iloc[-1]

    # Read globals directly from the shot HDF5 (universal approach).
    globals_dict = {}
    try:
        with h5.File(h5_path, 'r') as src:
            if 'globals' in src:
                # Prefer top-level globals attributes (most common layout)
                globals_dict = dict(src['globals'].attrs)
    except Exception:
        # If opening fails, leave globals_dict empty and continue
        globals_dict = {}

    # Determine run name to use as combined filename
    run_name = None
    # common possible keys for run name
    for key in ("run_name", "run name", "run"):
        if key in globals_dict and globals_dict[key]:
            run_name = str(globals_dict[key])
            break
    if not run_name:
        # fallback to the shot file basename
        run_name = os.path.splitext(os.path.basename(h5_path))[0]

    # Save combined file in the parent directory of the shot folder (day folder's parent)
    day_dir = os.path.dirname(h5_path)
    parent_dir = os.path.abspath(os.path.join(day_dir, os.pardir))
    os.makedirs(parent_dir, exist_ok=True)
    # If run_name is 'auto', use the shot's 'sequence_index' attribute to
    # name the combined file (one combined file per sequence). Fall back to
    # using run_name if sequence_index not found.
    combined_filename = f"{run_name}.h5"
    if str(run_name).lower() == 'auto':
        seq_idx = None
        try:
            with h5.File(h5_path, 'r') as _src:
                # check root attrs first
                for key in ('sequence_index', 'sequence index', 'sequence'):
                    if key in _src.attrs and _src.attrs[key] is not None:
                        seq_idx = str(_src.attrs[key])
                        break
                # check globals group
                if seq_idx is None and 'globals' in _src:
                    try:
                        for key in ('sequence_index', 'sequence index', 'sequence'):
                            if key in _src['globals'].attrs and _src['globals'].attrs[key] is not None:
                                seq_idx = str(_src['globals'].attrs[key])
                                break
                    except Exception:
                        pass
                # check other top-level groups for a sequence attribute
                if seq_idx is None:
                    for gname in _src.keys():
                        try:
                            grp = _src[gname]
                            for key in ('sequence_index', 'sequence index', 'sequence'):
                                if key in grp.attrs and grp.attrs[key] is not None:
                                    seq_idx = str(grp.attrs[key])
                                    break
                            if seq_idx is not None:
                                break
                        except Exception:
                            continue
        except Exception:
            seq_idx = None
        if seq_idx:
            combined_filename = f"{seq_idx}.h5"
    combined_path = os.path.join(parent_dir, combined_filename)

    # Open source shot and combined file together and write combined data.
    shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
    # Detect whether combined file already exists to create a new summary if needed
    combined_existed = os.path.exists(combined_path)
    with h5.File(h5_path, 'r') as src, h5.File(combined_path, 'a') as dst:
        if not combined_existed:
            # mark this as a new summary file for the sequence
            try:
                if str(run_name).lower() == 'auto' and 'sequence_index' not in dst.attrs:
                    # store sequence index as root attr for combined file
                    try:
                        # if we successfully determined seq_idx earlier use it
                        dst.attrs['sequence_index'] = os.path.splitext(combined_filename)[0]
                    except Exception:
                        pass
            except Exception:
                pass
        # If globals were empty earlier, try again from the open src handle
        if not globals_dict and 'globals' in src:
            globals_dict = dict(src['globals'].attrs)

        # Re-evaluate run_name using the globals read from the file
        if not run_name:
            for key in ("run_name", "run name", "run"):
                if key in globals_dict and globals_dict[key]:
                    run_name = str(globals_dict[key])
                    break
        if not run_name:
            run_name = shot_basename

        all_runs = dst.require_group('All Runs')

        # Use shot basename as shot_id; create (or get) shot group
        shot_id = shot_basename
        shot_group = all_runs.require_group(shot_id)
        # Keep a reference to the source shot file
        shot_group.attrs['source_shot'] = h5_path

        # Create (or reuse) a small placeholder dataset '<run_name>.dat' under this shot_group
        dataset_name = f"{run_name}.dat"
        if dataset_name in shot_group:
            ds = shot_group[dataset_name]
        else:
            ds = shot_group.create_dataset(dataset_name, data=np.bytes_(''))

        # Copy the shot file's root 'run time' attribute (common variants) into the combined dataset
        # Try several locations for 'run time': root attrs, '/globals', or any top-level group
        rt_val = None
        for rt_key in ('run time', 'run_time', 'runtime'):
            try:
                if rt_key in src.attrs:
                    rt_val = src.attrs[rt_key]
                    break
            except Exception:
                pass
        if rt_val is None and 'globals' in src:
            try:
                for rt_key in ('run time', 'run_time', 'runtime'):
                    if rt_key in src['globals'].attrs:
                        rt_val = src['globals'].attrs[rt_key]
                        break
            except Exception:
                pass
        if rt_val is None:
            # Check top-level groups for a 'main' group that may hold run time
            try:
                for k in src.keys():
                    if k == 'globals':
                        continue
                    try:
                        g = src[k]
                        for rt_key in ('run time', 'run_time', 'runtime'):
                            if rt_key in g.attrs:
                                rt_val = g.attrs[rt_key]
                                break
                        if rt_val is not None:
                            break
                    except Exception:
                        continue
            except Exception:
                pass
        if rt_val is not None:
            try:
                ds.attrs['run time'] = rt_val
            except (TypeError, ValueError):
                ds.attrs['run time'] = json.dumps(rt_val, default=str)

        # Write globals as attributes on the dataset. Prefer native types, else JSON.
        for k, v in globals_dict.items():
            try:
                ds.attrs[k] = v
            except (TypeError, ValueError):
                ds.attrs[k] = json.dumps(v, default=str)

        # Copy images if present under '/images/<orientation>/<label>/<image>'
        if 'images' in src:
            images_root = shot_group.require_group('Images')
            for orientation in src['images'].keys():
                for label in src['images'][orientation].keys():
                    for image_name in src['images'][orientation][label].keys():
                        src_path = f"/images/{orientation}/{label}/{image_name}"
                        src_obj = src[src_path]

                        # Determine camera name from attributes or fall back to label
                        cam = None
                        for key in ('camera', 'Camera', 'device', 'cam'):
                            if key in src_obj.attrs:
                                cam = str(src_obj.attrs[key])
                                break
                        if not cam:
                            cam = label or 'camera'

                        cam_group = images_root.require_group(cam)

                        # Ensure unique dataset name in cam_group
                        ds_name = image_name
                        counter = 1
                        while ds_name in cam_group:
                            ds_name = f"{image_name}_{counter}"
                            counter += 1

                        # Use h5py copy to copy dataset efficiently between files
                        try:
                            dst.copy(src_obj, cam_group, name=ds_name)
                            new_ds = cam_group[ds_name]
                        except Exception:
                            # Fallback: create placeholder
                            new_ds = cam_group.create_dataset(ds_name, data=np.bytes_(''))

                        # Attach orientation and label attributes
                        try:
                            new_ds.attrs['orientation'] = orientation
                        except Exception:
                            new_ds.attrs['orientation'] = str(orientation)
                        try:
                            new_ds.attrs['label'] = label
                        except Exception:
                            new_ds.attrs['label'] = str(label)

                        # Copy other attributes from source dataset
                        for akey in src_obj.attrs:
                            if akey in ('camera', 'Camera', 'device', 'cam'):
                                continue
                            aval = src_obj.attrs[akey]
                            try:
                                new_ds.attrs[akey] = aval
                            except Exception:
                                new_ds.attrs[akey] = json.dumps(aval, default=str)

        # Copy all results from '/results' group
        # This includes both scalar results (as attributes) and array results (as datasets)
        if 'results' in src:
            results_group = shot_group.require_group('Results')
            
            for grp_name in src['results'].keys():
                grp = src['results'][grp_name]
                
                # Copy attributes saved in the results group (these are typical save_result entries)
                for akey, aval in grp.attrs.items():
                    attr_name = f"{grp_name}/{akey}"
                    try:
                        ds.attrs[attr_name] = aval
                    except (TypeError, ValueError):
                        try:
                            ds.attrs[attr_name] = json.dumps(aval, default=str)
                        except Exception:
                            ds.attrs[attr_name] = str(aval)

                # For any datasets under the results group (arrays), capture scalar or
                # single-element datasets as values; otherwise copy array data to combined file.
                grp_result_group = results_group.require_group(grp_name)
                for item_name in grp.keys():
                    item = grp[item_name]
                    if isinstance(item, h5.Dataset):
                        try:
                            data = item[()]
                            # If scalar or single-element, store the value directly
                            if np.isscalar(data) or (hasattr(data, 'shape') and np.prod(data.shape) == 1):
                                try:
                                    val = data.item() if hasattr(data, 'item') else data.tolist()[0] if hasattr(data, 'tolist') else data
                                    ds.attrs[f"{grp_name}/{item_name}"] = val
                                except Exception:
                                    ds.attrs[f"{grp_name}/{item_name}"] = json.dumps(data.tolist() if hasattr(data, 'tolist') else str(data), default=str)
                            else:
                                # For array data, store it as a dataset in a results group
                                # Use unique name if it already exists
                                ds_name = item_name
                                counter = 1
                                while ds_name in grp_result_group:
                                    ds_name = f"{item_name}_{counter}"
                                    counter += 1
                                
                                try:
                                    # Copy the array dataset
                                    grp_result_group.create_dataset(ds_name, data=data, compression=compression, compression_opts=compression_opts, shuffle=shuffle, chunks=chunks)
                                    # Also copy attributes from the source dataset
                                    for src_akey, src_aval in item.attrs.items():
                                        try:
                                            grp_result_group[ds_name].attrs[src_akey] = src_aval
                                        except Exception:
                                            grp_result_group[ds_name].attrs[src_akey] = str(src_aval)
                                except Exception:
                                    # If that fails, store metadata
                                    meta = {'dtype': str(item.dtype), 'shape': list(item.shape)}
                                    ds.attrs[f"{grp_name}/{item_name}"] = json.dumps(meta)
                        except Exception:
                            ds.attrs[f"{grp_name}/{item_name}"] = '<<unreadable>>'
        
        # Copy any additional top-level datasets that contain analysis data
        # (e.g., 'shot number', or other data at root level)
        for key in src.keys():
            if key not in ('globals', 'images', 'results') and isinstance(src[key], h5.Dataset):
                try:
                    data = src[key][()]
                    # Store as attribute if scalar, otherwise as dataset
                    if np.isscalar(data) or (hasattr(data, 'shape') and np.prod(data.shape) == 1):
                        try:
                            val = data.item() if hasattr(data, 'item') else data.tolist()[0] if hasattr(data, 'tolist') else data
                            ds.attrs[key] = val
                        except Exception:
                            ds.attrs[key] = json.dumps(data.tolist() if hasattr(data, 'tolist') else str(data), default=str)
                    else:
                        # Store array as dataset
                        misc_group = shot_group.require_group('MiscData')
                        ds_name = key
                        counter = 1
                        while ds_name in misc_group:
                            ds_name = f"{key}_{counter}"
                            counter += 1
                        try:
                            misc_group.create_dataset(ds_name, data=data, compression=compression, compression_opts=compression_opts, shuffle=shuffle, chunks=chunks)
                        except Exception:
                            ds.attrs[key] = str(data)
                except Exception:
                    pass

    # If requested by globals, delete duplicate shots (keep the first/earliest)
    def _truthy(val):
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        s = str(val).lower()
        return s in ('1', 'true', 'yes', 'y')

    delete_flag = globals_dict.get('delete_shots')
    # also check ds attrs in case lyse wrote the flag there
    try:
        with h5.File(combined_path, 'r') as cfile:
            if 'All Runs' in cfile and shot_basename in cfile['All Runs']:
                shot_group = cfile['All Runs'][shot_basename]
                dataset_name = f"{run_name}.dat"
                if dataset_name in shot_group:
                    ds = shot_group[dataset_name]
                    if delete_flag is None:
                        delete_flag = ds.attrs.get('delete_shots', delete_flag)
    except Exception:
        pass

    if _truthy(delete_flag):
        try:
            def _coerce_time(val, fpath=None):
                # Try numeric
                try:
                    return float(val)
                except Exception:
                    pass
                # Try ISO datetime
                try:
                    return datetime.datetime.fromisoformat(str(val)).timestamp()
                except Exception:
                    pass
                # Try common datetime format
                try:
                    t = time.strptime(str(val), '%Y-%m-%d %H:%M:%S')
                    return time.mktime(t)
                except Exception:
                    pass
                # Fallback to file mtime
                try:
                    if fpath and os.path.exists(fpath):
                        return os.path.getmtime(fpath)
                except Exception:
                    pass
                return float('inf')

            def _read_run_time(fpath):
                try:
                    with h5.File(fpath, 'r') as fh:
                        # check root attrs first
                        for key in ('run time', 'run_time', 'runtime'):
                            if key in fh.attrs:
                                return _coerce_time(fh.attrs[key], fpath)
                        # check globals group
                        if 'globals' in fh:
                            try:
                                for key in ('run time', 'run_time', 'runtime'):
                                    if key in fh['globals'].attrs:
                                        return _coerce_time(fh['globals'].attrs[key], fpath)
                            except Exception:
                                pass
                        # check other top-level groups
                        try:
                            for k in fh.keys():
                                if k == 'globals':
                                    continue
                                try:
                                    grp = fh[k]
                                    for key in ('run time', 'run_time', 'runtime'):
                                        if key in grp.attrs:
                                            return _coerce_time(grp.attrs[key], fpath)
                                except Exception:
                                    continue
                        except Exception:
                            pass
                except Exception:
                    pass
                return os.path.getmtime(fpath) if os.path.exists(fpath) else float('inf')

            # Optimize deletion: read current shot run_time once and only inspect
            # files with modification time <= current file mtime. Stop early when
            # we find any earlier run_time for the same run_name.
            try:
                current_rt = _read_run_time(h5_path)
            except Exception:
                current_rt = os.path.getmtime(h5_path)

            current_mtime = os.path.getmtime(h5_path) if os.path.exists(h5_path) else float('inf')
            delete_current = False
            for fname in os.listdir(day_dir):
                if not fname.lower().endswith('.h5'):
                    continue
                fpath = os.path.join(day_dir, fname)
                # skip combined and the current file
                if os.path.abspath(fpath) == os.path.abspath(combined_path) or os.path.abspath(fpath) == os.path.abspath(h5_path):
                    continue
                try:
                    f_mtime = os.path.getmtime(fpath)
                except Exception:
                    continue
                # only consider files that are not newer than current shot
                if f_mtime > current_mtime:
                    continue
                try:
                    with h5.File(fpath, 'r') as fh:
                        g = {}
                        if 'globals' in fh:
                            try:
                                g = dict(fh['globals'].attrs)
                            except Exception:
                                g = {}
                        match = False
                        for key in ('run_name', 'run name', 'run'):
                            if key in g and g[key] and str(g[key]) == str(run_name):
                                match = True
                                break
                        if not match:
                            continue
                        other_rt = _read_run_time(fpath)
                        if other_rt < current_rt:
                            delete_current = True
                            break
                except Exception:
                    continue

            if delete_current:
                try:
                    os.remove(h5_path)
                except Exception:
                    try:
                        trash_dir = os.path.join(day_dir, '_deleted_shots')
                        os.makedirs(trash_dir, exist_ok=True)
                        base = os.path.basename(h5_path)
                        dest = os.path.join(trash_dir, base)
                        os.replace(h5_path, dest)
                    except Exception:
                        pass
        except Exception:
            pass

    # Optionally, return the path of the combined file for downstream use
    return combined_path
if __name__ == '__main__':
    main()