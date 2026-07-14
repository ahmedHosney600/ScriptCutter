from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal
import pyqtgraph as pg

# Enable anti-aliasing globally for crisp waveform rendering on high-DPI displays (Mac Retina)
pg.setConfigOptions(antialias=True)

class MacSmoothPlotWidget(pg.PlotWidget):
    def wheelEvent(self, ev):
        import platform
        if platform.system() == "Darwin":
            # Trackpads on Mac send very high-resolution scroll events that cause chaotic zooming in pyqtgraph.
            # We ignore wheel events to prevent this. Users can use 'Fit to Screen' and 'Focus on Clip' buttons.
            ev.ignore()
        else:
            super().wheelEvent(ev)

class PlayheadLine(pg.InfiniteLine):
    def hoverEvent(self, ev):
        view = self.getViewBox()
        if view and not ev.isExit():
            y = view.mapSceneToView(ev.scenePos()).y()
            if y <= 1.0:
                self.setCursor(Qt.ArrowCursor)
                return
        super().hoverEvent(ev)

    def mouseClickEvent(self, ev):
        view = self.getViewBox()
        if view:
            click_y = view.mapSceneToView(ev.scenePos()).y()
            if click_y <= 1.0:
                ev.ignore()
                return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev):
        view = self.getViewBox()
        if view:
            click_y = view.mapSceneToView(ev.buttonDownScenePos()).y()
            if click_y <= 1.0:
                ev.ignore()
                return
        super().mouseDragEvent(ev)

class BoundaryLine(pg.InfiniteLine):
    def hoverEvent(self, ev):
        view = self.getViewBox()
        if view and not ev.isExit():
            y = view.mapSceneToView(ev.scenePos()).y()
            if y > 1.0:
                self.setCursor(Qt.ArrowCursor)
                return
        super().hoverEvent(ev)

    def mouseClickEvent(self, ev):
        view = self.getViewBox()
        if view:
            click_y = view.mapSceneToView(ev.scenePos()).y()
            if click_y > 1.0:
                ev.ignore()
                return
        super().mouseClickEvent(ev)

    def mouseDragEvent(self, ev):
        view = self.getViewBox()
        if view:
            click_y = view.mapSceneToView(ev.buttonDownScenePos()).y()
            if click_y > 1.0:
                ev.ignore()
                return
        super().mouseDragEvent(ev)

class TimelineWidget(QWidget):
    playhead_jumped = Signal(float) 
    bounds_changed = Signal(float, float) # Triggers visual cache update
    bounds_drag_finished = Signal(float, float) # Triggers undo stack commit

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.plot = MacSmoothPlotWidget()
        self.plot.setBackground('#2b2b2b')
        self.plot.showGrid(x=True, y=False, alpha=0.3)
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.hideAxis('left')
        layout.addWidget(self.plot)
        
        self.plot.scene().sigMouseClicked.connect(self.on_mouse_click)
        
        self.start_line = BoundaryLine(pos=0, angle=90, movable=True, pen=pg.mkPen('g', width=3))
        self.end_line = BoundaryLine(pos=5, angle=90, movable=True, pen=pg.mkPen('r', width=3))
        
        self.playhead = PlayheadLine(pos=0, angle=90, movable=True, pen=pg.mkPen('w', width=2))
        self.playhead.setZValue(10) 
        self.playhead.addMarker('v', position=1.0, size=15) 
        
        self.start_line.label = pg.InfLineLabel(self.start_line, text="{value:.2f}s", position=0.05, color='g')
        self.end_line.label = pg.InfLineLabel(self.end_line, text="{value:.2f}s", position=0.05, color='r')
        
        self.plot.addItem(self.start_line)
        self.plot.addItem(self.end_line)
        self.plot.addItem(self.playhead)
        
        self.start_line.sigPositionChanged.connect(self.enforce_bounds)
        self.end_line.sigPositionChanged.connect(self.enforce_bounds)
        
        self.start_line.sigPositionChangeFinished.connect(lambda *args: self.bounds_drag_finished.emit(self.start_line.value(), self.end_line.value()))
        self.end_line.sigPositionChangeFinished.connect(lambda *args: self.bounds_drag_finished.emit(self.start_line.value(), self.end_line.value()))
        
        self.waveform_top = None
        self.waveform_bottom = None
        self.waveform_fill = None
        self.total_duration = 0.1

    def on_mouse_click(self, event):
        if event.button() == Qt.RightButton:
            pos = event.scenePos()
            if self.plot.sceneBoundingRect().contains(pos):
                mouse_point = self.plot.plotItem.vb.mapSceneToView(pos)
                jump_time = max(0, min(self.total_duration, mouse_point.x()))
                self.set_playhead(jump_time)
                self.playhead_jumped.emit(jump_time)

    def enforce_bounds(self):
        start_val = self.start_line.value()
        end_val = self.end_line.value()
        if start_val >= end_val:
            if self.sender() == self.start_line:
                self.start_line.setValue(end_val - 0.05)
                start_val = end_val - 0.05
            elif self.sender() == self.end_line:
                self.end_line.setValue(start_val + 0.05)
                end_val = start_val + 0.05
                
        # Emit the new bounds every time you finish dragging!
        self.bounds_changed.emit(start_val, end_val)

    def set_waveform(self, peaks, total_duration):
        self.total_duration = total_duration
        
        if self.waveform_top: self.plot.removeItem(self.waveform_top)
        if self.waveform_bottom: self.plot.removeItem(self.waveform_bottom)
        if self.waveform_fill: self.plot.removeItem(self.waveform_fill)
            
        if not peaks or total_duration <= 0: return
        
        time_steps = [i * (total_duration / len(peaks)) for i in range(len(peaks))]
        neg_peaks = [-p for p in peaks] 
        
        wave_pen = pg.mkPen('#777777', width=1.5)
        self.waveform_top = self.plot.plot(x=time_steps, y=peaks, pen=wave_pen)
        self.waveform_bottom = self.plot.plot(x=time_steps, y=neg_peaks, pen=wave_pen)
        
        self.waveform_fill = pg.FillBetweenItem(self.waveform_bottom, self.waveform_top, brush=pg.mkBrush(130, 130, 130, 200))
        self.plot.addItem(self.waveform_fill)
        
        self.plot.setYRange(-1.0, 1.2) 
        self.plot.setLimits(xMin=0, xMax=total_duration, yMin=-1.0, yMax=1.2)

    def set_playhead(self, time):
        self.playhead.setValue(time)

    def set_clip_bounds(self, start, end):
        self.start_line.sigPositionChanged.disconnect(self.enforce_bounds)
        self.end_line.sigPositionChanged.disconnect(self.enforce_bounds)
        
        self.start_line.setValue(start)
        self.end_line.setValue(end)
        self.playhead.setValue(start)
        
        self.start_line.sigPositionChanged.connect(self.enforce_bounds)
        self.end_line.sigPositionChanged.connect(self.enforce_bounds)
        
        self.focus_on_clip()

    def focus_on_clip(self):
        start = self.start_line.value()
        end = self.end_line.value()
        padding = (end - start) * 0.2  
        self.plot.setXRange(max(0, start - padding), min(self.total_duration, end + padding))

    def fit_to_screen(self):
        if self.total_duration > 0:
            self.plot.setXRange(0, self.total_duration)