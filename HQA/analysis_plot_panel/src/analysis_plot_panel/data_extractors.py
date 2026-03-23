# -*- coding: utf-8 -*-
"""
Created on Mon Mar 15 15:08:46 2021

@author: Nick Sauerwein
"""

import lyse
import numpy as np

import os
import os.path
import json

import h5py

try:
    from combined_file_utils import find_combined_file
except Exception:
    find_combined_file = None

def get_mtime(filename):
    # Ensure filename is a string
    if not isinstance(filename, str):
        if isinstance(filename, (list, tuple)):
            filename = str(filename[0]) if filename else None
        else:
            filename = str(filename)
    if filename is None:
        return None
    # Check if file exists before accessing its modification time
    if not os.path.exists(filename):
        return None
    return os.path.getmtime(filename)

class DataExtractorManager:
    
    def __init__(self):
        
        self.data_extractors = {}
        
    def update_local_data(self, h5_path):
        requires_h5_file = any(
            getattr(self.data_extractors[key], 'requires_h5_file', False)
            for key in self.data_extractors
        )

        if requires_h5_file:
            with h5py.File(h5_path, 'r') as h5_file:
                for key in self.data_extractors:
                    self.data_extractors[key].update_local_data(h5_path, h5_file = h5_file)
        else:
            for key in self.data_extractors:
                self.data_extractors[key].update_local_data(h5_path, h5_file = None)
            
    def clean_memory(self, h5_paths):
        for key in self.data_extractors:
            self.data_extractors[key].clean_memory(h5_paths)
            
    def __getitem__(self, key):
        return self.data_extractors[key]
    
    def __setitem__(self, key, de):
        self.data_extractors[key] = de
        

class DataExtractor:
    requires_h5_file = False
    MAX_CACHE_SIZE = 100  # Cache maximum 100 files to prevent unbounded memory growth

    def __init__(self, load_to_ram = True):
        
        self.load_to_ram = load_to_ram
        
        self.local_datas = {}
        self.local_mtimes = {}
        
        if self.load_to_ram:
            self.local_data_changed = True          
        
    def update_local_data(self, h5_path, h5_file = None):
        mtime = get_mtime(h5_path)
        
        # If the individual file no longer exists, try combined-file fallback
        if mtime is None:
            combined_mtime = None
            try:
                combined_path = find_combined_file(h5_path) if find_combined_file is not None else None
                if combined_path is not None:
                    combined_mtime = get_mtime(combined_path)
            except Exception:
                combined_mtime = None

            # If neither shot file nor combined file is available, drop cache entry
            if combined_mtime is None:
                if h5_path in self.local_datas:
                    del self.local_datas[h5_path]
                    self.local_data_changed = True
                if h5_path in self.local_mtimes:
                    del self.local_mtimes[h5_path]
                return

            # Use combined-file mtime as cache key for deleted shots
            mtime = f"combined:{combined_mtime}"
        
        # Check if cached data is still valid
        if h5_path in self.local_datas and self.local_mtimes.get(h5_path) == mtime:
            self.local_data_changed = False
        elif self.load_to_ram:
            # Enforce cache size limit to prevent unbounded memory growth
            if len(self.local_datas) >= self.MAX_CACHE_SIZE:
                # Remove oldest entry
                oldest_key = next(iter(self.local_datas))
                del self.local_datas[oldest_key]
                if oldest_key in self.local_mtimes:
                    del self.local_mtimes[oldest_key]
            
            self.local_datas[h5_path] = self.extract_data(h5_path, h5_file = h5_file)
            self.local_mtimes[h5_path] = mtime
            self.local_data_changed = True
            
    def update_local_datas(self):
        # Create a list copy of keys to avoid "dictionary changed size during iteration"
        # when update_local_data removes entries (e.g., for missing files)
        for key in list(self.local_datas.keys()):
            self.update_local_data(key)
    
    def get_data(self, h5_path, h5_file = None):
        
        if self.load_to_ram:
            
            self.update_local_data(h5_path, h5_file = h5_file)
            
            return self.local_datas[h5_path]        
        else:
            return self.extract_data(h5_path, h5_file = h5_file)
        
    def clean_memory(self, h5_paths):
        # Extract filepath list from DataFrame if needed
        if hasattr(h5_paths, 'filepath'):
            h5_paths_list = h5_paths.filepath.tolist()
        elif isinstance(h5_paths, list):
            h5_paths_list = h5_paths
        else:
            h5_paths_list = []

        h5_paths_set = set(h5_paths_list)
            
        for key in list(self.local_datas):
            if key not in h5_paths_set:
                del self.local_datas[key]
                if key in self.local_mtimes:
                    del self.local_mtimes[key]
                
                self.local_data_changed = True        
            
