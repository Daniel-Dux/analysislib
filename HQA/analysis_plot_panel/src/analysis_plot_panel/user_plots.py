# -*- coding: utf-8 -*-
"""
Created on Mon Mar 22 13:57:44 2021

@author: Nick Sauerwein
"""

import numpy as np
import pyqtgraph as pg

from pyqtgraph.Qt import QtCore, QtGui
from PyQt5.QtWidgets import QCheckBox, QLabel

from __init__ import AnalysisPlot, color_palette



class ImagingPlot(AnalysisPlot):
    
    def __init__(self, title, **kwargs):
        
        super().__init__(title, **kwargs)
        
        self.setMinimumHeight(550)
        self.setMinimumWidth(550)
        
        
        self.axsumy = self.plots.addPlot(title="")
        self.axsumy.setFixedWidth(100)
        
        
        
        self.sumy = self.axsumy.plot()
        self.sumy_fit = self.axsumy.plot(pen=pg.mkPen(style=QtCore.Qt.DashLine, color = color_palette[1]))
        
        self.img = pg.ImageItem()
        self.aximg = self.plots.addPlot(title="")
        
        self.aximg.addItem(self.img)
        
        self.axsumy.setYLink(self.aximg)
        
        
        # Isocurve draplotsg
        self.iso = pg.IsocurveItem(level=1000, pen=color_palette[2])
        self.iso.setParentItem(self.img)
        self.iso.setZValue(5)
        
        # Contrast/color control
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.img)
        self.plots.addItem(self.hist)
        
        # Draggable line for setting isocurve level
        self.isoLine = pg.InfiniteLine(angle=0, movable=True, pen=color_palette[2])
        self.hist.vb.addItem(self.isoLine)
        self.hist.vb.setMouseEnabled(y=False) # makes user interaction a little easier
        self.isoLine.setValue(1000)
        self.isoLine.setZValue(1000) # bring iso line above contrast controls
        self.isoLine.sigDragged.connect(self.updateIsocurve)

    

        # Monkey-patch the image to use our custom hover function. 
        # This is generally discouraged (you should subclass ImageItem instead),
        # but it works for a very simple use like this. 
        self.img.hoverEvent = self.imageHoverEvent
        
        self.plots.nextRow()
        self.plots.nextColumn()
        
        self.axsumx = self.plots.addPlot()
        self.axsumx.setFixedHeight(100)
        self.axsumx.setXLink(self.aximg)
        
        
        
        self.sumx = self.axsumx.plot()
        self.sumx_fit = self.axsumx.plot(pen=pg.mkPen(style=QtCore.Qt.DashLine, color = color_palette[1]))
        
        
        self.table.setMinimumHeight(85)

        
        # self.img.translate(-0.5, -0.5)
        
        self.scalex = 1
        self.scaley = 1
        
        self.cx = 0
        self.cy = 0
    
     
    def update(self, data_img, datax, datay, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning):
        
        #update plots
        self.img.setImage(data_img.T)
        self.iso.setData(data_img.T)        
        
        self.data_img = data_img
        
        self.sumy.setData(datay, ygrid)
        self.sumy_fit.setData(datay_fit, ygrid)
        self.sumx.setData(xgrid, datax)
        self.sumx_fit.setData(xgrid, datax_fit)
        
        
        
        # set position and scale of image (robust across pyqtgraph/Qt versions)
        dx = xgrid[1] - xgrid[0]
        dy = ygrid[1] - ygrid[0]

        x0 = xgrid[0] - 0.5 * dx
        y0 = ygrid[0] - 0.5 * dy
        w  = dx * len(xgrid)
        h  = dy * len(ygrid)

        self.img.setRect(QtCore.QRectF(x0, y0, w, h))

        # keep these for your bookkeeping / hover math if you want
        self.scalex = dx
        self.scaley = dy
        self.cx = xgrid[0]
        self.cy = ygrid[0]
        
        self.axsumx.setLabel('bottom', tabledata[0][0], units = 'mm')
        self.axsumy.setLabel('left', tabledata[1][0], units = 'mm')
        
        #update table and warning
        self.table.setData(tabledata)
        self.update_warning(warning)
         
    def updateIsocurve(self):
        self.iso.setLevel(self.isoLine.value())
        
    def imageHoverEvent(self, event):
        """Show the position, pixel, and value under the mouse cursor.
        """
        if event.isExit():
            self.aximg.setTitle("")
            return
        pos = event.pos()
        i, j = pos.y(), pos.x()
        i = int(np.clip(i, 0, self.data_img.shape[0] - 1))
        j = int(np.clip(j, 0, self.data_img.shape[1] - 1))
        val = self.data_img[i, j]
        ppos = self.img.mapToParent(pos)
        x, y = ppos.x(), ppos.y()
        self.aximg.setTitle("pos: (%0.1f, %0.1f) value: %g" % (x, y, val))


