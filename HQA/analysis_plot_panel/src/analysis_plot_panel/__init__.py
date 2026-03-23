# -*- coding: utf-8 -*-
"""
Created on Wed Mar 10 15:35:59 2021

@author: nicks
"""

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore
import numpy as np
import sys

from pyqtgraph.dockarea import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import QIntValidator, QStandardItemModel, QStandardItem, QColor

from PIL import ImageColor

import lyse

import collections

from data_extractors import MultiDataExtractor, SingleDataExtractor, ArrayDataExtractor, EmptyDataExtractor, DataExtractorManager

color_palette_html = ['#1f77b4', 
                      '#ff7f0e', 
                      '#2ca02c', 
                      '#d62728', 
                      '#9467bd', 
                      '#8c564b',
                      '#e377c2', 
                      '#7f7f7f',
                      '#bcbd22',
                      '#17becf']

color_palette = [ImageColor.getcolor(color, "RGB") for color in color_palette_html]





from sortedcontainers import SortedSet

class ShotSelector(pg.LayoutWidget):
    
    valueChanged = pyqtSignal()
    selectionChanged = pyqtSignal()
    
    def __init__(self, **kwargs):
        
        super().__init__(**kwargs)
        
        self.nshots = 1
        
        self.setFixedHeight(100)
        
        self.current_idx_le= QLineEdit(self)
        
        self.current_idx_le.setMaximumWidth(30)
        self.current_idx_le.setValidator(QIntValidator()) 
        
        self.current_idx_le.setText(str(-1))
        
        self.addWidget(self.current_idx_le)
        
        self.slider = QSlider(self)
        
        self.slider.setPageStep(1)
        self.slider.setOrientation(Qt.Horizontal)
        
        self.addWidget(self.slider, colspan = 2)
        
        self.nextRow()
        
        self.addWidget(QLabel('index selector'))
        
        self.idx_select_le = QLineEdit(self)
        self.idx_select_le.setText(':')
        self.addWidget(self.idx_select_le)
        
        self.warning = QLabel()
        self.warning.setMargin(5)
        self.update_warning()
        self.addWidget(self.warning)
        
        self.update_nshots(self.nshots)
        
        self.idx_select_le.editingFinished.connect(self.update_selection)
        self.current_idx_le.editingFinished.connect(self.setSliderValue)
        self.slider.valueChanged.connect(self.setLabelValue)
    
    def update_nshots(self, nshots):
        self.nshots = int(nshots)
        self.idx = np.arange(self.nshots)

        if self.nshots <= 0:
            self.idx_selected = SortedSet([])
            self.slider.setRange(0, 0)
            self.current_idx_le.setText('0')
            self.update_warning('no shots loaded')
            self.selectionChanged.emit()
            return

        self.slider.setRange(0, self.nshots - 1)
        
        self.update_selection()
        self.setSliderValue()

    
    def update_warning(self, warning = ''):
        if warning == '':
            self.warning.setStyleSheet("background-color: lightgreen")
            warning = 'all good'
        else:
            self.warning.setStyleSheet("background-color: red")
        
        self.warning.setText(warning)
        
    def update_selection(self):
        if self.nshots <= 0:
            self.idx_selected = SortedSet([])
            self.slider.setRange(0, 0)
            self.update_warning('no shots loaded')
            self.selectionChanged.emit()
            return

        self.update_warning()
        
        slice_text = self.idx_select_le.text()
        slices = slice_text.split(',')
        
        self.idx_selected = SortedSet([])
        for s in slices:
            try:
                scope = locals()
                
                select = eval('self.idx['+s+']', scope)
                
                if isinstance(select, np.ndarray):
                    for idx in select:
                        self.idx_selected.add(idx)
                else:
                    self.idx_selected.add(select)
                    
            except:
                self.update_warning('problem in selected indeces')
                return 0
            
        self.slider.setRange(0, len(self.idx_selected) - 1)
        
        
        if int(self.current_idx_le.text())%self.nshots not in self.idx_selected:
            self.current_idx_le.setText(self.idx_selected[-1])
            
            self.update_warning('last index not in selection <br> -> setting last selected')
            
        self.selectionChanged.emit()
            
    def setLabelValue(self, value):
        if not hasattr(self, 'idx_selected') or len(self.idx_selected) == 0:
            return

        newval = self.idx_selected[value]
        
        if newval != self.get_current_index():
            self.current_idx_le.setText(str(newval))
            
            self.valueChanged.emit()
        
    def setSliderValue(self):
        if self.nshots <= 0:
            return

        self.update_warning()
        
        value = int(self.current_idx_le.text())
        
        try:
            value_sl = self.idx_selected.index(value%len(self.idx))
            self.slider.setValue(value_sl)
        except ValueError:
            self.update_warning('set index not in selection <br> ignore')
    
    def get_current_index(self):
        if self.nshots <= 0:
            return 0
        return int(self.current_idx_le.text())%self.nshots
    
    def get_selected_indices(self):
        if not hasattr(self, 'idx_selected') or len(self.idx_selected) == 0:
            return np.array([], dtype=int)
        return np.array(list(self.idx_selected))
            
        