class MultiDataExtractor(DataExtractor):
    def __init__(self,**kwargs):
        
        super().__init__(load_to_ram=False, **kwargs)
        
        self.data_extractors = {}
        self.children_changed = False
        
    def extract_data(self, h5_path, h5_file = None):
        
        data = {}
        
        for key in self.data_extractors:
            try:
                data[key] = self.data_extractors[key].get_data(h5_path, h5_file = h5_file)
            except Exception as e:
                # Data not available for this file, skip it gracefully
                # Only log at debug level to avoid spamming the console
                import logging
                logging.debug(f"Could not extract data '{key}' from {h5_path}: {e}")
                data[key] = None
        
        self.children_changed = False
        
        return [data]
    
    def clean_children(self, keys):
        self.children_changed = False
        for key in list(self.data_extractors):
            if key not in keys:
                del self.data_extractors[key]
                self.children_changed = True
                
    def clean_memory(self, h5_paths):
       for key in self.data_extractors:
            self.data_extractors[key].clean_memory(h5_paths)
            
    def __getitem__(self, key):
        return self.data_extractors[key]
    
    def __setitem__(self, key, de):
        self.children_changed = True
        self.data_extractors[key] = de
        
    @property
    def local_data_changed(self):
        return any([self.data_extractors[key].local_data_changed for key in self.data_extractors]) or self.children_changed
        
class EmptyDataExtractor(DataExtractor):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        
    def extract_data(self, h5_path, h5_file = None):
        return []     
    
class ArrayDataExtractor(DataExtractor):

    def __init__(self,idx,  **kwargs):
        super().__init__(**kwargs)
        self.idx = idx
        
    def extract_data(self, h5_path, h5_file = None):
        res = None
        try:
            run = lyse.Run(h5_path, no_write=True)
            try:
                res = run.get_result_array(self.idx[0],self.idx[1])
            finally:
                # Ensure file is closed to prevent handle leaks
                if hasattr(run, 'close'):
                    run.close()
        except:
            res = None
        
        return res

class SingleDataExtractor(DataExtractor):

    def __init__(self,idx,  **kwargs):
        super().__init__(**kwargs)
        self.idx = idx
        
    def extract_data(self, h5_path, h5_file = None):
        res = None
        
        # First try the individual shot file
        file_exists = os.path.exists(h5_path)
        if file_exists:
            try:
                run = lyse.Run(h5_path, no_write=True)
                try:
                    if len(self.idx) == 1:
                        res = run.get_globals().get(self.idx[0])
                    else:
                        res = run.get_result(self.idx[0], self.idx[1])
                finally:
                    # Ensure file is closed to prevent handle leaks
                    if hasattr(run, 'close'):
                        run.close()
            except Exception as e:
                res = None
        
        # If individual file doesn't have the data, try combined file
        if res is None:
            try:
                from combined_file_utils import find_combined_file
                
                combined_path = find_combined_file(h5_path)
                if combined_path:
                    shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
                    
                    with h5py.File(combined_path, 'r') as f:
                        if 'All Runs' in f and shot_basename in f['All Runs']:
                            shot_group = f['All Runs'][shot_basename]
                            
                            # Find the run name from the dataset name
                            run_name = shot_basename
                            for name in shot_group.keys():
                                if name.endswith('.dat'):
                                    run_name = name[:-4]
                                    break
                            
                            # Look for the requested data as an attribute
                            ds = shot_group.get(f"{run_name}.dat")
                            if ds:
                                if len(self.idx) == 1:
                                    # For single index (globals), look in attributes
                                    attr_name = self.idx[0]
                                    if attr_name in ds.attrs:
                                        res = ds.attrs[attr_name]
                                        # Parse JSON if needed
                                        if isinstance(res, (str, bytes)):
                                            if isinstance(res, bytes):
                                                res = res.decode('utf-8')
                                            try:
                                                res = json.loads(res)
                                            except Exception:
                                                pass
                                else:
                                    # For two indices (group/result), look in attributes with group/name format
                                    attr_name = f"{self.idx[0]}/{self.idx[1]}"
                                    if attr_name in ds.attrs:
                                        res = ds.attrs[attr_name]
                                        # Parse JSON if needed
                                        if isinstance(res, (str, bytes)):
                                            if isinstance(res, bytes):
                                                res = res.decode('utf-8')
                                            try:
                                                res = json.loads(res)
                                            except Exception:
                                                pass
            except ImportError:
                # combined_file_utils not available
                res = None
            except Exception:
                res = None
        
        return res 

