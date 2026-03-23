# -*- coding: utf-8 -*-
"""
Created on Mon Mar 22 14:07:54 2021

@author: nicks
"""

import lyse
import numpy as np
import h5py
import os
import logging

from uncertainties import ufloat

from data_extractors import DataExtractor
from combined_file_utils import (
    find_combined_file, 
    is_combined_file,
    get_combined_file_result,
    get_combined_file_result_array,
    get_combined_file_image
)

logger = logging.getLogger(__name__)

class FluoDataExtractor(DataExtractor):
    def __init__(self, imaging, cam, **kwargs):
        
        super().__init__(**kwargs)
        
        self.imaging = imaging
        self.cam = cam
    
    def _extract_from_combined(self, combined_path, shot_basename, run_name):
        """Try to extract data from combined file"""
        try:
            with h5py.File(combined_path, 'r') as h5_file:
                imaging = self.imaging
                cam = self.cam
                
                # Try to get results from combined file attributes
                N_val = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Natoms')
                N_err = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Natoms_err')
                
                if N_val is None or N_err is None:
                    return None
                
                N = ufloat(N_val, N_err)
                Nx = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Nx'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Nx_err')
                )
                Ny = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Ny'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Ny_err')
                )
                
                sx = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sx'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sx_err')
                )
                sy = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sy'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sy_err')
                )
                cx = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cx'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cx_err')
                )
                cy = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cy'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cy_err')
                )
                
                axesx = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_axesx')
                axesy = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_axesy')
                
                if axesx is None or axesy is None:
                    return None
                
                tabledata = np.array([
                    (axesx,'{:.1ueS}'.format(Nx),'{:.1uS}'.format(sx),'{:.1uS}'.format(cx)), 
                    (axesy, '{:.1ueS}'.format(Ny),'{:.1uS}'.format(sy),'{:.1uS}'.format(cy))
                ], dtype=[('axis',object),('N ('+'{:.1ueS}'.format(N)+')', object), ('c (mm)', object), ('s (mm)', object)])
                
                # Try to get array images from Results or Images group
                # First try Results group (new structure from updated single_shot_combine.py)
                data_img = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_diff_image')
                xsum = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_xsum')
                ysum = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_ysum')
                datax_fit = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_xfit')
                datay_fit = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_yfit')
                xgrid = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_xgrid')
                ygrid = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_ygrid')
                
                # If not in Results, try Images group (for manually stored images)
                if data_img is None:
                    data_img = get_combined_file_image(h5_file, shot_basename, cam, 'diff_image')
                if xsum is None:
                    xsum = get_combined_file_image(h5_file, shot_basename, cam, 'xsum')
                if ysum is None:
                    ysum = get_combined_file_image(h5_file, shot_basename, cam, 'ysum')
                if datax_fit is None:
                    datax_fit = get_combined_file_image(h5_file, shot_basename, cam, 'xfit')
                if datay_fit is None:
                    datay_fit = get_combined_file_image(h5_file, shot_basename, cam, 'yfit')
                if xgrid is None:
                    xgrid = get_combined_file_image(h5_file, shot_basename, cam, 'xgrid')
                if ygrid is None:
                    ygrid = get_combined_file_image(h5_file, shot_basename, cam, 'ygrid')
                
                # If images not available in combined file, fall back to individual file
                if data_img is None:
                    return None
                
                warning = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_warning')
                if warning is None:
                    warning = ''
                
                return data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning
        except Exception as e:
            logger.debug(f"Error extracting from combined file: {e}")
            return None
                    
    def extract_data(self, h5_path , h5_file = None):
        
        shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
        file_exists = os.path.exists(h5_path)
        
        # Try to load from combined file first
        combined_path = find_combined_file(h5_path)
        if combined_path:
            try:
                with h5py.File(combined_path, 'r') as f:
                    if is_combined_file(f) and shot_basename in f['All Runs']:
                        shot_group = f['All Runs'][shot_basename]
                        # Find run_name from dataset
                        run_name = shot_basename
                        for name in shot_group.keys():
                            if name.endswith('.dat'):
                                run_name = name[:-4]
                                break
                        
                        result = self._extract_from_combined(combined_path, shot_basename, run_name)
                        if result is not None:
                            if not file_exists:
                                logger.info(f"Loaded {self.imaging}/{self.cam} data from combined file for deleted shot: {shot_basename}")
                            return result
            except Exception as e:
                logger.debug(f"Error loading from combined file {combined_path}: {e}")
                pass
        
        # If file is deleted and no combined file data, return error message
        if not file_exists:
            logger.warning(f"Shot file deleted and no combined file data available: {h5_path}")
            data_img = np.zeros((2, 2))
            tabledata = np.array([['FILE_DELETED'], ['No data: file deleted and not in combined file']], 
                               dtype=[('axis', object), ('N', object), ('c (mm)', object), ('s (mm)', object)])
            xsum, ysum = np.arange(2), np.arange(2)
            datax_fit, datay_fit = np.arange(2), np.arange(2)
            xgrid, ygrid = np.arange(2), np.arange(2)
            warning = 'Shot file deleted - not in combined file'
            return data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning
        
        # Fall back to individual file (for shots that still exist)
        run = lyse.Run(h5_path, no_write=True)
        
        imaging = self.imaging
        cam = self.cam
        
        try:
            from uncertainties import ufloat
            
            N = ufloat(*run.get_results(imaging, cam+'_Natoms', cam+'_Natoms_err'))
            Nx = ufloat(*run.get_results(imaging, cam+'_Nx', cam+'_Nx_err'))
            Ny = ufloat(*run.get_results(imaging, cam+'_Ny', cam+'_Ny_err'))
            
            sx = ufloat(*run.get_results(imaging, cam+'_sx', cam+'_sx_err'))
            sy = ufloat(*run.get_results(imaging, cam+'_sy', cam+'_sy_err'))
            cx = ufloat(*run.get_results(imaging, cam+'_cx', cam+'_cx_err'))
            cy = ufloat(*run.get_results(imaging, cam+'_cy', cam+'_cy_err'))
            
            axesx, axesy = run.get_results(imaging, cam+'_axesx', cam+'_axesy')
            
            tabledata = np.array([
                (axesx,'{:.1ueS}'.format(Nx),'{:.1uS}'.format(sx),'{:.1uS}'.format(cx)), 
                (axesy, '{:.1ueS}'.format(Ny),'{:.1uS}'.format(sy),'{:.1uS}'.format(cy))
                ], dtype=[('axis',object),('N ('+'{:.1ueS}'.format(N)+')', object), ('c (mm)', object), ('s (mm)', object)])
    
            data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid = run.get_result_arrays(imaging, cam+'_diff_image',
                                                 cam+'_xsum',
                                                 cam+'_ysum',
                                                 cam+'_xfit', 
                                                 cam+'_yfit',
                                                 cam+'_xgrid',
                                                 cam+'_ygrid')
            
            warning = run.get_result(imaging, cam+'_warning')
        except:
            data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning = np.zeros((2,2)), np.arange(2), np.arange(2), np.arange(2), np.arange(2), np.arange(2), np.arange(2),np.array([['no_data_x'],['no_data_y']]), 'no data in shot'
            

        return data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning
    