class AnalysisPlotPanel(QMainWindow):
    
    def __init__(self, h5_paths, n_rows = 3, **kwargs):
        
        self.h5_paths = h5_paths
        
        super().__init__(**kwargs)
        
        pg.mkQApp()
        
        self.n_rows = n_rows
        
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)
        self.area = DockArea()
        
        self.setCentralWidget(self.area)
        self.resize(1000,500)
        
        self.dshotselector = Dock("Shot selector")
        self.shotselector = ShotSelector()
        self.shotselector_container = pg.LayoutWidget()
        self.bt_remove_all_shots = QPushButton('Remove all shots from lyse queue', self)
        self.bt_remove_all_shots.clicked.connect(self.remove_all_shots_from_lyse_queue)
        self.shotselector_container.addWidget(self.shotselector, colspan=2)
        self.shotselector_container.nextRow()
        self.shotselector_container.addWidget(self.bt_remove_all_shots, colspan=2)
        
        self.dshotselector.addWidget(self.shotselector_container)
        self.area.addDock(self.dshotselector, 'bottom')
        
        self.qpg_dock = Dock("Quick Plot Generator")
        self.qpg_dock.addWidget(QuickPlotGenerator(self))
        self.qpg_dock.setMinimumSize(self.qpg_dock.minimumSizeHint())
        self.area.addDock(self.qpg_dock)
        
        
        self.show()
        
        self.plots = {}
        self.data_extractor_manager = DataExtractorManager()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._refresh_now)
        self._pending_h5_path = None
        self._refresh_debounce_ms = 40
        
        self.shotselector.valueChanged.connect(self.refresh)
        self.shotselector.selectionChanged.connect(self.refresh)
        
        self.df = lyse.data()

    def remove_all_shots_from_lyse_queue(self):
        try:
            current_nshots = len(self.h5_paths) if self.h5_paths is not None else 0
            if current_nshots == 0:
                QMessageBox.information(self, 'Lyse queue', 'Lyse queue is already empty.')
                return

            answer = QMessageBox.question(
                self,
                'Remove all shots',
                f'Remove all {current_nshots} shots from the lyse queue?',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

            app = None
            for module_name in ('lyse.__main__', '__main__'):
                module = sys.modules.get(module_name)
                if module is not None:
                    candidate = getattr(module, 'app', None)
                    if candidate is not None and hasattr(candidate, 'filebox'):
                        app = candidate
                        break

            if app is None:
                qapp = QApplication.instance()
                if qapp is not None:
                    for widget in qapp.topLevelWidgets():
                        candidate = getattr(widget, 'app', None)
                        if candidate is not None and hasattr(candidate, 'filebox'):
                            app = candidate
                            break

            if app is not None and hasattr(app.filebox, 'shots_model'):
                shots_model = app.filebox.shots_model
                table_view = app.filebox.ui.tableView

                table_view.selectAll()
                shots_model.remove_selection(confirm=False)
                table_view.clearSelection()
            else:
                try:
                    from labscript_utils.ls_zprocess import zmq_get
                    port = int(getattr(lyse, '_lyse_port', 42519))
                    response = zmq_get(port, 'localhost', 'clear shots', timeout=5)
                    if isinstance(response, str) and response.startswith('error'):
                        raise RuntimeError(response)
                except Exception as remote_error:
                    QMessageBox.warning(
                        self,
                        'Lyse queue',
                        'Could not access running lyse GUI instance and remote clear request failed.\n'
                        f'{remote_error}'
                    )
                    return

            refreshed_paths = lyse.data()
            nshots = len(refreshed_paths) if refreshed_paths is not None else 0
            if nshots == 0:
                QMessageBox.information(self, 'Lyse queue', 'Lyse queue cleared.')

            self.update_h5_paths(refreshed_paths)
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, 'Lyse queue', f'Failed to clear lyse queue:\n{e}')
        
    def add_plot_dock(self, plot_name,plot_widget, data_extractor, **kwargs):
        if plot_name not in self.plots:
            plot_widget.plot_name = plot_name
            plot_widget.data_extractor = data_extractor
            self.data_extractor_manager[plot_name] = data_extractor
            
            dock = Dock(plot_name,**kwargs)
            
            dock.sigClosed.connect(self.remove_plot)
            dock.addWidget(plot_widget)
            if len(self.plots):
                if len(self.plots) % self.n_rows == 2:
                    position = 'right'
                    self.area.addDock(dock, position)
                if len(self.plots) %(self.n_rows*2) in  [0, 1]:
                    position = 'bottom'
                    self.area.addDock(dock, position, relativeTo= self.area.docks[list(self.plots.keys())[-1]])
                if len(self.plots) %(self.n_rows*2) in  [3, 4]:
                    position = 'top'
                    self.area.addDock(dock, position, relativeTo= self.area.docks[list(self.plots.keys())[-1]])
                print (len(self.plots) %(self.n_rows*2), len(self.plots) %self.n_rows)
            else:
                self.area.addDock(dock, 'right')
            
            
            self.plots[plot_name] = plot_widget
        else:
            print (f'Plot {plot_name} already exists. Please choose different name.')
    
    def remove_plot(self ,dock):
        plot_name = dock.title()
        if plot_name in self.plots:
            plot_widget = self.plots[plot_name]
            # Cleanup resources
            try:
                if hasattr(plot_widget, 'data_extractor'):
                    plot_widget.data_extractor.clean_memory([])
            except:
                pass
            # Remove from data extractor manager
            if plot_name in self.data_extractor_manager.data_extractors:
                del self.data_extractor_manager.data_extractors[plot_name]
            del self.plots[plot_name]
        
    def update_h5_paths(self, h5_paths):
        # Handle None case - get fresh data from lyse
        if h5_paths is None:
            try:
                h5_paths = lyse.data()
            except:
                h5_paths = None
        # Also update the dataframe
        self.df = h5_paths
        
        self.h5_paths = h5_paths
        
        # Only update shot selector if we have valid data
        if h5_paths is not None and hasattr(h5_paths, '__len__'):
            try:
                self.shotselector.update_nshots(len(h5_paths))
            except TypeError:
                # If h5_paths is not a proper sequence, log and continue
                import logging
                logging.debug(f"Could not get length of h5_paths: {h5_paths}")
        
        for plot_name, plot in self.plots.items():
            if h5_paths is not None:
                plot.data_extractor.clean_memory(h5_paths)
            if hasattr(plot, 'update_combos'):
                try:
                    plot.update_combos(h5_paths)
                except Exception as e:
                    import logging
                    logging.debug(f"Could not update combos for plot {plot_name}: {e}")
            
    def refresh(self, h5_path = None):
        self._pending_h5_path = h5_path
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(self._refresh_debounce_ms)

    def _refresh_now(self):
        h5_path = self._pending_h5_path
        self._pending_h5_path = None

        if self.h5_paths is not None and len(self.h5_paths):

            self.h5_paths_selected = self.h5_paths.iloc[self.shotselector.get_selected_indices()]
            
            
            if h5_path == None:
                i = self.shotselector.get_current_index()
                h5_path = self.h5_paths.filepath.iloc[i]
            
            # Ensure h5_path is a string, not a Series or tuple
            if not isinstance(h5_path, str):
                if hasattr(h5_path, 'values'):
                    h5_path = str(h5_path.values[0]) if len(h5_path.values) > 0 else str(h5_path)
                elif isinstance(h5_path, (list, tuple)):
                    h5_path = str(h5_path[0]) if h5_path else None
                else:
                    h5_path = str(h5_path)
                
            self.data_extractor_manager.update_local_data(h5_path)
            
            for plot_name, plot in self.plots.items():
                plot.update_from_h5(h5_path)
        else:
            pass


