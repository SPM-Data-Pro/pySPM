import matplotlib
matplotlib.use('QT5Agg')

from PyQt5.QtWidgets import QMainWindow, QShortcut, QApplication, QFileDialog, QSizePolicy, QTableWidgetItem
from PyQt5.QtCore import Qt, QSettings, QDir, QFileInfo
from pySPM.tools.spectraviewer import Ui_SpectraViewer
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import pySPM
import sys
import numpy as np
import os

DPI = 100.0
class SpectraViewer(QMainWindow):
    def __init__(self, filename=None, parent=None):
        super(SpectraViewer, self).__init__(parent)
        self.ui = Ui_SpectraViewer()
        self.ui.setupUi(self)
        self.sf = 7200
        self.k0 = 0
        self.dsf = 0
        self.dk0 = 0
        self.ita = None
        self.fig = Figure(figsize=(8,6), dpi=DPI)
        self.canvas = FigureCanvas(self.fig)
        self.canvas.setParent(self.ui.fig)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ui.fig.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.ui.fig.updateGeometry()
        self.canvas.updateGeometry()

        self.toolbar = NavigationToolbar(self.canvas, self.ui.fig)
        self.ax = self.fig.add_subplot(111)
        self.nextMass = QShortcut(Qt.Key_Plus, self)
        self.prevMass = QShortcut(Qt.Key_Minus, self)
        self.nextMass.activated.connect(self.next_mass)
        self.prevMass.activated.connect(self.prev_mass)
        self.ui.pushButton_2.clicked.connect(self.toggleMassCal)
        self.ui.pushButton.clicked.connect(self.removeMassCalItem)
        self.ui.show_mass.clicked.connect(self.yAxisScaleChanged)
        self.canvas.mpl_connect('motion_notify_event', self.on_motion)
        self.canvas.mpl_connect('button_press_event', self.onMousePress)
        self.canvas.mpl_connect('button_release_event', self.onMouseRelease)
        self.canvas.mpl_connect("scroll_event", self.scrolling)
        self.labels = []
        self.action = None
        self.lab_lines = []
        self.MassCal = []
        self.open(filename)

    def resizeEvent(self, event):
        return
        sx, sy = self.ui.fig.width()/DPI, self.ui.fig.height()/DPI
        self.fig.set_size_inches(sx, sy)
        self.ui.fig.updateGeometry()
        self.canvas.updateGeometry()
        self.canvas.draw()
        self.canvas.flush_events()

    def __del__(self):
        if self.ita is not None:
            del self.ita

    def removeMassCalItem(self):
        row = self.ui.tableMassCal.selectedItems()[0].row()
        del self.MassCal[row]
        self.DoMassCal()
    
    def refresh(self):
        r = self.ax.get_xlim()
        self.yAxisScaleChanged()
        self.canvas.draw()
        self.canvas.flush_events()

    def next_mass(self):
        r = self.ax.get_xlim()
        self.ax.set_xlim(r[0]+1, r[1]+1)
        self.refresh()

    def prev_mass(self):
        r = self.ax.get_xlim()
        self.ax.set_xlim(r[0]-1, r[1]-1)
        self.refresh()

    def clear_labels(self):
        for x in self.labels:
            x.remove()
        self.labels[:] = []
        for x in self.lab_lines:
            self.ax.lines.remove(x)
        self.lab_lines[:] = []

    def plot_labels(self, colors=['r','g','b']):
        r = self.ax.get_xlim()        
        E = []
        for nm in range(int(np.round(r[0],0)), int(np.round(r[1],0))+1):
            E += pySPM.utils.get_peaklist(nm, self.ita.polarity=='Negative')
        m0s = [pySPM.utils.get_mass(x) for x in E]
        P = list(zip(m0s, E))
        P.sort(key=lambda x: x[0])
        y = self.ax.get_ylim()[1]
        for i, (mi, Ei) in enumerate(P):
            col = colors[i%len(colors)]
            self.lab_lines.append(self.ax.axvline(mi, color=col, alpha=.5))
            self.labels.append(self.ax.annotate(Ei, (mi, y), (5, 0), rotation=90, va='top', ha='left', textcoords='offset pixels'))

    def yAxisScaleChanged(self):
        r = self.ax.get_xlim()
        delta = r[1]-r[0]
        self.clear_labels()     
        
        if self.ita is not None:
            SatLevel = self.ita.size['pixels']['x']*self.ita.size['pixels']['y']*self.ita.Nscan
            self.sat_level.set_ydata(SatLevel)
        
        max = 0
        left = int(pySPM.utils.mass2time(r[0], sf=self.sf, k0=self.k0)/2)
        right = int(pySPM.utils.mass2time(r[1], sf=self.sf, k0=self.k0)/2)+1
        if left<0:
            left = 0
        if right >= len(self.S):
            right = len(self.S)-1
        if left<self.t[-1] and right>0:
            max = np.max(self.S[left:right+1])
            self.ax.set_ylim(0, 1.2*max)
        if delta<10:
            self.ui.show_mass.setEnabled(True)
            if self.ui.show_mass.isChecked():
                self.plot_labels()
        else:
            self.ui.show_mass.setEnabled(False)
        m0 = pySPM.utils.time2mass(left+right, self.sf, self.k0)
        dm = 2*np.sqrt(m0)*np.sqrt((self.dk0**2/(self.sf**2))+m0*(self.dsf**2/(self.sf**2)))
        self.ui.lab_m0.setText("m0 = {:.5f} ± {:.5f}".format(m0,dm))

    def scrolling(self, event):
        r = self.ax.get_xlim()
        delta = (r[1]-r[0])
        m0 = event.xdata
        zfact = 2
        if event.button =="down":
            zfact = 1/zfact
        low = m0-(m0-r[0])*zfact
        high = m0+(r[1]-m0)*zfact
        self.ax.set_xlim((low, high))
        self.refresh()
            
    def open(self, t_filename=None):
        settings = QSettings(QSettings.IniFormat, QSettings.UserScope, "pySPM", "pySPM")
        if t_filename is None:
            home = QDir.cleanPath(os.getenv("HOMEPATH"))
            path = settings.value("lastPath", home)
            self.filename = QFileDialog.getOpenFileName(None, "Choose measurement file", path, "*.ita")
        else:
            self.filename = t_filename
        
        check_file = QFileInfo(self.filename)
        self.setWindowTitle(check_file.fileName())
        if not check_file.exists() or  not check_file.isFile():
            return
        
        settings.setValue("lastPath", check_file.path())
        self.ita = pySPM.ITA(self.filename)
        self.t, self.S = self.ita.getSpectrum(time=True)
        self.sf, self.k0 = self.ita.get_mass_cal()
        self.mass = pySPM.utils.time2mass(self.t, self.sf, self.k0)
        self.spec = self.ax.plot(self.mass, self.S)[0]
        SatLevel = self.ita.size['pixels']['x']*self.ita.size['pixels']['y']*self.ita.Nscan
        self.sat_level = self.ax.axhline(SatLevel, color='r')
        self.plotSpectra()
        
    def get_mass(self, formula):
        if self.ita is not None and not (formula.endsWith('+') or formula.endsWith('-')):
            if self.ita.polarity=='Negative':
                pol = "-"
            else:
                pol = "+"
            formula = formula + pol
        return pySPM.utils.get_mass(formula)    

    def plotSpectra(self):
        self.mass = pySPM.utils.time2mass(self.t, self.sf, self.k0)
        self.spec.set_xdata(self.mass)
        self.refresh()

    def onMousePress(self, event):
        if event.button == 3:
            x = event.xdata
            
            i = pySPM.utils.closest_arg(self.mass, x)
            last = i-1;
            while i!=last:
                last = i
                i = i-10+np.argmax(self.S[i-10:i+10])
            I = self.S[i]
            self.MassCal.append(dict(time=self.t[i]))
            print("clicked @{}u (t={})".format(x, self.t[i]))
        elif event.button == Qt.LeftButton:
            self.action = ('move', event.xdata)
        else:
            print(event)

    def on_motion(self, event):
        r = self.ax.get_xlim()
        if self.action is not None:
            if self.action[0] == 'move':
                if event.xdata is not None:
                    delta = r[1]-r[0]
                    dx = event.xdata-self.action[1]
                    self.ax.set_xlim((r[0]-dx,r[1]-dx))
                    self.refresh()

    def onMouseRelease(self, event):
        if event.button == 3:
            x = event.xdata
            NM = np.round(x, 0);
            frags = pySPM.utils.get_peaklist(NM, self.ita.polarity=='Negative')
            masses = np.array([pySPM.utils.get_mass(x) for x in frags])
            dm = masses-x
            i = np.argmin(np.abs(dm))
            self.MassCal[-1]['mass'] = masses[i]
            self.MassCal[-1]['elt'] = frags[i]
            print("assigned to {}".format(frags[i]))
            self.DoMassCal()
        self.action = None
        self.refresh()

    def DoMassCal(self):
        ts = [x['time'] for x in self.MassCal]
        ms = [x['mass'] for x in self.MassCal]
        if len(ts)>1:
            self.sf, self.k0, self.dsf, self.dk0 = pySPM.utils.fitSpectrum(ts, ms, error=True)
        else:
            self.k0 = ts[0]-self.sf*np.sqrt(ms[0])
            dsf = 0
            dk0 = 0
        self.ui.lab_k0.setText("k0 = {} ± {}".format(self.k0, self.dk0))
        self.ui.lab_sf.setText("sf = {} ± {}".format(self.sf, self.dsf))
        
        self.ita.setK0(self.k0)
        self.ita.setSF(self.sf)
        
        self.ui.tableMassCal.clearContents()
        self.ui.tableMassCal.setRowCount(len(self.MassCal))
        for i in range(len(self.MassCal)):
            self.ui.tableMassCal.setItem(i, 0, QTableWidgetItem(self.MassCal[i]['elt']))
            m = pySPM.utils.time2mass(self.MassCal[i]['time'], self.sf, self.k0)
            self.ui.tableMassCal.setItem(i, 1, QTableWidgetItem("{:.3f}".format(self.MassCal[i]['mass'])))
            self.ui.tableMassCal.setItem(i, 2, QTableWidgetItem("{:.0f}".format(self.MassCal[i]['time'])))
            delta = "{:.6f}".format(m-self.MassCal[i]['mass'])
            self.ui.tableMassCal.setItem(i, 3, QTableWidgetItem(delta)) 
        self.mass = pySPM.utils.time2mass(self.t, self.sf, self.k0)
        self.plotSpectra()
    
    def toggleMassCal(self):
        vis = not self.ui.tableMassCal.isVisible()
        self.ui.tableMassCal.setVisible(vis)
        self.ui.pushButton.setVisible(vis)
        if vis:
            self.ui.pushButton_2.setText("«")
        else:
            self.ui.pushButton_2.setText("»")
    
def main():
    filename = None
    if len(sys.argv)>1:
        filename = sys.argv[1]
    print("Loading file \"{}\"".format(filename))
    app = QApplication(sys.argv)
    window = SpectraViewer(filename)
    window.show()
    sys.exit(app.exec_())
    
if __name__ == '__main__':
    main()