class AbsorptionDataExtractor(DataExtractor):
    def __init__(self, imaging, cam, **kwargs):
        
        super().__init__(**kwargs)
        
        self.imaging = imaging
        self.cam = cam
    
    def _extract_from_combined(self, combined_path, shot_basename, run_name):
        """Try to extract data from combined file"""
        try:
            with h5py.File(combined_path, 'r') as h5_file:
                imaging = self.imaging
                cam = self.cam
                
                # Try to get results from combined file attributes
                N_val = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Natoms')
                if N_val is None:
                    return None
                
                N = N_val
                Nx = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Nx'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Nx_err')
                )
                Ny = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Ny'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_Ny_err')
                )
                
                sx = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sx'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sx_err')
                )
                sy = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sy'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_sy_err')
                )
                cx = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cx'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cx_err')
                )
                cy = ufloat(
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cy'),
                    get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_cy_err')
                )
                
                axesx = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_axesx')
                axesy = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_axesy')
                
                if axesx is None or axesy is None:
                    return None
                
                tabledata = np.array([
                    (axesx, '{:.1ueS}'.format(Nx),'{:.1uS}'.format(sx),'{:.1uS}'.format(cx)), 
                    (axesy, '{:.1ueS}'.format(Ny),'{:.1uS}'.format(sy),'{:.1uS}'.format(cy))
                ], dtype=[('axis',object),('N ('+'{:.0f}'.format(N)+')', object), ('c (mm)', object), ('s (mm)', object)])
                
                # Try to get array images from Results or Images group
                # First try Results group (new structure from updated single_shot_combine.py)
                data_img = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_OD_image')
                xsum = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_xsum')
                ysum = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_ysum')
                datax_fit = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_xfit')
                datay_fit = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_yfit')
                xgrid = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_xgrid')
                ygrid = get_combined_file_result_array(h5_file, shot_basename, run_name, imaging, cam+'_ygrid')
                
                # If not in Results, try Images group (for manually stored images)
                if data_img is None:
                    data_img = get_combined_file_image(h5_file, shot_basename, cam, 'OD_image')
                if xsum is None:
                    xsum = get_combined_file_image(h5_file, shot_basename, cam, 'xsum')
                if ysum is None:
                    ysum = get_combined_file_image(h5_file, shot_basename, cam, 'ysum')
                if datax_fit is None:
                    datax_fit = get_combined_file_image(h5_file, shot_basename, cam, 'xfit')
                if datay_fit is None:
                    datay_fit = get_combined_file_image(h5_file, shot_basename, cam, 'yfit')
                if xgrid is None:
                    xgrid = get_combined_file_image(h5_file, shot_basename, cam, 'xgrid')
                if ygrid is None:
                    ygrid = get_combined_file_image(h5_file, shot_basename, cam, 'ygrid')
                
                # If images not available in combined file, fall back to individual file
                if data_img is None:
                    return None
                
                warning = get_combined_file_result(h5_file, shot_basename, run_name, imaging, cam+'_warning')
                if warning is None:
                    warning = ''
                
                return data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning
        except Exception as e:
            logger.debug(f"Error extracting from combined file: {e}")
            return None
        
    def extract_data(self, h5_path, h5_file = None):
        
        shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
        
        # Try to load from combined file first
        combined_path = find_combined_file(h5_path)
        if combined_path:
            try:
                with h5py.File(combined_path, 'r') as f:
                    if is_combined_file(f) and shot_basename in f['All Runs']:
                        shot_group = f['All Runs'][shot_basename]
                        # Find run_name from dataset
                        run_name = shot_basename
                        for name in shot_group.keys():
                            if name.endswith('.dat'):
                                run_name = name[:-4]
                                break
                        
                        result = self._extract_from_combined(combined_path, shot_basename, run_name)
                        if result is not None:
                            return result
            except Exception:
                pass
        
        # Fall back to individual file
        run = lyse.Run(h5_path, no_write=True)
        
        imaging = self.imaging
        cam = self.cam
        try:
            N = run.get_result(imaging, cam+'_Natoms')
            Nx = ufloat(*run.get_results(imaging, cam+'_Nx', cam+'_Nx_err'))
            Ny = ufloat(*run.get_results(imaging, cam+'_Ny', cam+'_Ny_err'))
            
            sx = ufloat(*run.get_results(imaging, cam+'_sx', cam+'_sx_err'))
            sy = ufloat(*run.get_results(imaging, cam+'_sy', cam+'_sy_err'))
            cx = ufloat(*run.get_results(imaging, cam+'_cx', cam+'_cx_err'))
            cy = ufloat(*run.get_results(imaging, cam+'_cy', cam+'_cy_err'))
            
            axesx, axesy = run.get_results(imaging, cam+'_axesx', cam+'_axesy')
            
            tabledata = np.array([
                (axesx, '{:.1ueS}'.format(Nx),'{:.1uS}'.format(sx),'{:.1uS}'.format(cx)), 
                (axesy, '{:.1ueS}'.format(Ny),'{:.1uS}'.format(sy),'{:.1uS}'.format(cy))
                ], dtype=[('axis',object),('N ('+'{:.0f}'.format(N)+')', object), ('c (mm)', object), ('s (mm)', object)])
    
            data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid = run.get_result_arrays(imaging, cam+'_OD_image',
                                                 cam+'_xsum',
                                                 cam+'_ysum',
                                                 cam+'_xfit', 
                                                 cam+'_yfit',
                                                 cam+'_xgrid',
                                                 cam+'_ygrid')
            
            warning = run.get_result(imaging, cam+'_warning')
        except:
            data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning = np.zeros((2,2)), np.arange(2), np.arange(2), np.arange(2), np.arange(2), np.arange(2), np.arange(2),np.array([['no_data_x'],['no_data_y']]), 'no data in shot'
            
        return data_img, xsum, ysum, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning

class SpectrumDataExtractor(DataExtractor):
    def __init__(self, name, frametype, **kwargs):
        
        super().__init__(**kwargs)
        
        self.name = name
        self.frametype = frametype
        
        
    def extract_data(self, h5_path, h5_file = None):
        if not os.path.exists(h5_path):
            freqs, n_photons, omega0, kappa, A, offset, f0, f1, duration = np.array([0.,1.]), np.array([0.,1.]), 0., 0., 0., 0., 0., 1, 1
            tabledata = np.arange(2, dtype='float64')
            warning = 'shot file missing'
            return freqs, n_photons, omega0, kappa, A, offset, f0, f1, duration, tabledata, warning

        run = lyse.Run(h5_path, no_write=True)
        
        imaging = 'cavity_spectrum'
        
        name = self.name
        frametype = self.frametype
        
        spectrum_name = name+' '+frametype
        
        try:
            
            f0 = run.get_result(imaging, spectrum_name+' f0')
            f1 = run.get_result(imaging, spectrum_name+' f1')
            duration = run.get_result(imaging, spectrum_name+' duration')
            
            kappa = run.get_result(imaging, spectrum_name+' kappa')
            omega0 = run.get_result(imaging, spectrum_name+' omega0')
            A = run.get_result(imaging, spectrum_name+' A')
            offset = run.get_result(imaging, spectrum_name+' offset')
            n_photons_total = run.get_result(imaging, spectrum_name+' n_photons_total')
            
            
            n_photons = run.get_result_array(imaging, spectrum_name+' n_photons')
            freqs = run.get_result_array(imaging, spectrum_name+' freqs')
            
            
            tabledata = np.array([
                ('{:.0f}'.format(n_photons_total),f'{omega0/2/np.pi:.3f}',f'{(kappa/2/np.pi):.3f}')
                ], dtype = [('N photons', object), ('omega0/2/pi (MHz)', object), ('kappa/2/pi (MHz)', object)])
            
            warning = run.get_result(imaging, spectrum_name+' warning')
        except Exception:
            freqs, n_photons, omega0, kappa, A, offset, f0, f1, duration,tabledata, warning = np.array([0.,1.]), np.array([0.,1.]), 0., 0., 0., 0.,0., 1, 1,np.arange(2,dtype = 'float64'), 'no data in shot'
            
        return freqs, n_photons, omega0, kappa, A, offset, f0, f1, duration, tabledata , warning
        