class MultiSpectrumPlot(AnalysisPlot):
    def __init__(self, title, labels, **kwargs):
        super().__init__(title, **kwargs)
        
        self.labels = labels
        
        self.setMinimumHeight(200)
        self.setMinimumWidth(400)
        
        self.plot = self.plots.addPlot()
        
        self.curves_hist = {}
        self.curves_fit = {}
        for i, label in enumerate(labels):
           self.curves_hist[label]= self.plot.plot([0,1],[0], stepMode="center", fillLevel=0, fillOutline=True, brush=color_palette[i], name = label)
           self.curves_fit[label] = self.plot.plot(pen=pg.mkPen(style=QtCore.Qt.DashLine,width=0.5, color = (211,211,211), ))
        
        
        self.legend = pg.LegendItem()
        self.legend.setParentItem(self.plot.graphicsItem())
        for i, label in enumerate(labels):
           self.legend.addItem(self.curves_hist[label], label)
           
        self.plot.setLabel('bottom', 'frequency', units = 'MHz')
        self.plot.setLabel('left', 'counts', units = '1')
        
        
    def update(self,data):
        for label in self.labels:
            freqs, counts, omega0, kappa, A, offset, f0, f1, duration,tabledata , warning = data[label]
            
            #update_plot
            self.freq2t = lambda freq: duration * (freq - f0)/(f1 - f0)
            self.cnt2rate = lambda c: c/(duration/(len(counts)))
            self.rate2cnt = lambda c: c*(duration/(len(counts)))
            
            deltafreqs = freqs[1] - freqs[0]
            freqs = np.append(freqs, freqs[-1] + deltafreqs)
            freqs -= deltafreqs / 2.
            
            self.curves_hist[label].setData(freqs, counts)
            
            
            lorenzian = lambda omega, omega0, kappa, A, offset: A * (kappa/2)**2 / ((omega - omega0)**2 + (kappa/2)**2) + offset
            freqsp = np.linspace(f0, f1, 400)
            
            self.curves_fit[label].setData(freqsp, lorenzian(2*np.pi*freqsp, omega0, kappa, A, offset))

class SpectrumPlot(AnalysisPlot):
    def __init__(self, title, maximal_count_rate = 10e6, **kwargs):
        super().__init__(title, **kwargs)
        
        
        self.setMinimumHeight(200)
        self.setMinimumWidth(400)
        
        self.plot = self.plots.addPlot()
        
        self.curve_hist = self.plot.plot([0,1],[0], stepMode="center", fillLevel=0, fillOutline=True, brush=color_palette[0])
        self.curve_fit = self.plot.plot(pen=pg.mkPen(style=QtCore.Qt.DashLine,width=2, color = color_palette[1], ))
        
        self.plot.setLabel('bottom', 'frequency', units = 'MHz')
        self.plot.setLabel('left', 'counts', units = '1')
        
        self.maxrate = pg.InfiniteLine(angle=0, pen=pg.mkPen(style=QtCore.Qt.DashLine))
        self.maximal_count_rate = maximal_count_rate
        
        self.plot.addItem(self.maxrate, ignoreBounds = True)
        
        f = lambda x: x
        
        self.secondary_xaxis('time', f, units = 's')
        self.secondary_yaxis('counte rate', f, units = 'Hz')
        
        
    def update(self,freqs, counts, omega0, kappa, A, offset, f0, f1, duration,tabledata , warning): 
        
        #update_plot
        self.freq2t = lambda freq: duration * (freq - f0)/(f1 - f0)
        self.cnt2rate = lambda c: c/(duration/(len(counts)))
        self.rate2cnt = lambda c: c*(duration/(len(counts)))
        
        self.axx2f = self.freq2t
        self.axy2f = self.cnt2rate
        
        self.maxrate.setValue(self.rate2cnt(self.maximal_count_rate))
        
        deltafreqs = freqs[1] - freqs[0]
        freqs = np.append(freqs, freqs[-1] + deltafreqs)
        freqs -= deltafreqs / 2.
        
        
        lorenzian = lambda omega, omega0, kappa, A, offset: A * (kappa/2)**2 / ((omega - omega0)**2 + (kappa/2)**2) + offset

        freqsp = np.linspace(f0, f1, 400)
        
        self.curve_hist.setData(freqs, counts)
        
        self.curve_fit.setData(freqsp, lorenzian(2*np.pi*freqsp, omega0, kappa, A, offset))
        
        
        #update table and warning
        self.table.setData(tabledata)
        self.update_warning(warning)
        
    def secondary_xaxis(self,label, f, **kwargs):
        
        self.axx2 = pg.AxisItem('top')
        self.axx2f = f
        
        self.plot.layout.addItem(self.axx2, 0 ,1)
        
        self.axx2.setLabel(label,**kwargs)
        
        def update_secondary_xaxis():
            view = np.array(self.plot.vb.viewRange()[0])
            self.axx2.setRange(*self.axx2f(view))
        
        self.plot.vb.sigXRangeChanged.connect(update_secondary_xaxis)
        self.plot.vb.sigResized.connect(update_secondary_xaxis)
        
    def secondary_yaxis(self,label, f,**kwargs):
        
        self.axy2 = pg.AxisItem('right')
        self.axy2f = f
        self.plot.layout.addItem(self.axy2, 2 ,2)
        
        self.axy2.setLabel(label,**kwargs)
        
        def update_secondary_yaxis():
            view = np.array(self.plot.vb.viewRange()[1])
            self.axy2.setRange(*self.axy2f(view))
        
        self.plot.vb.sigYRangeChanged.connect(update_secondary_yaxis)
        self.plot.vb.sigResized.connect(update_secondary_yaxis)
        