class DataPlot(QSplitter):
    def __init__(self,  **kwargs):
        
        super().__init__(**kwargs)
        
        self.setOrientation(Qt.Vertical)
        
        self.plots = pg.GraphicsLayoutWidget()
        
        self.addWidget(self.plots)
        
        self.bottom = QSplitter()
        self.bottom.setOrientation(Qt.Horizontal)
        
        self.addWidget(self.bottom)
        
        self.h5_path_shown = None
        
    def cleanup(self):
        """Clean up resources to prevent memory leaks"""
        try:
            if hasattr(self, 'plots') and self.plots is not None:
                self.plots.deleteLater()
            if hasattr(self, 'bottom') and self.bottom is not None:
                self.bottom.deleteLater()
        except:
            pass
        
    def update_from_h5(self, h5_path):
        if self.h5_path_shown != h5_path or self.data_extractor.local_data_changed:
            self.h5_path_shown = h5_path
            self.update(*self.data_extractor.extract_data(h5_path))
        
class QuickDataPlot(DataPlot):
    def __init__(self, ap, **kwargs):
        
        super().__init__(**kwargs)
        
        self.plot = self.plots.addPlot()
        
        for key in self.plot.axes:
            ax = self.plot.getAxis(key)
            # Fix Z value making the grid on top of the image
            ax.setZValue(1)
        self.ap = ap
        self.h5_paths_shown = tuple()
        self._last_clean_paths_signature = None
        
        self.table = QTableWidget()
        self.table.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
        
        self.bottom.addWidget(self.table)
        
        self.plot_setting = PlotSettings(self.plot)
        
        self.bottom.addWidget(self.plot_setting)

    def get_all_h5_paths(self):
        if self.ap.h5_paths is None:
            return []
        if hasattr(self.ap.h5_paths, 'filepath'):
            return self.ap.h5_paths.filepath.tolist()
        return list(self.ap.h5_paths)

    def clean_data_extractor_if_needed(self):
        current_paths = self.get_all_h5_paths()
        current_signature = tuple(current_paths)
        if self._last_clean_paths_signature != current_signature:
            self.data_extractor.clean_memory(current_paths)
            self._last_clean_paths_signature = current_signature
        return current_paths
        
    def update_from_h5(self, h5_path = None):
        self.update_data_extractor()
        current_paths = self.get_all_h5_paths()
        current_signature = tuple(current_paths)

        if self.data_extractor.local_data_changed or self.h5_paths_shown != current_signature:
            self.h5_paths_shown = current_signature
            self.update()


class AnalysisPlot(DataPlot):
    def __init__(self, title,  **kwargs):
        
        super().__init__(**kwargs)
        
        
        self.table = pg.TableWidget()
        
        self.bottom.addWidget(self.table)
        
        self.desciption = pg.LayoutWidget()
        self.title = QLabel()
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        self.title.setText('<h2>'+title+' </h2>')
        self.warning = QLabel()
        self.warning.setAlignment(QtCore.Qt.AlignCenter)
        
        self.desciption.addWidget(self.title)
        self.desciption.nextRow()
        self.desciption.addWidget(self.warning)
        
        self.bottom.addWidget(self.desciption)
        
    def update_warning(self, warning):
        if warning == '':
            self.warning.setStyleSheet("background-color: lightgreen")
            warning = 'all good'
        else:
            self.warning.setStyleSheet("background-color: red")
        
        self.warning.setText(warning)
        
    def update_from_h5(self, h5path):
        if hasattr(self, 'data_extractor'):
            self.update(*self.data_extractor.get_data(h5path))
        else:
            pass

class ExtendedCombo( QComboBox ):
    def __init__( self,  parent = None):
        super().__init__( parent )

        self.setFocusPolicy(Qt.StrongFocus)
        self.setEditable( True )
        self.completer = QCompleter( self )

        # always show all completions
        self.completer.setCompletionMode( QCompleter.UnfilteredPopupCompletion )
        self.pFilterModel = QSortFilterProxyModel( self )
        self.pFilterModel.setFilterCaseSensitivity( Qt.CaseInsensitive )

        self.completer.setPopup( self.view() )

        self.setCompleter( self.completer )

        self.lineEdit().textEdited[str].connect( self.pFilterModel.setFilterFixedString )
        self.completer.activated.connect(self.setTextIfCompleterIsClicked)

    def setModel( self, model ):
        super().setModel(model)
        self.pFilterModel.setSourceModel(model)
        self.completer.setModel(self.pFilterModel)

    def setModelColumn( self, column ):
        self.completer.setCompletionColumn( column )
        self.pFilterModel.setFilterKeyColumn( column )
        super().setModelColumn( column )


    def view( self ):
        return self.completer.popup()

    def index( self ):
        return self.currentIndex()

    def setTextIfCompleterIsClicked(self, text):
      if text:
        index = self.findText(text)
        self.setCurrentIndex(index)


class PlotSettings(QTableWidget):
    def __init__(self,plot, **kwargs):
        super().__init__(**kwargs)
        
        self.plot = plot
        self.setColumnCount(3)
        self.setColumnWidth(0, 100)
        self.setColumnWidth(1, 100)
        
        self.setHorizontalHeaderLabels(['parameter', 'setting', 'units'])
        
        self.setRowCount(4)
        
        
        # title
        i = 0
        self.le_title = QLineEdit()
        
        self.setCellWidget(i, 0, QLabel('title'))
        self.setCellWidget(i, 1, self.le_title)
        
        self.le_title.textChanged[str].connect(self.set_title)
        
        
        # xlabel
        i +=1
        self.le_xlabel = QLineEdit()
        self.le_xlabel_unit = QLineEdit()
        
        self.setCellWidget(i, 0, QLabel('xlabel'))
        self.setCellWidget(i, 1, self.le_xlabel)
        self.setCellWidget(i, 2, self.le_xlabel_unit)
        
        self.le_xlabel.textChanged[str].connect(self.set_xlabel)
        self.le_xlabel_unit.textChanged[str].connect(self.set_xlabel)
        
        # ylabel
        i +=1
        self.le_ylabel = QLineEdit()
        self.le_ylabel_unit = QLineEdit()
        
        self.setCellWidget(i, 0, QLabel('ylabel'))
        self.setCellWidget(i, 1, self.le_ylabel)
        self.setCellWidget(i, 2, self.le_ylabel_unit)
        
        self.le_ylabel.textChanged[str].connect(self.set_ylabel)
        self.le_ylabel_unit.textChanged[str].connect(self.set_ylabel)
        
        # grid
        i +=1
        self.cb_grid = QCheckBox()
        self.setCellWidget(i, 0, QLabel('grid'))
        self.setCellWidget(i, 1, self.cb_grid)
        
        self.cb_grid.stateChanged.connect(self.set_grid)
        
    def set_title(self):
        self.plot.setTitle(self.le_title.text())
        
    def set_xlabel(self):
        self.plot.setLabel('bottom', self.le_xlabel.text(), units = self.le_xlabel_unit.text())
        
    def set_ylabel(self):
        self.plot.setLabel('left', self.le_ylabel.text(), units = self.le_ylabel_unit.text())
        
    def set_grid(self):
        self.plot.showGrid(x = self.cb_grid.isChecked(), y = self.cb_grid.isChecked(), alpha = 0.3)
  
