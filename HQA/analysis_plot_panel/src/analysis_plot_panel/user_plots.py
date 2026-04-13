# -*- coding: utf-8 -*-
"""
Created on Mon Mar 22 13:57:44 2021

@author: Nick Sauerwein
"""

import numpy as np
import pyqtgraph as pg

from pyqtgraph.Qt import QtCore, QtGui
from PyQt5.QtWidgets import QCheckBox, QLabel, QPushButton, QDoubleSpinBox, QHBoxLayout, QWidget, QGridLayout

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

        self.bt_auto_levels = QPushButton('Auto Levels', self)
        self.bt_auto_levels.clicked.connect(self.auto_levels)
        self.desciption.nextRow()
        self.desciption.addWidget(self.bt_auto_levels)

        # self.img.translate(-0.5, -0.5)
        
        self.scalex = 1
        self.scaley = 1
        
        self.cx = 0
        self.cy = 0
    
    def auto_levels(self):
        if hasattr(self, 'data_img') and self.data_img is not None:
            lo = float(np.nanmin(self.data_img))
            hi = float(np.nanmax(self.data_img))
            self.hist.setLevels(lo, hi)

    def update(self, data_img, datax, datay, datax_fit, datay_fit, xgrid, ygrid, tabledata, warning):
        
        #update plots
        self.img.setImage(data_img.T, autoLevels=False)
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

        # --- trace plot ---
        self.plot = self.plots.addPlot()
        self.trace = self.plot.plot(pen=pg.mkPen(style=QtCore.Qt.DashLine, width=2, color=color_palette[1]))
        self.plot.setLabel('bottom', 'times', units='s')
        self.plot.setLabel('left', 'volts', units='mV')

        # --- FFT plot (hidden until toggled on) ---
        self.plots.nextRow()
        self.fft_plot = self.plots.addPlot()
        self.fft_curve = self.fft_plot.plot(pen=pg.mkPen(width=1.5, color=color_palette[0]))
        self.fft_plot.setLabel('bottom', 'Frequency', units='Hz')
        self.fft_plot.setLabel('left', 'Magnitude', units='dB')
        self.fft_plot.hide()

        # --- FFT controls bar ---
        self._fft_ctrl = QWidget()
        ctrl_layout = QHBoxLayout(self._fft_ctrl)
        ctrl_layout.setContentsMargins(4, 2, 4, 2)
        ctrl_layout.setSpacing(6)

        self._cb_fft = QCheckBox('FFT')
        self._cb_fft.setChecked(False)
        self._cb_fft.stateChanged.connect(self._on_fft_toggled)
        ctrl_layout.addWidget(self._cb_fft)

        ctrl_layout.addWidget(QLabel('t start (s):'))
        self._sb_t0 = QDoubleSpinBox()
        self._sb_t0.setDecimals(4)
        self._sb_t0.setMinimum(-1e9)
        self._sb_t0.setMaximum(1e9)
        self._sb_t0.setSingleStep(0.001)
        self._sb_t0.setValue(0.0)
        self._sb_t0.valueChanged.connect(self._recompute_fft)
        ctrl_layout.addWidget(self._sb_t0)

        ctrl_layout.addWidget(QLabel('t end (s):'))
        self._sb_t1 = QDoubleSpinBox()
        self._sb_t1.setDecimals(4)
        self._sb_t1.setMinimum(-1e9)
        self._sb_t1.setMaximum(1e9)
        self._sb_t1.setSingleStep(0.001)
        self._sb_t1.setValue(1.0)
        self._sb_t1.valueChanged.connect(self._recompute_fft)
        ctrl_layout.addWidget(self._sb_t1)

        ctrl_layout.addStretch()
        self.desciption.nextRow()
        self.desciption.addWidget(self._fft_ctrl)

        # raw data cache for recompute on range change
        self._raw_times = None
        self._raw_volts = None

    def _on_fft_toggled(self, state):
        if state:
            self.fft_plot.show()
        else:
            self.fft_plot.hide()
        self._recompute_fft()

    def _recompute_fft(self):
        if not self._cb_fft.isChecked():
            return
        if self._raw_times is None or self._raw_volts is None:
            return

        t0 = self._sb_t0.value()
        t1 = self._sb_t1.value()
        if t1 <= t0:
            return

        mask = (self._raw_times >= t0) & (self._raw_times <= t1)
        t_sel = self._raw_times[mask]
        v_sel = self._raw_volts[mask]

        if len(v_sel) < 4:
            return

        # assume uniform sampling; use median dt for robustness
        dt = float(np.median(np.diff(t_sel)))
        if dt <= 0:
            return

        n = len(v_sel)
        freqs = np.fft.rfftfreq(n, d=dt)
        spectrum = np.abs(np.fft.rfft(v_sel - v_sel.mean()))
        # convert to dB, guard against zero
        spectrum_db = 20.0 * np.log10(np.maximum(spectrum, 1e-30))

        self.fft_curve.setData(freqs, spectrum_db)

    def update(self, volts, times, tabledata, sig_type, warning):
        if sig_type == 'fft':
            self.plot.setLabel('bottom', 'freqs', units='Hz')
            self.plot.setLabel('left', 'Magnitude', units='dB')
            volts = 10 * np.log(volts)
        elif sig_type == 'trace':
            self.plot.setLabel('bottom', 'times', units='s')
            self.plot.setLabel('left', 'volts', units='V')
            self.plot.setLogMode(False, False)
            volts = volts / 1e3

        self.trace.setData(times, volts)

        # cache for FFT recompute
        self._raw_times = np.asarray(times, dtype=float)
        self._raw_volts = np.asarray(volts, dtype=float)

        # auto-set spin box range to data extent on first update
        if len(times):
            t_min = float(times[0])
            t_max = float(times[-1])
            # only snap range if spin boxes still hold default or out-of-data values
            if self._sb_t0.value() == 0.0 and self._sb_t1.value() == 1.0:
                self._sb_t0.setValue(t_min)
                self._sb_t1.setValue(t_max)

        self._recompute_fft()

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

        self.bt_auto_levels = QPushButton('Auto Levels', self)
        self.bt_auto_levels.clicked.connect(self.auto_levels)
        self.desciption.nextRow()
        self.desciption.addWidget(self.bt_auto_levels)
    
    def auto_levels(self):
        if hasattr(self, '_last_corrected_image') and self._last_corrected_image is not None:
            lo = float(np.nanmin(self._last_corrected_image))
            hi = float(np.nanmax(self._last_corrected_image))
            self.hist_corrected.setLevels(lo, hi)

    def update(self, corrected_image, background_avg, tabledata, warning, roi_data=None):
        
        # Update corrected image
        self._last_corrected_image = corrected_image
        self.img_corrected.setImage(corrected_image.T, autoLevels=False)
        
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

        self.channel_selector_widget = None
        self.channel_checkboxes = {}
        self.all_channel_names = []
        self._fft_channel_checkboxes = {}

        # Plot item dicts – populated dynamically by _rebuild_layout
        self.plot_items = {}      # idx -> {plot, curve, channel_name, times, values}
        self.fft_plot_items = {}  # idx -> {plot, curve, channel_name}

        self.target_visible_points = 3000
        self.max_points_overview = 5000
        self._is_refreshing_curves = False

        self.table.setMinimumHeight(100)

        self.current_traces_dict = {}
        self.current_tabledata = np.array([], dtype=[])
        self.current_warning = ""

        # Spinboxes for FFT time window – embedded in the channel-selector widget
        self._sb_t0 = QDoubleSpinBox()
        self._sb_t0.setDecimals(4)
        self._sb_t0.setMinimum(-1e9)
        self._sb_t0.setMaximum(1e9)
        self._sb_t0.setSingleStep(0.001)
        self._sb_t0.setValue(0.0)
        self._sb_t0.valueChanged.connect(self._recompute_fft)

        self._sb_t1 = QDoubleSpinBox()
        self._sb_t1.setDecimals(4)
        self._sb_t1.setMinimum(-1e9)
        self._sb_t1.setMaximum(1e9)
        self._sb_t1.setSingleStep(0.001)
        self._sb_t1.setValue(1.0)
        self._sb_t1.valueChanged.connect(self._recompute_fft)

        # Link-X checkbox (re-parented into the channel selector widget each rebuild)
        self._cb_link_x = QCheckBox('Lock time axes')
        self._cb_link_x.setChecked(False)
        self._cb_link_x.stateChanged.connect(self._apply_x_link)

    # ------------------------------------------------------------------
    # FFT helpers
    # ------------------------------------------------------------------

    def _any_fft_active(self):
        return any(cb.isChecked() for cb in self._fft_channel_checkboxes.values())

    def _get_fft_channels(self):
        """Return channels whose FFT checkbox is checked."""
        return [ch for ch, cb in self._fft_channel_checkboxes.items() if cb.isChecked()]

    def _on_fft_checkbox_changed(self):
        """Rebuild layout whenever an FFT checkbox is toggled."""
        self._rebuild_layout()

    def _rebuild_layout(self):
        """Destroy and recreate all plot items to reflect current show/FFT state."""
        # Disconnect zoom signals before clearing
        for item in self.plot_items.values():
            try:
                item['plot'].vb.sigXRangeChanged.disconnect(self.on_plot_xrange_changed)
            except Exception:
                pass
        self.plot_items.clear()
        self.fft_plot_items.clear()
        self.plots.clear()

        selected = set(self.get_selected_channels())
        fft_active = self._any_fft_active()
        fft_channels = set(self._get_fft_channels())
        shown = [ch for ch in self.all_channel_names if ch in selected]

        if not fft_active:
            # Two trace columns, no FFT column
            for i, ch in enumerate(shown):
                if i >= self.max_channels:
                    break
                row = i // 2
                col = i % 2
                plot = self.plots.addPlot(row=row, col=col)
                plot.setTitle(ch)
                plot.setLabel('bottom', 'Time', units='s')
                plot.setLabel('left', 'Voltage', units='V')
                plot.showGrid(True, True, alpha=0.3)
                plot.vb.sigXRangeChanged.connect(self.on_plot_xrange_changed)
                self.plot_items[i] = {
                    'plot': plot, 'curve': None,
                    'channel_name': ch, 'times': None, 'values': None,
                }
        else:
            # Left column: time traces; right column: FFT (only FFT-checked channels)
            for i, ch in enumerate(shown):
                if i >= self.max_channels:
                    break
                plot = self.plots.addPlot(row=i, col=0)
                plot.setTitle(ch)
                plot.setLabel('bottom', 'Time', units='s')
                plot.setLabel('left', 'Voltage', units='V')
                plot.showGrid(True, True, alpha=0.3)
                plot.vb.sigXRangeChanged.connect(self.on_plot_xrange_changed)
                self.plot_items[i] = {
                    'plot': plot, 'curve': None,
                    'channel_name': ch, 'times': None, 'values': None,
                }
                if ch in fft_channels:
                    fft_plot = self.plots.addPlot(row=i, col=1)
                    fft_plot.setLabel('bottom', 'Frequency', units='Hz')
                    fft_plot.setLabel('left', 'Power', units='dBm')
                    fft_plot.showGrid(True, True, alpha=0.3)
                    fft_plot.setTitle(f'{ch} FFT')
                    fft_curve = fft_plot.plot(
                        pen=pg.mkPen(color=color_palette[i % len(color_palette)], width=1.5))
                    self.fft_plot_items[i] = {
                        'plot': fft_plot, 'curve': fft_curve, 'channel_name': ch,
                    }

        self._apply_x_link()
        self._fill_trace_data()
        self._recompute_fft()

    def _apply_x_link(self):
        """Link or unlink X axes of all trace plots depending on the checkbox state."""
        plots = [item['plot'] for item in self.plot_items.values()]
        if not plots:
            return
        if hasattr(self, '_cb_link_x') and self._cb_link_x.isChecked():
            ref_vb = plots[0].vb
            for p in plots[1:]:
                p.setXLink(plots[0])
        else:
            for p in plots:
                p.setXLink(None)

    def _fill_trace_data(self):
        """Fill current trace data into existing plot_items."""
        if not self.current_traces_dict:
            return
        for idx, plot_item in self.plot_items.items():
            ch = plot_item['channel_name']
            if ch is None or ch not in self.current_traces_dict:
                continue
            times, values = self.current_traces_dict[ch]
            times  = np.asarray(times,  dtype=float)
            values = np.asarray(values, dtype=float)
            if plot_item['curve'] is not None:
                plot_item['plot'].removeItem(plot_item['curve'])
            x_range = plot_item['plot'].vb.viewRange()[0]
            times_plot, values_plot = self._prepare_plot_data(times, values, x_range=x_range)
            if not len(times_plot):
                times_plot, values_plot = self._prepare_plot_data(times, values, x_range=None)
            curve = plot_item['plot'].plot(
                times_plot, values_plot,
                pen=pg.mkPen(color=color_palette[idx % len(color_palette)], width=1.5))
            plot_item['curve'] = curve
            plot_item['times'] = times
            plot_item['values'] = values

    def _recompute_fft(self):
        """Compute and display dBm FFT for all active fft_plot_items."""
        if not self.fft_plot_items or not self.current_traces_dict:
            return
        t0 = self._sb_t0.value()
        t1 = self._sb_t1.value()
        if t1 <= t0:
            return
        for fft_item in self.fft_plot_items.values():
            ch = fft_item['channel_name']
            if ch is None or ch not in self.current_traces_dict:
                fft_item['curve'].setData([], [])
                continue
            times, values = self.current_traces_dict[ch]
            times  = np.asarray(times,  dtype=float)
            values = np.asarray(values, dtype=float)
            mask  = (times >= t0) & (times <= t1)
            t_sel = times[mask]
            v_sel = values[mask]
            if len(v_sel) < 4:
                fft_item['curve'].setData([], [])
                continue
            dt = float(np.median(np.diff(t_sel)))
            if dt <= 0:
                continue
            n     = len(v_sel)
            freqs = np.fft.rfftfreq(n, d=dt)
            # One-sided peak amplitude spectrum (Volts)
            amp = np.abs(np.fft.rfft(v_sel - v_sel.mean())) * 2.0 / n
            amp[0] /= 2.0             # DC bin: no doubling
            if n % 2 == 0:
                amp[-1] /= 2.0        # Nyquist bin: no doubling
            # dBm = 10·log10(Vrms² / (R·1mW)),  R = 50 Ω, Vrms = amp/sqrt(2)
            R   = 50.0
            dbm = 10.0 * np.log10(np.maximum(amp**2 / (2.0 * R * 1e-3), 1e-30))
            fft_item['curve'].setData(freqs, dbm)

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
        """Rebuild the channel selector widget with Show + FFT checkboxes and time spinboxes."""
        # Clear existing checkboxes
        for cb in self.channel_checkboxes.values():
            cb.hide(); cb.setParent(None); cb.deleteLater()
        self.channel_checkboxes.clear()
        for cb in self._fft_channel_checkboxes.values():
            cb.hide(); cb.setParent(None); cb.deleteLater()
        self._fft_channel_checkboxes.clear()

        # Detach spinboxes before the old widget is deleted
        self._sb_t0.setParent(None)
        self._sb_t1.setParent(None)
        self._cb_link_x.setParent(None)

        if self.channel_selector_widget is not None:
            for i in range(self.count()):
                if self.widget(i) == self.channel_selector_widget:
                    self.widget(i).setParent(None)
                    break
            self.channel_selector_widget.deleteLater()

        # Grid layout:
        #   Row 0: "Channel"      | ch1       | ch2 | ...
        #   Row 1: "Show"         | cb        | cb  | ...
        #   Row 2: "FFT"          | cb        | cb  | ...
        #   Row 3: "FFT t0 (s):"  | [spinbox spanning all channel cols]
        #   Row 4: "FFT t1 (s):"  | [spinbox spanning all channel cols]
        self.channel_selector_widget = QWidget()
        grid = QGridLayout(self.channel_selector_widget)
        grid.setContentsMargins(4, 2, 4, 2)
        grid.setSpacing(4)

        grid.addWidget(QLabel('<b>Channel</b>'), 0, 0)
        grid.addWidget(QLabel('<b>Show</b>'),    1, 0)
        grid.addWidget(QLabel('<b>FFT</b>'),     2, 0)

        self.all_channel_names = sorted(all_channels)
        n_ch = len(self.all_channel_names)
        for col_idx, channel_name in enumerate(self.all_channel_names, start=1):
            grid.addWidget(QLabel(channel_name), 0, col_idx)

            show_cb = QCheckBox()
            show_cb.setChecked(True)
            show_cb.stateChanged.connect(self.on_channel_selection_changed)
            self.channel_checkboxes[channel_name] = show_cb
            grid.addWidget(show_cb, 1, col_idx)

            fft_cb = QCheckBox()
            fft_cb.setChecked(False)
            fft_cb.stateChanged.connect(self._on_fft_checkbox_changed)
            self._fft_channel_checkboxes[channel_name] = fft_cb
            grid.addWidget(fft_cb, 2, col_idx)

        # Time-range spinboxes spanning all channel columns
        span = max(n_ch, 1)
        grid.addWidget(QLabel('FFT t0 (s):'), 3, 0)
        grid.addWidget(self._sb_t0, 3, 1, 1, span)
        grid.addWidget(QLabel('FFT t1 (s):'), 4, 0)
        grid.addWidget(self._sb_t1, 4, 1, 1, span)
        grid.addWidget(self._cb_link_x, 5, 0, 1, span + 1)

        self.insertWidget(0, self.channel_selector_widget)
    
    def on_channel_selection_changed(self):
        """Called when a Show checkbox is toggled."""
        self._rebuild_layout()

    def get_selected_channels(self):
        """Get list of currently selected channel names."""
        return [name for name, cb in self.channel_checkboxes.items() if cb.isChecked()]

    def render_selected_channels(self):
        """Repopulate plots with current data (no layout rebuild)."""
        self._fill_trace_data()
        self._recompute_fft()

    def update(self, traces_dict, tabledata, warning):
        self.current_traces_dict = traces_dict
        self.current_tabledata = tabledata
        self.current_warning = warning

        channels_changed = set(traces_dict.keys()) != set(self.all_channel_names)
        if channels_changed:
            self.update_channel_selector(traces_dict.keys())
            self._rebuild_layout()
        else:
            self._fill_trace_data()
            self._recompute_fft()

        # Snap spinbox range to data extent on first meaningful update
        if traces_dict:
            all_times = [np.asarray(t, dtype=float) for t, _v in traces_dict.values()
                         if t is not None and len(t)]
            if all_times:
                t_min = float(min(t[0] for t in all_times))
                t_max = float(max(t[-1] for t in all_times))
                if self._sb_t0.value() == 0.0 and self._sb_t1.value() == 1.0:
                    self._sb_t0.setValue(t_min)
                    self._sb_t1.setValue(t_max)

        self.table.setData(tabledata)
        self.update_warning(warning)