class TracePlot(AnalysisPlot):
    def __init__(self, title, **kwargs):
        super().__init__(title, **kwargs)

        self.setMinimumHeight(200)
        self.setMinimumWidth(400)
        
        self.plot = self.plots.addPlot()
        
        self.trace = self.plot.plot(pen=pg.mkPen(style=QtCore.Qt.DashLine,width=2, color = color_palette[1], ))

        self.plot.setLabel('bottom', 'times', units = 's')
        self.plot.setLabel('left', 'volts', units = 'mV')
        
        
        
    def update(self,volts, times, tabledata, sig_type, warning): 
        #update_plot        
        # print(type(volts))
        volts_=np.array([])
        if sig_type == 'fft' :
            self.plot.setLabel('bottom', 'freqs', units = 'Hz')
            self.plot.setLabel('left', 'Magnitude', units = 'dB')
            # self.plot.setLogMode(False,True)
            volts = 10*np.log(volts)
            
        elif sig_type == 'trace' :
            self.plot.setLabel('bottom', 'times', units = 's')
            self.plot.setLabel('left', 'volts', units = 'V')
            self.plot.setLogMode(False,False)
            volts = volts/1e3
        
        self.trace.setData(times, volts)
        
        
        #update table and warning
        self.table.setData(tabledata)
        self.update_warning(warning)

class FluoBackgroundPlot(AnalysisPlot):
    """Plot for fluorescence background-subtracted images"""
    
    def __init__(self, title, **kwargs):
        
        super().__init__(title, **kwargs)
        
        self.setMinimumHeight(500)
        self.setMinimumWidth(800)
        
        # Corrected image plot (now full width)
        self.img_corrected = pg.ImageItem()
        self.ax_corrected = self.plots.addPlot(title="Corrected Image")
        self.ax_corrected.addItem(self.img_corrected)
        
        # Contrast/color control for corrected image
        self.hist_corrected = pg.HistogramLUTItem()
        self.hist_corrected.setImageItem(self.img_corrected)
        self.plots.addItem(self.hist_corrected)
        
        # ROI rectangles (non-resizable, non-movable)
        self.signal_roi_rect = pg.ROI([0, 0], [1, 1], pen=pg.mkPen('g', width=2), movable=False, resizable=False)
        self.ax_corrected.addItem(self.signal_roi_rect)
        
        self.bg_roi_rect = pg.ROI([0, 0], [1, 1], pen=pg.mkPen('r', width=2), movable=False, resizable=False)
        self.ax_corrected.addItem(self.bg_roi_rect)
        
        self.table.setMinimumHeight(100)
    
    def update(self, corrected_image, background_avg, tabledata, warning, roi_data=None):
        
        # Update corrected image
        self.img_corrected.setImage(corrected_image.T)
        
        # Update ROI positions if available
        if roi_data is not None:
            # Signal ROI (green)
            sig_x, sig_y, sig_w, sig_h = roi_data['signal']
            self.signal_roi_rect.setPos([sig_x - sig_w/2, sig_y - sig_h/2])
            self.signal_roi_rect.setSize([sig_w, sig_h])
            
            # Background ROI (red)
            bg_x, bg_y, bg_w, bg_h = roi_data['background']
            self.bg_roi_rect.setPos([bg_x - bg_w/2, bg_y - bg_h/2])
            self.bg_roi_rect.setSize([bg_w, bg_h])
        
        # Update table and warning
        self.table.setData(tabledata)
        self.update_warning(warning)        


