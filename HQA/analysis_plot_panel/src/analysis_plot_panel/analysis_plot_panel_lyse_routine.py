# -*- coding: utf-8 -*-
"""
Created on Thu Mar 11 14:58:18 2021

@author: Nick Sauerwein
"""
import lyse
import numpy as np

from __init__ import AnalysisPlotPanel

from user_plots import ImagingPlot, SpectrumPlot, MultiSpectrumPlot, TracePlot, FluoBackgroundPlot, ADwinTracesPlot
from user_data_extractors import FluoDataExtractor, AbsorptionDataExtractor, SpectrumDataExtractor, ScopeDataExtractor, FluoBackgroundDataExtractor, ADwinTracesDataExtractor
from data_extractors import MultiDataExtractor




# Profiling disabled to avoid conflicts with other profiling tools
# import cProfile
# import pstats

# profile = cProfile.Profile()
# profile.enable()


fm = lyse.figure_manager

# Try to get the current shot path and data
# Always get ALL h5_paths from lyse.data() for proper plotting
try:
    h5_paths = lyse.data()
    if h5_paths is not None and len(h5_paths) > 0:
        h5_path = h5_paths.filepath.iloc[-1]
    else:
        h5_path = None
except (AttributeError, KeyError, TypeError):
    # Fallback: try to get spinning top path if available
    try:
        if lyse.spinning_top:
            h5_path = lyse.path
        else:
            h5_path = None
    except:
        h5_path = None
    h5_paths = None

if h5_paths is not None and len(h5_paths):
    last_globals = run = lyse.Run(h5_paths.filepath.iloc[-1]).get_globals()

if not hasattr(fm, 'ap'):
    fm.ap = AnalysisPlotPanel(h5_paths if h5_paths is not None else lyse.data())



# Imaging Methods
imagings = ['fluo_imaging', 'absorption_imaging']

cams = {'fluo_imaging': [],
        'absorption_imaging': [],
        'mot_counting': ['MOT_Counting']}


imaging = 'fluo_imaging'
for cam in cams[imaging]:
    plot_name = imaging + ' ' + cam
    
    if not plot_name in fm.ap.plots:
        ip = ImagingPlot(plot_name)
        
        fm.ap.add_plot_dock(plot_name, ip, FluoDataExtractor(imaging, cam))
        
        
imaging = 'absorption_imaging'
for cam in cams[imaging]:
    plot_name = imaging + ' ' + cam
    
    if not plot_name in fm.ap.plots:        
        ip = ImagingPlot(plot_name)
        
        fm.ap.add_plot_dock(plot_name, ip, AbsorptionDataExtractor(imaging, cam))

# Fluorescence background analysis plot
for cam in ['MOT_Counting']:
    plot_name = 'fluo_background ' + cam
    
    if not plot_name in fm.ap.plots:
        fbp = FluoBackgroundPlot(plot_name)
        fm.ap.add_plot_dock(plot_name, fbp, FluoBackgroundDataExtractor(cam))

# ADwin analog input traces plot
plot_name = 'ADwin Traces'
if not plot_name in fm.ap.plots:
    atp = ADwinTracesPlot(plot_name)
    fm.ap.add_plot_dock(plot_name, atp, ADwinTracesDataExtractor())

#imaging = 'mot_counting'
#for cam in cams[imaging]:
#    plot_name = imaging + ' ' + cam
#    
#    if not plot_name in fm.ap.plots:        
#        ip = ImagingPlot(plot_name)
#        
#        fm.ap.add_plot_dock(plot_name, ip, FluoDataExtractor(imaging, cam))


# Spectra
# SpectrumDataExtractorDict = {}
# for spec_counter in range(len(last_globals['cavity_probe_names'])):
#     name = last_globals['cavity_probe_names'][spec_counter]
#     frametype = last_globals['cavity_probe_frametypes'][spec_counter]
#     spectrum_name = name+' '+frametype

#     if not spectrum_name in fm.ap.plots:
#         sp = SpectrumPlot(spectrum_name)
        
#         SpectrumDataExtractorDict[spectrum_name] = SpectrumDataExtractor(name, frametype)
        
#         fm.ap.add_plot_dock(spectrum_name, sp, SpectrumDataExtractorDict[spectrum_name])

# if not 'MultiSpectrumPlot' in fm.ap.plots:
#     msde = MultiDataExtractor()
#     for key in SpectrumDataExtractorDict:
#         msde[key] = SpectrumDataExtractorDict[key]
    
#     msp = MultiSpectrumPlot('All Spectra', SpectrumDataExtractorDict.keys())
#     msp.data_extractor = msde

#     fm.ap.add_plot_dock('MultiSpectrumPlot', msp, msde)

# Scope traces
# ScopeDataExtractorDict = {}
# names = last_globals['trace_names']
# for name in names :
#     frametype = ''
#     spectrum_name = name+' '+frametype

#     if not spectrum_name in fm.ap.plots:
#         tp = TracePlot(spectrum_name)
#         ScopeDataExtractorDict[spectrum_name] = ScopeDataExtractor(name, frametype)
#         fm.ap.add_plot_dock(spectrum_name, tp, ScopeDataExtractorDict[spectrum_name])

fm.ap.update_h5_paths(h5_paths)
fm.ap.refresh(h5_path) 
        
# profile.disable()
# ps = pstats.Stats(profile)
# ps.sort_stats('cumtime')
# ps.print_stats(10)