from pandas.api.types import is_numeric_dtype
class NumericDataCombo(ExtendedCombo):
    
    def __init__(self, df, **kwargs):
        
        super().__init__(**kwargs)
        self._last_model_signature = None
        self._committed_text = 'shot number'

        self.currentIndexChanged.connect(self._commit_current_text)
        if self.lineEdit() is not None:
            self.lineEdit().editingFinished.connect(self._commit_current_text)

        self.update_model(df)

    def _commit_current_text(self):
        text = str(self.currentText())
        if self.findText(text) >= 0:
            self._committed_text = text

    def get_stable_text(self):
        text = str(self.currentText())
        if self.findText(text) >= 0:
            self._committed_text = text
            return text
        return self._committed_text
                
    def update_model(self, df):
        signature = None
        if df is not None and hasattr(df, 'columns') and hasattr(df, 'dtypes'):
            try:
                signature = (
                    tuple(df.columns.tolist()),
                    tuple(str(df.dtypes[col]) for col in df.columns)
                )
            except Exception:
                signature = None

        if signature is not None and signature == self._last_model_signature:
            return

        current_text = str(self.currentText()) if self.count() else 'shot number'
        model = QStandardItemModel()

        item = QStandardItem('shot number')
        model.setItem(0, 0, item)

        i = 1
        if df is None or not hasattr(df, 'columns') or not hasattr(df, 'dtypes'):
            self.setModel(model)
            self.setCurrentText('shot number')
            return

        added_labels = {'shot number'}
        for midx in df.columns:
            if is_numeric_dtype(df.dtypes[midx]):
                if isinstance(midx, tuple):
                    column_name = ','.join([str(x) for x in midx if x not in (None, '')])
                else:
                    column_name = str(midx)

                if not column_name or column_name in added_labels:
                    continue

                item = QStandardItem(column_name)
                model.setItem(i, 0, item)
                i += 1
                added_labels.add(column_name)
                
        self.setModel(model)
        self._last_model_signature = signature
        if self.findText(current_text) >= 0:
            self.setCurrentText(current_text)
            self._committed_text = current_text
        elif self.findText(self._committed_text) >= 0:
            self.setCurrentText(self._committed_text)
        else:
            self.setCurrentText('shot number')
            self._committed_text = 'shot number'
        
    def get_idx(self):
        return tuple(self.get_stable_text().split(','))
        