class ADwinTracesPlot(AnalysisPlot):
    """Plot for ADwin analog input traces with multiple channels"""
    
    def __init__(self, title, max_channels=8, **kwargs):
        super().__init__(title, **kwargs)
        
        self.setMinimumHeight(400)
        self.setMinimumWidth(600)
        self.max_channels = max_channels
        
        # Add channel selector at the top - insert before plots
        self.channel_selector_widget = None
        self.channel_selector_label = None
        self.channel_checkboxes = {}
        self.all_channel_names = []
        
        # Pre-allocate grid of plots
        num_cols = 2
        num_rows = (max_channels + num_cols - 1) // num_cols
        
        self.plot_items = {}
        self.curves_dict = {}
        self.channel_names = []
        self.target_visible_points = 3000
        self.max_points_overview = 5000
        self._is_refreshing_curves = False
        
        # Create all plots upfront in a grid
        for i in range(max_channels):
            row = i // num_cols
            col = i % num_cols
            plot = self.plots.addPlot(row=row, col=col)
            plot.setLabel('bottom', 'Time', units='s')
            plot.setLabel('left', 'Voltage', units='V')
            plot.showGrid(True, True, alpha=0.3)
            plot.hideAxis('left')
            plot.hideAxis('bottom')
            plot.vb.sigXRangeChanged.connect(self.on_plot_xrange_changed)
            self.plot_items[i] = {
                'plot': plot,
                'curve': None,
                'channel_name': None,
                'times': None,
                'values': None,
            }
        
        self.table.setMinimumHeight(100)
        
        # Store all traces data for re-rendering when selection changes
        self.current_traces_dict = {}
        self.current_tabledata = np.array([], dtype=[])
        self.current_warning = ""

    def _prepare_plot_data(self, times, values, x_range=None):
        """Prepare plot data with adaptive downsampling.

        If x_range is provided, downsample based on visible points only,
        so zooming in increases the effective displayed resolution.
        """
        if times is None or values is None or len(values) == 0:
            return np.array([]), np.array([])

        if x_range is None:
            if len(values) <= self.max_points_overview:
                return times, values
            stride = int(np.ceil(len(values) / self.max_points_overview))
            return times[::stride], values[::stride]

        x0, x1 = x_range
        if x1 < x0:
            x0, x1 = x1, x0

        start_idx = int(np.searchsorted(times, x0, side='left'))
        stop_idx = int(np.searchsorted(times, x1, side='right'))

        start_idx = max(0, start_idx - 1)
        stop_idx = min(len(times), stop_idx + 1)

        if stop_idx <= start_idx:
            return np.array([]), np.array([])

        times_visible = times[start_idx:stop_idx]
        values_visible = values[start_idx:stop_idx]

        if len(values_visible) <= self.target_visible_points:
            return times_visible, values_visible

        stride = int(np.ceil(len(values_visible) / self.target_visible_points))
        return times_visible[::stride], values_visible[::stride]

    def _refresh_plot_curve(self, plot_item):
        """Refresh a single curve according to current visible x-range."""
        curve = plot_item['curve']
        times = plot_item['times']
        values = plot_item['values']
        if curve is None or times is None or values is None:
            return

        x_range = plot_item['plot'].vb.viewRange()[0]
        times_plot, values_plot = self._prepare_plot_data(times, values, x_range=x_range)
        if len(times_plot):
            curve.setData(times_plot, values_plot)

    def on_plot_xrange_changed(self, *_):
        """Update displayed resolution of visible traces when zoom level changes."""
        if self._is_refreshing_curves:
            return

        self._is_refreshing_curves = True
        try:
            for plot_item in self.plot_items.values():
                if plot_item['curve'] is not None:
                    self._refresh_plot_curve(plot_item)
        finally:
            self._is_refreshing_curves = False
    
    def update_channel_selector(self, all_channels):
        """Update the channel selector checkboxes based on available channels"""
        # Clear existing checkboxes
        for cb in self.channel_checkboxes.values():
            cb.hide()
            cb.setParent(None)
            cb.deleteLater()
        self.channel_checkboxes.clear()
        
        # Remove old widget if it exists
        if self.channel_selector_widget is not None:
            # Find and remove the widget from the splitter
            for i in range(self.count()):
                if self.widget(i) == self.channel_selector_widget:
                    self.widget(i).setParent(None)
                    break
            self.channel_selector_widget.deleteLater()
        
        # Create new selector widget
        self.channel_selector_widget = pg.LayoutWidget()
        self.channel_selector_label = QLabel("Show channels:")
        self.channel_selector_widget.addWidget(self.channel_selector_label)
        
        # Create new checkboxes for each channel
        self.all_channel_names = sorted(all_channels)
        for channel_name in self.all_channel_names:
            cb = QCheckBox(channel_name)
            cb.setChecked(True)  # All channels selected by default
            cb.stateChanged.connect(self.on_channel_selection_changed)
            self.channel_checkboxes[channel_name] = cb
            self.channel_selector_widget.addWidget(cb)
        
        # Insert the new widget at position 0 (top of splitter)
        self.insertWidget(0, self.channel_selector_widget)
    
    def on_channel_selection_changed(self):
        """Called when user checks/unchecks a channel"""
        # Re-render with current selection
        self.render_selected_channels()
    
    def get_selected_channels(self):
        """Get list of currently selected channel names"""
        return [name for name, cb in self.channel_checkboxes.items() if cb.isChecked()]
    
    def render_selected_channels(self):
        """Render only the selected channels"""
        selected = self.get_selected_channels()
        
        # Filter traces_dict to only selected channels
        filtered_traces = {name: data for name, data in self.current_traces_dict.items() if name in selected}
        
        # Reset all plots
        for i in self.plot_items.values():
            plot = i['plot']
            if i['curve'] is not None:
                plot.removeItem(i['curve'])
            i['curve'] = None
            i['channel_name'] = None
            i['times'] = None
            i['values'] = None
            plot.setTitle('')
            plot.hideAxis('left')
            plot.hideAxis('bottom')
        
        if not filtered_traces:
            self.update_warning(self.current_warning or "No traces selected")
            return
        
        # Populate plots with selected data
        for idx, (channel_name, (times, values)) in enumerate(sorted(filtered_traces.items())):
            if idx >= self.max_channels:
                break
            
            plot_item = self.plot_items[idx]
            plot = plot_item['plot']
            
            # Show axes
            plot.showAxis('left')
            plot.showAxis('bottom')
            
            # Set title
            plot.setTitle(channel_name)

            # Store full-resolution data and render with adaptive visible-range downsampling
            plot_item['times'] = times
            plot_item['values'] = values
            x_range = plot.vb.viewRange()[0]
            times_plot, values_plot = self._prepare_plot_data(times, values, x_range=x_range)
            if not len(times_plot):
                times_plot, values_plot = self._prepare_plot_data(times, values, x_range=None)
            
            # Create new curve
            curve = plot.plot(times_plot, values_plot, 
                            pen=pg.mkPen(color=color_palette[idx % len(color_palette)], width=1.5))
            plot_item['curve'] = curve
            plot_item['channel_name'] = channel_name
    
    def update(self, traces_dict, tabledata, warning):
        """
        Update the plot with ADwin trace data.
        
        Parameters
        ----------
        traces_dict : dict
            Dictionary mapping channel names to (times, values) tuples
        tabledata : numpy.ndarray
            Table data to display
        warning : str
            Warning message if any
        """
        
        # Store current data
        self.current_traces_dict = traces_dict
        self.current_tabledata = tabledata
        self.current_warning = warning
        
        # Update channel selector if channels changed
        if set(traces_dict.keys()) != set(self.all_channel_names):
            self.update_channel_selector(traces_dict.keys())
        
        # Render with current selection
        self.render_selected_channels()
        
        # Update table and warning
        self.table.setData(tabledata)
        self.update_warning(warning)

        