class ScopeDataExtractor(DataExtractor):
    def __init__(self, name, frametype, **kwargs):
        
        super().__init__(**kwargs)
        
        self.name = name
        self.frametype = frametype
        
        
    def extract_data(self, h5_path, h5_file = None):
        if not os.path.exists(h5_path):
            volts, times, warning = np.array([0.,1.]), np.array([0.,1.]), 'shot file missing'
            tabledata, sig_type = np.array([], dtype=[]), 'trace'
            return volts, times, tabledata, sig_type, warning

        run = lyse.Run(h5_path, no_write=True)
        
        imaging = 'scope_Pico'
        
        name = self.name
        frametype = self.frametype
        
        spectrum_name = name
        
        try:
            
            sig_type = run.get_result(imaging, spectrum_name+' sig_type')
            
            tabledata = np.array([], dtype = [])
            
            volts = run.get_result_array(imaging, spectrum_name+' volts')
            times = run.get_result_array(imaging, spectrum_name+' times')
            
            warning = run.get_result(imaging, spectrum_name+' warning')
        except Exception:
            volts, times, warning = np.array([0.,1.]),np.array([0.,1.]),'no data in shot'
            tabledata, sig_type = np.array([], dtype = []), 'trace'
            
        return volts, times , tabledata, sig_type, warning