class Quick1DPlot(QuickDataPlot):
    
    def __init__(self,ap,**kwargs):
        
        super().__init__(ap,**kwargs)        
        self.nplots = 0
        
        self.table.setColumnCount(6)
        self.table.setRowCount(1)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 30)
        self.table.setColumnWidth(3, 50)
        self.table.setColumnWidth(4, 60)
        self.table.setColumnWidth(5, 80)
        self.table.setHorizontalHeaderLabels(['xvalue', 'yvalue', 'color', 'show', 'scatter', 'mean&err'])
         
        self.combos = []
        self.curves = []
        self.error_bars = []
        self.show_cbs = []
        self.scatter_cbs = []
        self.mean_error_cbs = []
        self._last_curve_selection_signature = None
        self._df_idx_map_cache = {}
        self._df_idx_map_signature = None
        self._combos_update_pending = False
        self._combo_update_timer = QTimer(self)
        self._combo_update_timer.setSingleShot(True)
        self._combo_update_timer.timeout.connect(self._apply_pending_combo_updates)
        
        self.mk_buttons()
        
            
    def mk_buttons(self):
        self.bt_add_plot = QPushButton('Add plot', self)
        self.bt_add_plot.clicked.connect(self.add_plot)
        self.table.setCellWidget(self.nplots, 0, self.bt_add_plot)
        
        
        self.bt_update = QPushButton('Update', self)
        self.bt_update.clicked.connect(self.update_from_h5)
        self.table.setCellWidget(self.nplots, 1, self.bt_update)
    
    def add_plot(self):
        self.nplots += 1
        self.table.setRowCount(self.nplots+1)
        combox = NumericDataCombo(self.ap.df if self.ap.df is not None else lyse.data())
        comboy = NumericDataCombo(self.ap.df if self.ap.df is not None else lyse.data())
        
        self.combos += [[combox,comboy]]
        self.table.setCellWidget(self.nplots - 1, 0, combox)
        self.table.setCellWidget(self.nplots - 1, 1, comboy)
        
        self.table.setItem(self.nplots - 1, 2, QTableWidgetItem())
        self.table.item(self.nplots - 1, 2).setBackground(QColor(*color_palette[self.nplots - 1]))
        
        #self.table.setFixedSize(self.table.sizeHint())
        
        self.curves += [self.plot.plot(pen=pg.mkPen(color = color_palette[self.nplots - 1], width = 1.5), symbol ='x', symbolPen = None, symbolBrush = None)]
        
        # Add ErrorBarItem for each curve
        error_bar = pg.ErrorBarItem(pen=pg.mkPen(color=color_palette[self.nplots - 1], width=1.5))
        self.plot.addItem(error_bar)
        self.error_bars += [error_bar]
        
        self.show_cbs += [QCheckBox()]
        self.show_cbs[self.nplots - 1].setChecked(True)
        self.table.setCellWidget(self.nplots - 1, 3, self.show_cbs[self.nplots - 1])
        self.show_cbs[self.nplots - 1].stateChanged.connect(self.update_shows)
        
        self.scatter_cbs += [QCheckBox()]
        self.scatter_cbs[self.nplots - 1].setChecked(False)
        self.table.setCellWidget(self.nplots - 1, 4, self.scatter_cbs[self.nplots - 1])
        self.scatter_cbs[self.nplots - 1].stateChanged.connect(self.update_scatters)
        
        self.mean_error_cbs += [QCheckBox()]
        self.mean_error_cbs[self.nplots - 1].setChecked(False)
        self.table.setCellWidget(self.nplots - 1, 5, self.mean_error_cbs[self.nplots - 1])
        self.mean_error_cbs[self.nplots - 1].stateChanged.connect(self.update_from_h5)
        
        # Set row height to ensure checkboxes are visible
        self.table.setRowHeight(self.nplots - 1, 25)
        
        self.mk_buttons()

    def update_combos(self, h5_paths):
        """Update numeric combo models when h5_paths/df change"""
        def combo_is_active(combo):
            line_edit = combo.lineEdit()
            return (
                combo.hasFocus() or
                (line_edit is not None and line_edit.hasFocus()) or
                combo.view().isVisible()
            )

        if any(combo_is_active(combo) for pair in self.combos for combo in pair):
            self._combos_update_pending = True
            self._combo_update_timer.start(250)
            return

        try:
            for combox, comboy in self.combos:
                combox.update_model(self.ap.df)
                comboy.update_model(self.ap.df)
            self._combos_update_pending = False
        except Exception as e:
            import logging
            logging.debug(f"Error updating Quick1DPlot combos: {e}")

    def _apply_pending_combo_updates(self):
        if self._combos_update_pending:
            self.update_combos(self.ap.h5_paths)
    
        
    def update_shows(self):
        for k, cb in enumerate(self.show_cbs):
            if cb.isChecked():
                self.curves[k].show()
            else:
                self.curves[k].hide()
                
    def update_scatters(self):
        for k, cb in enumerate(self.scatter_cbs):
            pen=pg.mkPen(color = color_palette[k], width = 1.5)
            brush=pg.mkBrush(color = color_palette[k])
            if cb.isChecked():
                self.curves[k].setSymbolBrush(brush)
                self.curves[k].setPen(None)
                self.error_bars[k].hide()
            else:
                self.curves[k].setSymbolBrush(None and self.show_cbs[k].isChecked())
                self.curves[k].setPen(pen)
                if self.mean_error_cbs[k].isChecked():
                    self.error_bars[k].show()
                else:
                    self.error_bars[k].hide()

        
    def update_data_extractor(self):
        
        idxxs = [combo[0].get_idx() for combo in self.combos]
        idxys = [combo[1].get_idx() for combo in self.combos]
        curve_signature = tuple(idxxs + idxys)
        if curve_signature != self._last_curve_selection_signature:
            self.data_extractor.children_changed = True
            self._last_curve_selection_signature = curve_signature

        df_idx_map = self._build_numeric_df_index_map()
        fallback_indices = []
        for idx in idxxs + idxys:
            if idx and idx[0] != 'shot number' and idx not in df_idx_map:
                fallback_indices.append(idx)
        fallback_indices = list(dict.fromkeys(fallback_indices))
        
        for idx in fallback_indices:
            if idx not in self.data_extractor.data_extractors:
                self.data_extractor[idx] = SingleDataExtractor(idx)

        self.data_extractor.clean_children(fallback_indices)
        if fallback_indices:
            self.clean_data_extractor_if_needed()

    def _build_numeric_df_index_map(self):
        df = self.ap.df
        if df is None or not hasattr(df, 'columns') or not hasattr(df, 'dtypes'):
            self._df_idx_map_cache = {}
            self._df_idx_map_signature = None
            return {}

        try:
            signature = (
                tuple(df.columns.tolist()),
                tuple(str(df.dtypes[col]) for col in df.columns)
            )
        except Exception:
            signature = None

        if signature is not None and signature == self._df_idx_map_signature:
            return self._df_idx_map_cache

        idx_map = {}
        for midx in df.columns:
            try:
                if not is_numeric_dtype(df.dtypes[midx]):
                    continue
            except Exception:
                continue

            if isinstance(midx, tuple):
                label = ','.join([str(x) for x in midx if x not in (None, '')])
            else:
                label = str(midx)

            if not label:
                continue

            idx_key = tuple(label.split(','))
            if idx_key not in idx_map:
                idx_map[idx_key] = midx

        self._df_idx_map_cache = idx_map
        self._df_idx_map_signature = signature
        return idx_map

    def _get_numeric_values_from_df(self, idx, n_points, df, df_idx_map):
        if idx and idx[0] == 'shot number':
            return np.arange(n_points, dtype=float)

        col = df_idx_map.get(idx)
        if col is None or df is None:
            return None

        try:
            series = df[col]
            values = np.asarray(series.to_numpy(), dtype=float)
            if len(values) != n_points:
                return None
            return values
        except Exception:
            return None
    
    def calculate_mean_and_error(self, xs, ys):
        """
        Group data by x-values and calculate mean and standard error.
        
        Parameters
        ----------
        xs : numpy.ndarray
            X-axis values
        ys : numpy.ndarray
            Y-axis values
            
        Returns
        -------
        mean_xs : numpy.ndarray
            Unique x-values (sorted)
        mean_ys : numpy.ndarray
            Mean y-value for each x-value
        std_errors : numpy.ndarray
            Standard error for each x-value
        """
        # Remove NaN values
        valid_mask = ~(np.isnan(xs) | np.isnan(ys))
        xs_clean = xs[valid_mask]
        ys_clean = ys[valid_mask]
        
        if len(xs_clean) == 0:
            return np.array([]), np.array([]), np.array([])
        
        # Sort by x-values
        sorted_indices = np.argsort(xs_clean)
        xs_sorted = xs_clean[sorted_indices]
        ys_sorted = ys_clean[sorted_indices]
        
        # Get unique x-values
        unique_xs = np.unique(xs_sorted)
        mean_ys = np.zeros_like(unique_xs)
        std_errors = np.zeros_like(unique_xs)
        
        # Calculate mean and std error for each unique x-value
        for i, x_val in enumerate(unique_xs):
            y_values = ys_sorted[xs_sorted == x_val]
            mean_ys[i] = np.mean(y_values)
            std_errors[i] = np.std(y_values) / np.sqrt(len(y_values)) if len(y_values) > 1 else 0
        
        return unique_xs, mean_ys, std_errors
        
    def update(self, data = None):
        
        # Extract ALL file paths to ensure all data is plotted
        h5_paths_to_plot = self.get_all_h5_paths()
        
        if not h5_paths_to_plot:
            # No data to plot  
            return

        idxxs = [combo[0].get_idx() for combo in self.combos]
        idxys = [combo[1].get_idx() for combo in self.combos]
        n_paths = len(h5_paths_to_plot)
        df = self.ap.df
        df_idx_map = self._build_numeric_df_index_map()
        
        # Use memory-efficient pre-allocated arrays instead of np.append in loop
        Xs = np.full((self.nplots, n_paths), np.nan, dtype=float)
        Ys = np.full((self.nplots, n_paths), np.nan, dtype=float)

        x_sources = []
        y_sources = []
        fallback_plot_indices = []
        for k in range(self.nplots):
            x_vals = self._get_numeric_values_from_df(idxxs[k], n_paths, df, df_idx_map)
            y_vals = self._get_numeric_values_from_df(idxys[k], n_paths, df, df_idx_map)
            x_sources.append(x_vals)
            y_sources.append(y_vals)

            if x_vals is not None:
                Xs[k, :] = x_vals
            if y_vals is not None:
                Ys[k, :] = y_vals

            if x_vals is None or y_vals is None:
                fallback_plot_indices.append(k)
        
        if fallback_plot_indices:
            for i, h5_path in enumerate(h5_paths_to_plot):
                data = self.data_extractor.get_data(h5_path)[0]

                for k in fallback_plot_indices:
                    idxx = idxxs[k]
                    idxy = idxys[k]

                    if x_sources[k] is None:
                        try:
                            if idxx[0] == 'shot number':
                                Xs[k, i] = i
                            else:
                                x_val = data.get(idxx) if isinstance(data, dict) else None
                                Xs[k, i] = float(x_val) if x_val is not None else np.nan
                        except Exception:
                            Xs[k, i] = np.nan

                    if y_sources[k] is None:
                        try:
                            if idxy[0] == 'shot number':
                                Ys[k, i] = i
                            else:
                                y_val = data.get(idxy) if isinstance(data, dict) else None
                                Ys[k, i] = float(y_val) if y_val is not None else np.nan
                        except Exception:
                            Ys[k, i] = np.nan
                    
        for k in range(self.nplots):
            # Remove NaN values for plotting to show only valid data points
            valid_mask = ~(np.isnan(Xs[k]) | np.isnan(Ys[k]))
            valid_xs = Xs[k][valid_mask]
            valid_ys = Ys[k][valid_mask]
            
            # Check if the mean_error checkbox exists and is checked
            if k < len(self.mean_error_cbs) and self.mean_error_cbs[k].isChecked():
                # Calculate mean and error for this curve
                mean_xs, mean_ys, std_errors = self.calculate_mean_and_error(valid_xs, valid_ys)
                
                if len(mean_xs) > 0:
                    self.curves[k].setData(mean_xs, mean_ys)
                    if k < len(self.error_bars):
                        self.error_bars[k].setData(x=mean_xs, y=mean_ys, height=std_errors)
                        self.error_bars[k].show()
                else:
                    self.curves[k].setData([], [])
                    if k < len(self.error_bars):
                        self.error_bars[k].hide()
            else:
                # Display raw data (only valid, non-NaN points)
                self.curves[k].setData(valid_xs, valid_ys)
                if k < len(self.error_bars):
                    self.error_bars[k].hide()

