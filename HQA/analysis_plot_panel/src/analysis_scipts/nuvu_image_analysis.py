"""
Nuvu Camera Image Analysis

Lyse analysis script for images acquired by cameras whose label starts with 'Nuvu'.
For now this script only locates and verifies the images so the analysis plot panel
can display them.  Extend this file to add ROI analysis, atom counting, etc.
"""

import lyse
import numpy as np
import h5py

#################################################################
# Load h5
#################################################################

try:
    h5_path = lyse.path
except AttributeError:
    df = lyse.data()
    h5_path = df.filepath.iloc[-1]

run = lyse.Run(h5_path)

#################################################################
# Discover and save Nuvu images
#################################################################

group = 'nuvu_image_analysis'

nuvu_found = []

try:
    all_labels = run.get_all_image_labels()
    print(f'nuvu_image_analysis: all_labels = {all_labels}')
except Exception as e:
    print(f'nuvu_image_analysis: could not get image labels: {e}')
    all_labels = {}

collected = {}  # {(orientation, label, image_name): array}

try:
    with h5py.File(h5_path, 'r') as f:
        images_group = f.get('images', {})
        print(f'nuvu_image_analysis: top-level images keys = {list(images_group.keys()) if images_group else "none"}')
        for orientation in list(all_labels.keys()):
            if orientation not in images_group:
                print(f'nuvu_image_analysis: orientation "{orientation}" not in images group, skipping')
                continue
            ori_group = images_group[orientation]
            print(f'nuvu_image_analysis: orientation "{orientation}" labels = {list(ori_group.keys())}')
            for label in all_labels.get(orientation, []):
                print(f'nuvu_image_analysis: checking label "{label}", startswith nuvu? {label.lower().startswith("nuvu")}')
                if not label.lower().startswith('nuvu'):
                    continue
                if label not in ori_group:
                    print(f'nuvu_image_analysis: label "{label}" not in ori_group, skipping')
                    continue
                label_group = ori_group[label]
                image_names = [k for k, v in label_group.items() if isinstance(v, h5py.Dataset)]
                print(f'nuvu_image_analysis: label "{label}" image_names = {image_names}')
                for image_name in image_names:
                    try:
                        raw = np.array(label_group[image_name], dtype='float')
                        print(f'nuvu_image_analysis: raw shape = {raw.shape}, ndim = {raw.ndim}')
                        # labscript stores images as (N, height, width); take first frame
                        img = raw[0] if raw.ndim == 3 else raw
                        print(f'nuvu_image_analysis: img shape after indexing = {img.shape}')
                        collected[(orientation, label, image_name)] = img
                    except Exception as e:
                        print(f'nuvu_image_analysis: could not read {orientation}/{label}/{image_name}: {e}')
except Exception as e:
    print(f'nuvu_image_analysis: error reading images: {e}')

print(f'nuvu_image_analysis: collected {len(collected)} image(s)')

# Save results after the HDF5 file is closed to avoid re-entrant lock conflict
# Do NOT pass group= so lyse saves to results/<script_name>/<key>
for (orientation, label, image_name), img in collected.items():
    try:
        result_key = f'{label}_{image_name}_image'
        print(f'nuvu_image_analysis: saving result_key="{result_key}"')
        run.save_result_array(result_key, img)
        nuvu_found.append(f'{orientation}/{label}/{image_name}')
    except Exception as e:
        print(f'nuvu_image_analysis: could not save {orientation}/{label}/{image_name}: {e}')

# Save a comma-separated index of result keys so the extractor can discover them
run.save_result('nuvu_image_keys', ','.join(
    f'{label}_{image_name}_image' for (_, label, image_name) in collected.keys()
))

if nuvu_found:
    print(f'nuvu_image_analysis: saved {len(nuvu_found)} image(s): {nuvu_found}')
else:
    print('nuvu_image_analysis: no Nuvu images found in this shot')