class FluoBackgroundDataExtractor(DataExtractor):
    def __init__(self, cam, **kwargs):
        
        super().__init__(**kwargs)
        
        self.cam = cam
        
    def extract_data(self, h5_path, h5_file = None):
        
        import os
        shot_basename = os.path.splitext(os.path.basename(h5_path))[0]
        file_exists = os.path.exists(h5_path)
        
        cam = self.cam
        prefix = 'fluo_background_'
        group = 'fluo_background_analysis'  # Analysis script name
        
        # Try to load from combined file first if individual file doesn't exist
        combined_path = None
        if not file_exists:
            from combined_file_utils import find_combined_file
            combined_path = find_combined_file(h5_path)
        
        # Try from individual file first
        run = None
        if file_exists:
            run = lyse.Run(h5_path, no_write=True)
        
        try:
            from uncertainties import ufloat
            
            if run is not None:
                # Try to extract from individual shot file
                signal_sum = run.get_result(group, prefix + cam + '_signal_sum')
                signal_uncertainty = run.get_result(group, prefix + cam + '_signal_uncertainty')
                bg_weight_factor = run.get_result(group, prefix + cam + '_bg_weight_factor')
                
                signal_sum_ufloat = ufloat(signal_sum, signal_uncertainty)
                
                # Get image data
                corrected_image = run.get_result_array(group, prefix + cam + '_corrected_image')
                background_avg = run.get_result_array(group, prefix + cam + '_background_avg')
                
                # Get ROI information
                signal_roi_x = run.get_result(group, prefix + cam + '_signal_roi_x')
                signal_roi_y = run.get_result(group, prefix + cam + '_signal_roi_y')
                signal_roi_width = run.get_result(group, prefix + cam + '_signal_roi_width')
                signal_roi_height = run.get_result(group, prefix + cam + '_signal_roi_height')
                bg_roi_x = run.get_result(group, prefix + cam + '_bg_roi_x')
                bg_roi_y = run.get_result(group, prefix + cam + '_bg_roi_y')
                bg_roi_width = run.get_result(group, prefix + cam + '_bg_roi_width')
                bg_roi_height = run.get_result(group, prefix + cam + '_bg_roi_height')
                
                # Package ROI data
                roi_data = {
                    'signal': (signal_roi_x, signal_roi_y, signal_roi_width, signal_roi_height),
                    'background': (bg_roi_x, bg_roi_y, bg_roi_width, bg_roi_height)
                }
                
                # Get orientation and label info
                orientation = run.get_result(group, prefix + cam + '_orientation')
                label = run.get_result(group, prefix + cam + '_label')
                
                # Try to get atom number if available
                try:
                    N_atoms = run.get_result(group, prefix + cam + '_Natoms')
                    N_atoms_err = run.get_result(group, prefix + cam + '_Natoms_err')
                    N_atoms_ufloat = ufloat(N_atoms, N_atoms_err)
                    has_atom_number = True
                except Exception:
                    has_atom_number = False
                
                # Build table data
                table_rows = [
                    ('Signal Sum', '{:.3ue}'.format(signal_sum_ufloat)),
                ]
                
                if has_atom_number:
                    table_rows.append(('Atom Number', '{:.3ue}'.format(N_atoms_ufloat)))
                
                table_rows.extend([
                    ('Weight Factor', '{:.4f}'.format(bg_weight_factor)),
                    ('Signal ROI', f'({signal_roi_x:.0f}, {signal_roi_y:.0f})'),
                    ('BG ROI', f'({bg_roi_x:.0f}, {bg_roi_y:.0f})'),
                    ('Orientation', orientation),
                    ('Label', label),
                ])
                
                tabledata = np.array(table_rows, dtype=[('Parameter', object), ('Value', object)])
                
                warning = ''
            else:
                raise ValueError("Individual file not available")
                
        except Exception as e:
            # Return dummy data if extraction fails
            # This handles cases where fluo_background_analysis was not run
            corrected_image = np.zeros((10, 10))
            background_avg = np.zeros((10, 10))
            tabledata = np.array([('Status', 'Analysis not available')], dtype=[('Parameter', object), ('Value', object)])
            warning = 'Fluorescence background analysis not available for this shot'
            roi_data = None
            
        return corrected_image, background_avg, tabledata, warning, roi_data