import h5py  
from pandas.api.types import is_numeric_dtype
class ArrayDataCombo(ExtendedCombo):
    
    def __init__(self, h5_paths, **kwargs):
        
        super().__init__(**kwargs)
        self.update_model(h5_paths)
                
    def update_model(self, h5_paths):
        # Handle None or DataFrame-like h5_paths gracefully
        if h5_paths is None:
            h5_paths = []
        elif hasattr(h5_paths, 'filepath'):
            h5_paths = h5_paths.filepath.tolist()
        
        results_array_labels = set([])
        for h5_path in h5_paths:
            try:
                with h5py.File(h5_path, 'r') as h5_file:
                    if 'results' not in h5_file:
                        continue
                    analysis_names = h5_file['results'].keys()
                    
                    for analysis_name in analysis_names:
                        for key in h5_file['results'][analysis_name].keys():
                            results_array_labels.add(analysis_name+','+key)
            except Exception as e:
                import logging
                logging.debug(f"Could not read results from {h5_path}: {e}")
                continue
            
        
        model = QStandardItemModel()

        item = QStandardItem('shot number')
        model.setItem(0, 0, item)
        
        
        for i, idx in enumerate(results_array_labels, start=1):
            item = QStandardItem(idx)
            model.setItem(i, 0, item)
                
        self.setModel(model)
        
    def get_idx(self):
        return tuple(str(self.currentText()).split(','))

class QuickWaterfallPlot(QuickDataPlot):
    
    def __init__(self,*args,**kwargs):
        
        super().__init__(*args, **kwargs)
        
        self.img = pg.ImageItem()
        self.plot.addItem(self.img)
        
        
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
        
        self.img.translate(-0.5, -0.5)
        
        self.scalex = 1
        self.scaley = 1
        
        self.cx = 0
        self.cy = 0
        
        self.nplots = 0

        self.table.setColumnCount(3)
        self.table.setRowCount(2)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 150)
        self.table.setHorizontalHeaderLabels(['xvalue', 'yarray', 'zarray'])
        
        self.combox = NumericDataCombo(self.ap.df)
        self.comboy = ArrayDataCombo(self.ap.h5_paths)
        self.comboz = ArrayDataCombo(self.ap.h5_paths)
        
        self.table.setCellWidget(0, 0, self.combox)
        self.table.setCellWidget(0, 1, self.comboy)
        self.table.setCellWidget(0, 2, self.comboz)
        
        self.mk_buttons()      
            
    def mk_buttons(self):
        self.bt_update = QPushButton('Update', self)
        self.bt_update.clicked.connect(self.update_from_h5)
        self.table.setCellWidget(1, 1, self.bt_update)
        
    
    def update_combos(self, h5_paths):
        """Update combo models when h5_paths/df change"""
        try:
            self.combox.update_model(self.ap.df)
            self.comboy.update_model(h5_paths)
            self.comboz.update_model(h5_paths)
        except Exception as e:
            import logging
            logging.debug(f"Error updating combos: {e}")

    def update_data_extractor(self):
        
        idxx = self.combox.get_idx()
        idxy = self.comboy.get_idx()
        idxz = self.comboz.get_idx()
        
        if idxx not in self.data_extractor.data_extractors:
            if idxx[0] == 'shot number':
                self.data_extractor[idxx] = EmptyDataExtractor()
            else:
                self.data_extractor[idxx] = SingleDataExtractor(idxx)
        
        if idxy not in self.data_extractor.data_extractors:
            self.data_extractor[idxy] = ArrayDataExtractor(idxy)
            
        if idxz not in self.data_extractor.data_extractors:
            self.data_extractor[idxz] = ArrayDataExtractor(idxz)
        
        self.data_extractor.clean_children([idxx, idxy, idxz])
        self.clean_data_extractor_if_needed()
        
    def update(self, data = None):
        # Use lists instead of np.append which causes memory leaks
        xs_list = []
        ys_list = []
        zs_list = []
        
        idxx = self.combox.get_idx()
        idxy = self.comboy.get_idx()
        idxz = self.comboz.get_idx()
        
        # Use all h5_paths, not just selected ones
        h5_paths = self.get_all_h5_paths()
        
        for i, h5_path in enumerate(h5_paths):
            
            data = self.data_extractor.get_data(h5_path)[0]
            
            
            if idxx[0] == 'shot number':
                x = i
            else:
                x = data.get(idxx) if isinstance(data, dict) else None
            
            y = data.get(idxy) if isinstance(data, dict) else None
            z = data.get(idxz) if isinstance(data, dict) else None
            
            if x is None or not isinstance(x, (int, float, np.number)):
                continue
                
            if y is not None and z is not None:
                xs_list.extend(x * np.ones_like(y))
                ys_list.extend(np.asarray(y).flat)
                zs_list.extend(np.asarray(z).flat)
            elif y is not None:
                xs_list.extend(x * np.ones_like(y))
                ys_list.extend(np.asarray(y).flat)
                zs_list.extend(np.full_like(y, np.nan))
            elif z is not None:
                xs_list.extend(x * np.ones_like(z))
                ys_list.extend(np.full_like(z, np.nan))
                zs_list.extend(np.asarray(z).flat)
        
        # Convert lists to arrays after loop
        xs = np.array(xs_list, dtype=float)
        ys = np.array(ys_list, dtype=float)
        zs = np.array(zs_list, dtype=float)
           
        # Handle empty data
        if len(xs) == 0 or len(ys) == 0 or len(zs) == 0:
            return
            
        # here we don't want to assume that the data is on a grid
        # this can happen if the parameters where changed between two sweeps
        xi = np.linspace(xs.min(), xs.max(), 200)
        yi = np.linspace(ys.min(), ys.max(), 200)
        
        Xi, Yi = np.meshgrid(xi, yi)
        
        from scipy.interpolate import griddata
        
        Zi = griddata((xs,ys), zs, (Xi, Yi), 'nearest')
        
        # Clear large intermediate data after interpolation
        del xs, ys, zs, Xi, Yi
        
        
        
        
        self.img.setImage(Zi.T)
        self.iso.setData(Zi.T)  
        self.data_img = Zi
        
        # set position and scale of image
        newscalex = xi[1] - xi[0]
        newscaley = yi[1] - yi[0]
        
        transx = (xi[0] - (self.cx - 0.5 * self.scalex)) / newscalex - 0.5
        transy = (yi[0] - (self.cy - 0.5 * self.scaley)) / newscaley - 0.5
        
        self.img.scale(newscalex/self.scalex, newscaley/self.scaley)
        self.img.translate(transx,transy)
        
        self.scalex = newscalex
        self.scaley = newscaley
        
        self.cx = xi[0]
        self.cy = yi[0]
        
    def updateIsocurve(self):
        self.iso.setLevel(self.isoLine.value())
        
    def imageHoverEvent(self, event):
        """Show the position, pixel, and value under the mouse cursor.
        """
        if event.isExit():
            self.plot.setTitle("")
            return
        pos = event.pos()
        i, j = pos.y(), pos.x()
        i = int(np.clip(i, 0, self.data_img.shape[0] - 1))
        j = int(np.clip(j, 0, self.data_img.shape[1] - 1))
        val = self.data_img[i, j]
        ppos = self.img.mapToParent(pos)
        x, y = ppos.x(), ppos.y()
        self.plot.setTitle("pos: (%0.1f, %0.1f) value: %g" % (x, y, val))