class ADwinTracesDataExtractor(DataExtractor):
    """Extract ADwin analog input traces for display in analysis plot panel"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
    def extract_data(self, h5_path, h5_file=None):
        """
        Extract analog input data from the shot file.
        
        Returns
        -------
        tuple
            (traces_dict, tabledata, warning)
            traces_dict: dict mapping channel names to (times, values) tuples
            tabledata: numpy array with data for the table display
            warning: warning string if any issues occurred
        """
        import h5py
        from labscript_utils import properties
        from user_devices.ADwinProII.ADwin_utils import DAC
        
        traces_dict = {}
        source_path = h5_path

        # Graceful handling for deleted shot files: avoid traceback spam.
        if not os.path.exists(source_path):
            combined_path = find_combined_file(h5_path)
            if combined_path and os.path.exists(combined_path):
                source_path = combined_path
            else:
                tabledata = np.array([('Status', 'Source file missing')], dtype=[('Channel', object), ('Info', object)])
                warning = 'Shot file deleted and no combined file found'
                return traces_dict, tabledata, warning
        
        try:
            with h5py.File(source_path, 'r') as f:
                # Check if ADwin device exists
                if 'devices/ADwin' not in f:
                    return traces_dict, np.array([], dtype=[]), 'No ADwin device data available in source file'
                
                adwin_group = f['devices/ADwin']
                
                # Check if analog input data exists
                if 'ANALOG_IN/TIMES' not in adwin_group or 'data/traces/ADwinAnalogIn_DATA' not in f:
                    return traces_dict, np.array([], dtype=[]), 'No analog input data in shot file'
                
                times_table = adwin_group['ANALOG_IN/TIMES'][:]
                raw_data = f['data/traces/ADwinAnalogIn_DATA']
                ain_attrs = dict(adwin_group['ANALOG_IN'].attrs)
                
                # Get properties to calculate clock rate
                props = properties.get(f, 'ADwin', 'connection_table_properties')
                from user_devices.ADwinProII import CLOCK_T12
                clock_rate = CLOCK_T12 / props["PROCESSDELAY"]
                
                # Calculate which channels have data and split indices
                acquisitions_per_channel = times_table["stop_time"] - times_table["start_time"]
                channels_with_data = np.where(acquisitions_per_channel > 0)[0]
                
                if len(channels_with_data) == 0:
                    return traces_dict, np.array([], dtype=[]), 'No ADwin channels with data'
                
                # Calculate split indices only for channels with data
                acquisitions_with_data = acquisitions_per_channel[channels_with_data]
                offsets = np.concatenate(([0], np.cumsum(acquisitions_with_data)))
                
                # Extract data for each channel with measurements
                for idx, channel_idx in enumerate(channels_with_data):
                    start_idx = int(offsets[idx])
                    stop_idx = int(offsets[idx + 1])
                    if stop_idx <= start_idx:
                        continue
                    data_array = raw_data[start_idx:stop_idx]
                    
                    if not data_array.size:
                        continue
                    
                    # Get channel label from attributes if it exists
                    label_key = str(channel_idx + 1)
                    if label_key in ain_attrs and isinstance(ain_attrs[label_key], (str, bytes)):
                        label = ain_attrs[label_key]
                        if isinstance(label, bytes):
                            label = label.decode('utf-8')
                    else:
                        label = f"AIN_{channel_idx + 1}"
                    
                    # Create time array for this channel
                    start_time = times_table["start_time"][channel_idx]
                    stop_time = times_table["stop_time"][channel_idx]
                    num_points = len(data_array)
                    
                    try:
                        times = np.linspace(start_time, stop_time, num_points, endpoint=False) / clock_rate
                    except (MemoryError, np.core._exceptions._ArrayMemoryError):
                        # If linspace fails due to memory, use arange with step size instead
                        step = (stop_time - start_time) / num_points
                        times = np.arange(num_points, dtype=np.float64) * step + start_time
                        times = times / clock_rate
                    
                    # Get ADwin module properties for voltage conversion
                    # ADwinAI8 has resolution_bits=16, min_V=-10, max_V=10
                    resolution_bits = 16
                    min_V = -10
                    max_V = 10
                    
                    # Convert from digital values to voltages using DAC
                    values = DAC(data_array, resolution=resolution_bits, min_V=min_V, max_V=max_V)
                    
                    # Apply gain mode correction if present
                    if "gain_mode" in times_table.dtype.names:
                        gain_mode = times_table["gain_mode"][channel_idx]
                        values = values / (2 ** gain_mode)
                    
                    traces_dict[label] = (times, values)
                
                # Build table data with channel information
                table_rows = [(f'Channels recorded', f'{len(traces_dict)}')]
                for ch_name in sorted(traces_dict.keys()):
                    times, values = traces_dict[ch_name]
                    table_rows.append((ch_name, f'{len(values)} samples'))
                
                tabledata = np.array(table_rows, dtype=[('Channel', object), ('Info', object)])
                warning = '' if traces_dict else 'No ADwin trace data extracted'
                
        except Exception as e:
            error_msg = str(e)[:100]
            tabledata = np.array([('Error', error_msg)], dtype=[('Channel', object), ('Info', object)])
            warning = f'Error extracting ADwin traces: {error_msg}'
        
        return traces_dict, tabledata, warning