class Quick2DPlot(QuickDataPlot):
    
    def __init__(self,*args, **kwargs):
        
        super().__init__(*args, **kwargs)
        
        self.img = pg.ImageItem()
        self.plot.addItem(self.img)
        
        
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
        
        self.img.translate(-0.5, -0.5)
        
        self.scalex = 1
        self.scaley = 1
        
        self.cx = 0
        self.cy = 0
        
        self.nplots = 0
        
        self.table.setColumnCount(3)
        self.table.setRowCount(2)
        self.table.setColumnWidth(0, 200)
        self.table.setColumnWidth(1, 150)
        self.table.setColumnWidth(2, 150)
        self.table.setHorizontalHeaderLabels(['xvalue', 'yarray', 'zarray'])
        
        self.combox = NumericDataCombo(self.ap.df)
        self.comboy = NumericDataCombo(self.ap.df)
        self.comboz = NumericDataCombo(self.ap.df)
        
        self.table.setCellWidget(0, 0, self.combox)
        self.table.setCellWidget(0, 1, self.comboy)
        self.table.setCellWidget(0, 2, self.comboz)
        
        self.mk_buttons()
            
    def mk_buttons(self):
        self.bt_update = QPushButton('Update', self)
        self.bt_update.clicked.connect(self.update_from_h5)
        self.table.setCellWidget(1, 1, self.bt_update)

    def update_combos(self, h5_paths):
        """Update numeric combo models when h5_paths/df change"""
        try:
            self.combox.update_model(self.ap.df)
            self.comboy.update_model(self.ap.df)
            self.comboz.update_model(self.ap.df)
        except Exception as e:
            import logging
            logging.debug(f"Error updating Quick2DPlot combos: {e}")

    def update_data_extractor(self):
        
        idxx = self.combox.get_idx()
        idxy = self.comboy.get_idx()
        idxz = self.comboz.get_idx()
        
        if idxx not in self.data_extractor.data_extractors:
            if idxx[0] == 'shot number':
                self.data_extractor[idxx] = EmptyDataExtractor()
            else:
                self.data_extractor[idxx] = SingleDataExtractor(idxx)   
                
        if idxy not in self.data_extractor.data_extractors:
            if idxy[0] == 'shot number':
                self.data_extractor[idxy] = EmptyDataExtractor()
            else:
                self.data_extractor[idxy] = SingleDataExtractor(idxy)  
        
        if idxz not in self.data_extractor.data_extractors:
            if idxz[0] == 'shot number':
                self.data_extractor[idxz] = EmptyDataExtractor()
            else:
                self.data_extractor[idxz] = SingleDataExtractor(idxz)
                
        self.data_extractor.clean_children([idxx, idxy, idxz])
        self.clean_data_extractor_if_needed()
        
    def update(self, murks = None):
        
        # Use lists instead of np.append which causes memory leaks
        xs_list = []
        ys_list = []
        zs_list = []
        
        idxx = self.combox.get_idx()
        idxy = self.comboy.get_idx()
        idxz = self.comboz.get_idx()
        
        # Use all h5_paths, not just selected ones
        h5_paths = self.get_all_h5_paths()
        
        for i, h5_path in enumerate(h5_paths):
            
            data = self.data_extractor.get_data(h5_path)[0]
            if idxx[0] == 'shot number':
                x_val = i
            else:
                x_val = data.get(idxx) if isinstance(data, dict) else None
            
            if idxy[0] == 'shot number':
                y_val = i
            else:
                y_val = data.get(idxy) if isinstance(data, dict) else None
            
            if idxz[0] == 'shot number':
                z_val = i
            else:
                z_val = data.get(idxz) if isinstance(data, dict) else None
            
            xs_list.append(x_val if x_val is not None else np.nan)
            ys_list.append(y_val if y_val is not None else np.nan)
            zs_list.append(z_val if z_val is not None else np.nan)
        
        # Convert lists to arrays after loop
        xs = np.array(xs_list, dtype=float)
        ys = np.array(ys_list, dtype=float)
        zs = np.array(zs_list, dtype=float)
        
        # Remove NaN values
        valid_mask = ~(np.isnan(xs) | np.isnan(ys) | np.isnan(zs))
        xs_valid = xs[valid_mask]
        ys_valid = ys[valid_mask]
        zs_valid = zs[valid_mask]
        
        if len(xs_valid) == 0 or len(ys_valid) == 0 or len(zs_valid) == 0:
            return
        
        # here we don't want to assume that the data is on a grid
        # this can happen if the parameters where changed between two sweeps
        
        xi = np.linspace(xs_valid.min(), xs_valid.max(), 200)
        yi = np.linspace(ys_valid.min(), ys_valid.max(), 200)
        
        Xi, Yi = np.meshgrid(xi, yi)
        
        from scipy.interpolate import griddata
        
        Zi = griddata((xs_valid, ys_valid), zs_valid, (Xi, Yi), 'nearest')
        
        # Clear large intermediate data after interpolation
        del xs_valid, ys_valid, zs_valid, Xi, Yi
        
        self.img.setImage(Zi.T)
        self.iso.setData(Zi.T)  
        self.data_img = Zi
        
        # set position and scale of image
        newscalex = xi[1] - xi[0]
        newscaley = yi[1] - yi[0]
        
        transx = (xi[0] - (self.cx - 0.5 * self.scalex)) / newscalex - 0.5
        transy = (yi[0] - (self.cy - 0.5 * self.scaley)) / newscaley - 0.5
        
        self.img.scale(newscalex/self.scalex, newscaley/self.scaley)
        self.img.translate(transx,transy)
        
        self.scalex = newscalex
        self.scaley = newscaley
        
        self.cx = xi[0]
        self.cy = yi[0]
        
        
        
        
    def updateIsocurve(self):
        self.iso.setLevel(self.isoLine.value())
        
    def imageHoverEvent(self, event):
        """Show the position, pixel, and value under the mouse cursor.
        """
        if event.isExit():
            self.plot.setTitle("")
            return
        pos = event.pos()
        i, j = pos.y(), pos.x()
        i = int(np.clip(i, 0, self.data_img.shape[0] - 1))
        j = int(np.clip(j, 0, self.data_img.shape[1] - 1))
        val = self.data_img[i, j]
        ppos = self.img.mapToParent(pos)
        x, y = ppos.x(), ppos.y()
        self.plot.setTitle("pos: (%0.1f, %0.1f) value: %g" % (x, y, val))
  
    
class QuickPlotGenerator(pg.LayoutWidget):
    
    def __init__(self, ap, **kwargs):
        super().__init__(**kwargs)
        
        self.ap = ap
        
        self.title = QLabel('<h2> Quick Plot Generator </h2>')
        
        self.addWidget(self.title,colspan = 2)
        
        self.nextRow()
        
        self.newlayout = pg.LayoutWidget()
        
        self.newlayout.addWidget(QLabel('Make new plot'))
        self.newlayout.nextRow()
        self.newlayout.addWidget(QLabel('Title: '))
        
        self.title_le = QLineEdit('murks')
        self.newlayout.addWidget(self.title_le)
        
        self.newlayout.nextRow()
        self.bt1d = QPushButton('make 1D plot', self)
        self.newlayout.addWidget(self.bt1d)
        
        self.bt1d.clicked.connect(self.mk1dplot)
        
        self.btwaterfall = QPushButton('make waterfall plot', self)
        self.newlayout.addWidget(self.btwaterfall)
        
        self.btwaterfall.clicked.connect(self.mkwaterfallplot)
        
        self.bt2d = QPushButton('make 2d plot', self)
        self.newlayout.addWidget(self.bt2d)
        
        self.bt2d.clicked.connect(self.mk2dplot)
        
        self.addWidget(self.newlayout)
        
    def mk1dplot (self):
        title = self.title_le.text()
        self.ap.add_plot_dock(title, Quick1DPlot(self.ap),  MultiDataExtractor(), closable = True)
        
    def mkwaterfallplot (self):
        title = self.title_le.text()
        self.ap.add_plot_dock(title, QuickWaterfallPlot(self.ap),  MultiDataExtractor(), closable = True)
        
    def mk2dplot (self):
        title = self.title_le.text()
        self.ap.add_plot_dock(title, Quick2DPlot(self.ap),  MultiDataExtractor(), closable = True)
        
        
        
        
        
        
        
        