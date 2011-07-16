#! /usr/bin/python

# All QUISK software is Copyright (C) 2006-2011 by James C. Ahlstrom.
# This free software is licensed for use under the GNU General Public
# License (GPL), see http://www.opensource.org.
# Note that there is NO WARRANTY AT ALL.  USE AT YOUR OWN RISK!!

"""The main program for Quisk, a software defined radio.

Usage:  python quisk.py [-c | --config config_file_path]
This can also be installed as a package and run as quisk.main().
"""

# Change to the directory of quisk.py.  This is necessary to import Quisk packages
# and to load other extension modules that link against _quisk.so.  It also helps to
# find ./__init__.py and ./help.html.
import sys, os
os.chdir(os.path.normpath(os.path.dirname(__file__)))
if sys.path[0] != "'.'":		# Make sure the current working directory is on path
  sys.path.insert(0, '.')

import wx, wx.html, wx.lib.buttons, wx.lib.stattext, wx.lib.colourdb
import math, cmath, time, traceback
import threading, pickle, webbrowser
import _quisk as QS
from types import *
from quisk_widgets import *

# Command line parsing: be able to specify the config file.
from optparse import OptionParser
parser = OptionParser()
parser.add_option('-c', '--config', dest='config_file_path',
		help='Specify the configuration file path')
argv_options = parser.parse_args()[0]
ConfigPath = argv_options.config_file_path	# Get config file path
if not ConfigPath:	# Use default path
  if sys.platform == 'win32':
    path = os.getenv('HOMEDRIVE', '') + os.getenv('HOMEPATH', '')
    for dir in ("My Documents", "Eigene Dateien", "Documenti", "Documents"):
      ConfigPath = os.path.join(path, dir)
      if os.path.isdir(ConfigPath):
        break
    else:
      ConfigPath = os.path.join(path, "My Documents")
    ConfigPath = os.path.join(ConfigPath, "quisk_conf.py")
    if not os.path.isfile(ConfigPath):	# See if the user has a config file
      try:
        import shutil	# Try to create an initial default config file
        shutil.copyfile('quisk_conf_win.py', ConfigPath)
      except:
        pass
  else:
    ConfigPath = os.path.expanduser('~/.quisk_conf.py')

# These FFT sizes have multiple small factors, and are prefered for efficiency:
fftPreferedSizes = (416, 448, 480, 512, 576, 640, 672, 704, 768, 800, 832,
864, 896, 960, 1024, 1056, 1120, 1152, 1248, 1280, 1344, 1408, 1440, 1536,
1568, 1600, 1664, 1728, 1760, 1792, 1920, 2016, 2048, 2080, 2112, 2240, 2304,
2400, 2464, 2496, 2560, 2592, 2688, 2816, 2880, 2912)

def round(x):	# round float to nearest integer
  if x >= 0:
    return int(x + 0.5)
  else:
    return - int(-x + 0.5)

class Timer:
  """Debug: measure and print times every ptime seconds.

  Call with msg == '' to start timer, then with a msg to record the time.
  """
  def __init__(self, ptime = 1.0):
    self.ptime = ptime		# frequency to print in seconds
    self.time0 = 0			# time zero; measure from this time
    self.time_print = 0		# last time data was printed
    self.timers = {}		# one timer for each msg
    self.names = []			# ordered list of msg
    self.heading = 1		# print heading on first use
  def __call__(self, msg):
    tm = time.time()
    if msg:
      if not self.time0:		# Not recording data
        return
      if self.timers.has_key(msg):
        count, average, highest = self.timers[msg]
      else:
        self.names.append(msg)
        count = 0
        average = highest = 0.0
      count += 1
      delta = tm - self.time0
      average += delta
      if highest < delta:
        highest = delta
      self.timers[msg] = (count, average, highest)
      if tm - self.time_print > self.ptime:	# time to print results
        self.time0 = 0		# end data recording, wait for reset
        self.time_print = tm
        if self.heading:
          self.heading = 0
          print "count, msg, avg, max (msec)"
        print "%4d" % count,
        for msg in self.names:		# keep names in order
          count, average, highest = self.timers[msg]
          if not count:
            continue
          average /= count
          print "  %s  %7.3f  %7.3f" % (msg, average * 1e3, highest * 1e3),
          self.timers[msg] = (0, 0.0, 0.0)
        print
    else:	# reset the time to zero
      self.time0 = tm		# Start timer
      if not self.time_print:
        self.time_print = tm

## T = Timer()		# Make a timer instance

class SoundThread(threading.Thread):
  """Create a second (non-GUI) thread to read, process and play sound."""
  def __init__(self):
    self.do_init = 1
    threading.Thread.__init__(self)
    self.doQuit = threading.Event()
    self.doQuit.clear()
  def run(self):
    """Read, process, play sound; then notify the GUI thread to check for FFT data."""
    if self.do_init:	# Open sound using this thread
      self.do_init = 0
      QS.start_sound()
      wx.CallAfter(application.PostStartup)
    while not self.doQuit.isSet():
      QS.read_sound()
      wx.CallAfter(application.OnReadSound)
    QS.close_sound()
  def stop(self):
    """Set a flag to indicate that the sound thread should end."""
    self.doQuit.set()

class ConfigScreen(wx.ScrolledWindow):
  """Display the configuration and status screen."""
  def __init__(self, parent, width, fft_size):
    wx.ScrolledWindow.__init__(self, parent,
       pos = (0, 0),
       size = (width, 100),
       style = wx.VSCROLL | wx.NO_BORDER)
    self.SetBackgroundColour(conf.color_graph)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_SCROLLWIN, self.OnScroll)
    #self.Bind(wx.EVT_SCROLLWIN_THUMBRELEASE, self.OnScrollDone)
    self.Bind(wx.EVT_IDLE, self.OnScrollDone)
    self.width = width
    self.setscroll = True
    self.rx_phase = None
    self.fft_size = fft_size
    self.interupts = 0
    self.read_error = -1
    self.write_error = -1
    self.underrun_error = -1
    self.fft_error = -1
    self.latencyCapt = -1
    self.latencyPlay = -1
    self.y_scale = 0
    self.y_zero = 0
    self.rate_min = -1
    self.rate_max = -1
    self.chan_min = -1
    self.chan_max = -1
    self.mic_max_display = 0
    self.err_msg = "No response"
    self.msg1 = ""
    self.dev_capt, self.dev_play = QS.sound_devices()
    self.controls = []
    self.controls_visible = True
    self.tabstops = [0] * 9
    ts = self.tabstops
    points = 24
    while points > 4:
      self.font = wx.Font(points, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
      self.SetFont(self.font)
      charx = self.charx = self.GetCharWidth()
      chary = self.chary = self.GetCharHeight()
      ts[0] = charx
      w, h = self.GetTextExtent("Capture errors 99999")
      ts[1] = ts[0] + w
      ts[2] = ts[1] + charx * 2
      w, h = self.GetTextExtent("Capture latency 999999")
      ts[3] = ts[2] + w
      ts[4] = ts[3] + charx * 2
      w, h = self.GetTextExtent("Playback latency 999999")
      ts[5] = ts[4] + w
      ts[6] = ts[5] + charx * 2
      w, h = self.GetTextExtent("Total latency 999999")
      ts[7] = ts[6] + w
      ts[8] = ts[7] + charx * 2
      if ts[8] < width:
        break
      points -= 2
    self.dy = chary		# line spacing
    self.mem_height = self.dy * 4
    self.bitmap = wx.EmptyBitmap(width, self.mem_height)
    self.mem_rect = wx.Rect(0, 0, width, self.mem_height)
    self.mem_dc = wx.MemoryDC(self.bitmap)
    br = wx.Brush(conf.color_graph)
    self.mem_dc.SetBackground(br)
    self.mem_dc.SetFont(self.font)
    self.mem_dc.Clear()
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    dc.SetFont(self.font)
    dc.SetTextForeground('Black')
    x0 = self.tabstops[0]
    x, y = self.GetViewStart()
    self.y = -y
    # Make and blit variable data
    self.MakeBitmap()
    dc.Blit(0, self.y, self.width, self.mem_height, self.mem_dc, 0, 0)
    self.y += self.mem_height	# height of bitmap
    if conf.config_file_exists:
      t = "Using configuration file %s" % conf.config_file_path
    else:
      dc.SetTextForeground('Red')
      t = "Configuration file %s was not found" % conf.config_file_path
    dc.DrawText(t, x0, self.y)
    dc.SetTextForeground('Black')
    self.y += self.dy
    dc.DrawText(application.config_text, x0, self.y)
    self.y += self.dy
    if conf.name_of_sound_play:
      t = "Play rate %d to %s." % (conf.playback_rate,  conf.name_of_sound_play)
    else:
      t = "No playback device"
    dc.DrawText(t, x0, self.y)
    self.y += self.dy
    if conf.microphone_name:
      t = "Microphone sample rate %d from %s." % (conf.mic_sample_rate, conf.microphone_name)
      dc.DrawText(t, x0, self.y)
      self.y += self.dy
      if conf.name_of_mic_play:
        t = "Microphone playback rate %d to %s." % (conf.mic_playback_rate, conf.name_of_mic_play)
        dc.DrawText(t, x0, self.y)
        self.y += self.dy
    self.y += self.dy / 2
    if not self.rx_phase:
      # Make controls
      xxx = x0
      self.rx_phase = ph = wx.Button(self, -1, "Rx Phase...")
      self.Bind(wx.EVT_BUTTON, self.OnBtnPhase, ph)
      x1, y1 = ph.GetSizeTuple()
      ycenter = self.y + y1 / 2
      ph.SetPosition((x0, self.y))
      self.controls.append(ph)
      if conf.name_of_mic_play:
        self.tx_phase = ph = wx.Button(self, -1, "Tx Phase...")
        self.Bind(wx.EVT_BUTTON, self.OnBtnPhase, ph)
        ph.SetPosition((x0 + x1 * 12 / 10, self.y))
        self.controls.append(ph)
      xxx += x1 + self.charx * 4
      self.control_height = y1
      # Choice (combo) box for decimation
      lst = Hardware.VarDecimGetChoices()
      if lst:
        txt = Hardware.VarDecimGetLabel()
        t = wx.StaticText(self, -1, txt)
        x1, y1 = t.GetSizeTuple()
        t.SetPosition((xxx, ycenter - y1 / 2))
        self.controls.append(t)
        xxx += x1 + self.charx * 2
        c = wx.Choice(self, -1, choices=lst)
        x1, y1 = c.GetSizeTuple()
        c.SetPosition((xxx, ycenter - y1 / 2))
        self.controls.append(c)
        xxx += x1 + self.charx * 4
        self.Bind(wx.EVT_CHOICE, application.OnBtnDecimation, c)
        index = Hardware.VarDecimGetIndex()
        c.SetSelection(index)
    self.y += self.control_height + self.dy
    dc.DrawText("Available devices for capture:", x0, self.y)
    self.y += self.dy
    for name in self.dev_capt:
      dc.DrawText('    ' + name, x0, self.y)
      self.y += self.dy
    dc.DrawText("Available devices for playback:", x0, self.y)
    self.y += self.dy
    for name in self.dev_play:
      dc.DrawText('    ' + name, x0, self.y)
      self.y += self.dy
    self.y += self.dy
    # t = "Rx Phase..."
    # w, h = dc.GetTextExtent(t)
    # r = wx.Rect(x0, self.y, w + 10, h + 10)
    # dc.DrawRoundedRectangleRect(r, 4)
    # dc.DrawLabel(t, r, wx.ALIGN_CENTER)
    # self.y += h + 10
    if self.setscroll:	# Set the scroll size once
      self.setscroll = False
      self.height = self.y
      self.SetScrollbars(1, 1, self.width, self.height)
  def MakeRow2(self, dc, *args):
    for col in range(len(args)):
      x = self.tabstops[col]
      t = args[col]
      if t is not None:
        t = str(t)
        if col % 2 == 1:
          w, h = dc.GetTextExtent(t)
          x -= w
        dc.DrawText(t, x, self.mem_y)
    self.mem_y += self.dy
  def MakeBitmap(self):
    self.mem_dc.Clear()
    self.mem_y = 0
    self.MakeRow2(self.mem_dc, "Interrupts", self.interupts,
                "Capture latency", self.latencyCapt,
                "Playback latency", self.latencyPlay,
                "Total latency", self.latencyCapt + self.latencyPlay)
    self.MakeRow2(self.mem_dc, "Capture errors", self.read_error,
                "Playback errors", self.write_error,
                "Underrun errors", self.underrun_error,
                "FFT errors", self.fft_error)
    if conf.microphone_name:
      level = "%3.0f" % self.mic_max_display
    else:
      level = "None"
    self.MakeRow2(self.mem_dc, "Sample rate", application.sample_rate,
                 "Mic level dB", level,
                 None, None, "FFT points", self.fft_size)
    if self.err_msg:		# Error message on line 4
      x = self.tabstops[0]
      self.mem_dc.SetTextForeground('Red')
      self.mem_dc.DrawText(self.err_msg, x, self.mem_y)
      self.mem_dc.SetTextForeground('Black')
      self.mem_y += self.dy
  def OnGraphData(self, data=None):
    (self.rate_min, self.rate_max, sample_rate, self.chan_min, self.chan_max,
         self.msg1, self.unused, self.err_msg,
         self.read_error, self.write_error, self.underrun_error,
         self.latencyCapt, self.latencyPlay, self.interupts, self.fft_error, self.mic_max_display,
         self.data_poll_usec
	 ) = QS.get_state()
    self.mic_max_display = 20.0 * math.log10((self.mic_max_display + 1) / 32767.0)
    self.RefreshRect(self.mem_rect)
  def ChangeYscale(self, y_scale):
    pass
  def ChangeYzero(self, y_zero):
    pass
  def OnIdle(self, event):
    pass
  def SetTxFreq(self, tx_freq, rx_freq):
    pass
  def OnBtnPhase(self, event):
    btn = event.GetEventObject()
    if btn.GetLabel()[0:2] == 'Tx':
      rx_tx = 'tx'
    else:
      rx_tx = 'rx'
    application.screenBtnGroup.SetLabel('Graph', do_cmd=True)
    if application.w_phase:
      application.w_phase.Raise()
    else:
      application.w_phase = QAdjustPhase(self, self.width, rx_tx)
  def OnScroll(self, event):
  # Scrolling controls within this window works poorly, so we try
  # to hide the controls until scrolling is finished.
    event.Skip()
    if self.controls_visible:
      self.controls_visible = False
      for c in self.controls:
        c.Hide()
  def OnScrollDone(self, event):
    event.Skip()
    self.controls_visible = True
    for c in self.controls:
      c.Show()

class GraphDisplay(wx.Window):
  """Display the FFT graph within the graph screen."""
  def __init__(self, parent, x, y, graph_width, height, chary):
    wx.Window.__init__(self, parent,
       pos = (x, y),
       size = (graph_width, height),
       style = wx.NO_BORDER)
    self.parent = parent
    self.chary = chary
    self.graph_width = graph_width
    self.line = [(0, 0), (1,1)]		# initial fake graph data
    self.SetBackgroundColour(conf.color_graph)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_LEFT_DOWN, parent.OnLeftDown)
    self.Bind(wx.EVT_RIGHT_DOWN, parent.OnRightDown)
    self.Bind(wx.EVT_LEFT_UP, parent.OnLeftUp)
    self.Bind(wx.EVT_MOTION, parent.OnMotion)
    self.Bind(wx.EVT_MOUSEWHEEL, parent.OnWheel)
    self.tune_tx = graph_width / 2	# Current X position of the Tx tuning line
    self.tune_rx = 0				# Current X position of Rx tuning line or zero
    self.scale = 20				# pixels per 10 dB
    self.peak_hold = 9999		# time constant for holding peak value
    self.height = 10
    self.y_min = 1000
    self.y_max = 0
    self.max_height = application.screen_height
    self.tuningPenTx = wx.Pen('Red', 1)
    self.tuningPenRx = wx.Pen('Green', 1)
    self.backgroundPen = wx.Pen(self.GetBackgroundColour(), 1)
    self.horizPen = wx.Pen(conf.color_gl, 1, wx.SOLID)
    if sys.platform == 'win32':
      self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
  def OnEnter(self, event):
    if not application.w_phase:
      self.SetFocus()	# Set focus so we get mouse wheel events
  def OnPaint(self, event):
    #print 'GraphDisplay', self.GetUpdateRegion().GetBox()
    dc = wx.PaintDC(self)
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawLines(self.line)
    x = self.tune_tx
    dc.SetPen(self.tuningPenTx)
    dc.DrawLine(x, 0, x, self.max_height)
    if self.tune_rx:
      dc.SetPen(self.tuningPenRx)
      dc.DrawLine(self.tune_rx, 20, self.tune_rx, self.max_height)
    if not self.parent.in_splitter:
      dc.SetPen(self.horizPen)
      chary = self.chary
      y = self.zeroDB
      for i in range(0, -99999, -10):
        if y >= chary / 2:
          dc.DrawLine(0, y, self.graph_width, y)	# y line
        y = y + self.scale
        if y > self.height:
          break
  def SetHeight(self, height):
    self.height = height
    self.SetSize((self.graph_width, height))
  def OnGraphData(self, data):
    x = 0
    for y in data:	# y is in dB, -130 to 0
      y = self.zeroDB - int(y * self.scale / 10.0 + 0.5)
      try:
        y0 = self.line[x][1]
      except IndexError:
        self.line.append([x, y])
      else:
        if y > y0:
          y = min(y, y0 + self.peak_hold)
        self.line[x] = [x, y]
      x = x + 1
    self.Refresh()
  def XXOnGraphData(self, data):
    line = []
    x = 0
    y_min = 1000
    y_max = 0
    for y in data:	# y is in dB, -130 to 0
      y = self.zeroDB - int(y * self.scale / 10.0 + 0.5)
      if y > y_max:
        y_max = y
      if y < y_min:
        y_min = y
      line.append((x, y))
      x = x + 1
    ymax = max(y_max, self.y_max)
    ymin = min(y_min, self.y_min)
    rect = wx.Rect(0, ymin, 1000, ymax - ymin)
    self.y_min = y_min
    self.y_max = y_max
    self.line = line
    self.Refresh() #rect=rect)
  def SetTuningLine(self, tune_tx, tune_rx):
    dc = wx.ClientDC(self)
    dc.SetPen(self.backgroundPen)
    dc.DrawLine(self.tune_tx, 0, self.tune_tx, self.max_height)
    if self.tune_rx:
      dc.DrawLine(self.tune_rx, 0, self.tune_rx, self.max_height)
    dc.SetPen(self.tuningPenTx)
    dc.DrawLine(tune_tx, 0, tune_tx, self.max_height)
    if tune_rx:
      dc.SetPen(self.tuningPenRx)
      dc.DrawLine(tune_rx, 20, tune_rx, self.max_height)
    self.tune_tx = tune_tx
    self.tune_rx = tune_rx

class GraphScreen(wx.Window):
  """Display the graph screen X and Y axis, and create a graph display."""
  def __init__(self, parent, data_width, graph_width, in_splitter=0):
    wx.Window.__init__(self, parent, pos = (0, 0))
    self.in_splitter = in_splitter	# Are we in the top of a splitter window?
    if in_splitter:
      self.y_scale = conf.waterfall_graph_y_scale
      self.y_zero = conf.waterfall_graph_y_zero
    else:
      self.y_scale = conf.graph_y_scale
      self.y_zero = conf.graph_y_zero
    self.VFO = 0
    self.WheelMod = 50		# Round frequency when using mouse wheel
    self.txFreq = 0
    self.sample_rate = application.sample_rate
    self.zoom = 1.0
    self.zoom_deltaf = 0
    self.data_width = data_width
    self.graph_width = graph_width
    self.doResize = False
    self.pen_tick = wx.Pen("Black", 1, wx.SOLID)
    self.font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.SetFont(self.font)
    w = self.GetCharWidth() * 14 / 10
    h = self.GetCharHeight()
    self.charx = w
    self.chary = h
    self.tick = max(2, h * 3 / 10)
    self.originX = w * 5
    self.offsetY = h + self.tick
    self.width = self.originX + self.graph_width + self.tick + self.charx * 2
    self.height = application.screen_height * 3 / 10
    self.x0 = self.originX + self.graph_width / 2		# center of graph
    self.tuningX = self.x0
    self.originY = 10
    self.zeroDB = 10	# y location of zero dB; may be above the top of the graph
    self.scale = 10
    self.SetSize((self.width, self.height))
    self.SetSizeHints(self.width, 1, self.width)
    self.SetBackgroundColour(conf.color_graph)
    self.Bind(wx.EVT_SIZE, self.OnSize)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_LEFT_DOWN, self.OnLeftDown)
    self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
    self.Bind(wx.EVT_LEFT_UP, self.OnLeftUp)
    self.Bind(wx.EVT_MOTION, self.OnMotion)
    self.Bind(wx.EVT_MOUSEWHEEL, self.OnWheel)
    self.MakeDisplay()
  def MakeDisplay(self):
    self.display = GraphDisplay(self, self.originX, 0, self.graph_width, 5, self.chary)
    self.display.zeroDB = self.zeroDB
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    if not self.in_splitter:
      dc.SetFont(self.font)
      self.MakeYTicks(dc)
      self.MakeXTicks(dc)
  def OnIdle(self, event):
    if self.doResize:
      self.ResizeGraph()
  def OnSize(self, event):
    self.doResize = True
    event.Skip()
  def ResizeGraph(self):
    """Change the height of the graph.

    Changing the width interactively is not allowed because the FFT size is fixed.
    Call after changing the zero or scale to recalculate the X and Y axis marks.
    """
    w, h = self.GetClientSize()
    if self.in_splitter:	# Splitter window has no X axis scale
      self.height = h
      self.originY = h
    else:
      self.height = h - self.chary		# Leave space for X scale
      self.originY = self.height - self.offsetY
    self.MakeYScale()
    self.display.SetHeight(self.originY)
    self.display.scale = self.scale
    self.doResize = False
    self.Refresh()
  def ChangeYscale(self, y_scale):
    self.y_scale = y_scale
    self.doResize = True
  def ChangeYzero(self, y_zero):
    self.y_zero = y_zero
    self.doResize = True
  def ChangeZoom(self, zoom, deltaf):
    self.zoom = zoom
    self.zoom_deltaf = deltaf
    self.doResize = True
  def MakeYScale(self):
    chary = self.chary
    scale = (self.originY - chary)  * 10 / (self.y_scale + 20)	# Number of pixels per 10 dB
    scale = max(1, scale)
    q = (self.originY - chary ) / scale / 2
    zeroDB = chary + q * scale - self.y_zero * scale / 10
    if zeroDB > chary:
      zeroDB = chary
    self.scale = scale
    self.zeroDB = zeroDB
    self.display.zeroDB = self.zeroDB
    QS.record_graph(self.originX, self.zeroDB, self.scale)
  def MakeYTicks(self, dc):
    chary = self.chary
    x1 = self.originX - self.tick * 3	# left of tick mark
    x2 = self.originX - 1		# x location of y axis
    x3 = self.originX + self.graph_width	# end of graph data
    dc.SetPen(self.pen_tick)
    dc.DrawLine(x2, 0, x2, self.originY + 1)	# y axis
    y = self.zeroDB
    for i in range(0, -99999, -10):
      if y >= chary / 2:
        dc.SetPen(self.pen_tick)
        dc.DrawLine(x1, y, x2, y)	# y tick
        t = `i`
        w, h = dc.GetTextExtent(t)
        dc.DrawText(`i`, x1 - w, y - h / 2)		# y text
      y = y + self.scale
      if y > self.originY:
        break
  def MakeXTicks(self, dc):
    sample_rate = int(self.sample_rate * self.zoom)
    VFO = self.VFO + self.zoom_deltaf
    originY = self.originY
    x3 = self.originX + self.graph_width	# end of fft data
    charx , z = dc.GetTextExtent('-30000XX')
    tick0 = self.tick
    tick1 = tick0 * 2
    tick2 = tick0 * 3
    # Draw the X axis
    dc.SetPen(self.pen_tick)
    dc.DrawLine(self.originX, originY, x3, originY)
    # Draw the band plan colors below the X axis
    x = self.originX
    f = float(x - self.x0) * sample_rate / self.data_width
    c = None
    y = originY + 1
    for freq, color in conf.BandPlan:
      freq -= VFO
      if f < freq:
        xend = int(self.x0 + float(freq) * self.data_width / sample_rate + 0.5)
        if c is not None:
          dc.SetPen(wx.TRANSPARENT_PEN)
          dc.SetBrush(wx.Brush(c))
          dc.DrawRectangle(x, y, min(x3, xend) - x, tick0)  # x axis
        if xend >= x3:
          break
        x = xend
        f = freq
      c = color
    stick =  1000		# small tick in Hertz
    mtick =  5000		# medium tick
    ltick = 10000		# large tick
    # check the width of the frequency label versus frequency span
    df = charx * sample_rate / self.data_width
    if df < 1000:
      tfreq = 1000		# tick frequency for labels
    elif df < 5000:
      tfreq = 5000		# tick frequency for labels
    elif df < 10000:
      tfreq = 10000
    elif df < 20000:
      tfreq = 20000
    elif df < 50000:
      tfreq = 50000
      stick =  5000
      mtick = 10000
      ltick = 50000
    else:
      tfreq = 100000
      stick =  5000
      mtick = 10000
      ltick = 50000
    # Draw the X axis ticks and frequency in kHz
    dc.SetPen(self.pen_tick)
    freq1 = VFO - sample_rate / 2
    freq1 = (freq1 / stick) * stick
    freq2 = freq1 + sample_rate + stick + 1
    y_end = 0
    for f in range (freq1, freq2, stick):
      x = self.x0 + int(float(f - VFO) / sample_rate * self.data_width)
      if self.originX <= x <= x3:
        if f % ltick is 0:		# large tick
          dc.DrawLine(x, originY, x, originY + tick2)
        elif f % mtick is 0:	# medium tick
          dc.DrawLine(x, originY, x, originY + tick1)
        else:					# small tick
          dc.DrawLine(x, originY, x, originY + tick0)
        if f % tfreq is 0:		# place frequency label
          t = str(f/1000)
          w, h = dc.GetTextExtent(t)
          dc.DrawText(t, x - w / 2, originY + tick2)
          y_end = originY + tick2 + h
    if y_end:		# mark the center of the display
      dc.DrawLine(self.x0, y_end, self.x0, application.screen_height)
  def OnGraphData(self, data):
    i1 = (self.data_width - self.graph_width) / 2
    i2 = i1 + self.graph_width
    self.display.OnGraphData(data[i1:i2])
  def SetVFO(self, vfo):
    self.VFO = vfo
    self.doResize = True
  def SetTxFreq(self, tx_freq, rx_freq):
    sample_rate = int(self.sample_rate * self.zoom)
    self.txFreq = tx_freq
    tx_x = self.x0 + int(float(tx_freq - self.zoom_deltaf) / sample_rate * self.data_width)
    self.tuningX = tx_x
    rx_x = self.x0 + int(float(rx_freq - self.zoom_deltaf) / sample_rate * self.data_width)
    if abs(tx_x - rx_x) < 2:		# Do not display Rx line for small frequency offset
      self.display.SetTuningLine(tx_x - self.originX, 0)
    else:
      self.display.SetTuningLine(tx_x - self.originX, rx_x - self.originX)
  def GetMousePosition(self, event):
    """For mouse clicks in our display, translate to our screen coordinates."""
    mouse_x, mouse_y = event.GetPositionTuple()
    win = event.GetEventObject()
    if win is not self:
      x, y = win.GetPositionTuple()
      mouse_x += x
      mouse_y += y
    return mouse_x, mouse_y
  def OnRightDown(self, event):
    sample_rate = int(self.sample_rate * self.zoom)
    VFO = self.VFO + self.zoom_deltaf
    mouse_x, mouse_y = self.GetMousePosition(event)
    freq = float(mouse_x - self.x0) * sample_rate / self.data_width
    freq = int(freq)
    if VFO > 0:
      vfo = VFO + freq - self.zoom_deltaf
      if sample_rate > 40000:
        vfo = (vfo + 5000) / 10000 * 10000	# round to even number
      elif sample_rate > 5000:
        vfo = (vfo + 500) / 1000 * 1000
      else:
        vfo = (vfo + 50) / 100 * 100
      tune = freq + VFO - vfo
      self.ChangeHwFrequency(tune, vfo, 'MouseBtn3', event)
  def OnLeftDown(self, event):
    sample_rate = int(self.sample_rate * self.zoom)
    mouse_x, mouse_y = self.GetMousePosition(event)
    self.mouse_x = mouse_x
    x = mouse_x - self.originX
    if self.display.tune_rx and abs(x - self.display.tune_tx) > abs(x - self.display.tune_rx):
      self.mouse_is_rx = True
    else:
      self.mouse_is_rx = False
    if mouse_y < self.originY:		# click above X axis
      freq = float(mouse_x - self.x0) * sample_rate / self.data_width + self.zoom_deltaf
      freq = int(freq)
      if self.mouse_is_rx:
        application.rxFreq = freq
        application.screen.SetTxFreq(self.txFreq, freq)
        QS.set_tune(freq + application.ritFreq, self.txFreq)
      else:
        self.ChangeHwFrequency(freq, self.VFO, 'MouseBtn1', event)
    self.CaptureMouse()
  def OnLeftUp(self, event):
    if self.HasCapture():
      self.ReleaseMouse()
  def OnMotion(self, event):
    sample_rate = int(self.sample_rate * self.zoom)
    if event.Dragging() and event.LeftIsDown():
      mouse_x, mouse_y = self.GetMousePosition(event)
      if conf.mouse_tune_method:		# Mouse motion changes the VFO frequency
        x = (mouse_x - self.mouse_x)	# Thanks to VK6JBL
        self.mouse_x = mouse_x
        freq = x * sample_rate / self.data_width
        freq = int(freq)
        self.ChangeHwFrequency(self.txFreq, self.VFO - freq, 'MouseMotion', event)
      else:		# Mouse motion changes the tuning frequency
        # Frequency changes more rapidly for higher mouse Y position
        speed = max(10, self.originY - mouse_y) / float(self.originY)
        x = (mouse_x - self.mouse_x)
        self.mouse_x = mouse_x
        freq = speed * x * sample_rate / self.data_width
        freq = int(freq)
        if self.mouse_is_rx:	# Mouse motion changes the receive frequency
          application.rxFreq += freq
          application.screen.SetTxFreq(self.txFreq, application.rxFreq)
          QS.set_tune(application.rxFreq + application.ritFreq, self.txFreq)
        else:					# Mouse motion changes the transmit frequency
          self.ChangeHwFrequency(self.txFreq + freq, self.VFO, 'MouseMotion', event)
  def OnWheel(self, event):
    wm = self.WheelMod		# Round frequency when using mouse wheel
    mouse_x, mouse_y = self.GetMousePosition(event)
    x = mouse_x - self.originX
    if self.display.tune_rx and abs(x - self.display.tune_tx) > abs(x - self.display.tune_rx):
      tune = application.rxFreq + wm * event.GetWheelRotation() / event.GetWheelDelta()
      if tune >= 0:
        tune = tune / wm * wm
      else:		# tune can be negative when the VFO is zero
        tune = - (- tune / wm * wm)
      application.rxFreq = tune
      application.screen.SetTxFreq(self.txFreq, tune)
      QS.set_tune(tune + application.ritFreq, self.txFreq)
    else:
      tune = self.txFreq + wm * event.GetWheelRotation() / event.GetWheelDelta()
      if tune >= 0:
        tune = tune / wm * wm
      else:		# tune can be negative when the VFO is zero
        tune = - (- tune / wm * wm)
      self.ChangeHwFrequency(tune, self.VFO, 'MouseWheel', event)
  def ChangeHwFrequency(self, tune, vfo, source, event):
    application.ChangeHwFrequency(tune, vfo, source, event)
  def PeakHold(self, name):
    if name == 'GraphP1':
      self.display.peak_hold = int(self.display.scale * conf.graph_peak_hold_1)
    elif name == 'GraphP2':
      self.display.peak_hold = int(self.display.scale * conf.graph_peak_hold_2)
    else:
      self.display.peak_hold = 9999
    if self.display.peak_hold < 1:
      self.display.peak_hold = 1

class WaterfallDisplay(wx.Window):
  """Create a waterfall display within the waterfall screen."""
  def __init__(self, parent, x, y, graph_width, height, margin):
    wx.Window.__init__(self, parent,
       pos = (x, y),
       size = (graph_width, height),
       style = wx.NO_BORDER)
    self.parent = parent
    self.graph_width = graph_width
    self.margin = margin
    self.height = 10
    self.sample_rate = application.sample_rate
    self.SetBackgroundColour('Black')
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.Bind(wx.EVT_LEFT_DOWN, parent.OnLeftDown)
    self.Bind(wx.EVT_RIGHT_DOWN, parent.OnRightDown)
    self.Bind(wx.EVT_LEFT_UP, parent.OnLeftUp)
    self.Bind(wx.EVT_MOTION, parent.OnMotion)
    self.Bind(wx.EVT_MOUSEWHEEL, parent.OnWheel)
    self.tune_tx = graph_width / 2	# Current X position of the Tx tuning line
    self.tune_rx = 0				# Current X position of Rx tuning line or zero
    self.tuningPen = wx.Pen('White', 3)
    self.marginPen = wx.Pen(conf.color_graph, 1)
    # Size of top faster scroll region is (top_key + 2) * (top_key - 1) / 2
    self.top_key = 8
    self.top_size = (self.top_key + 2) * (self.top_key - 1) / 2
    # Make the palette
    pal2 = conf.waterfallPalette
    red = []
    green = []
    blue = []
    n = 0
    for i in range(256):
      if i > pal2[n+1][0]:
         n = n + 1
      red.append((i - pal2[n][0]) *
       (long)(pal2[n+1][1] - pal2[n][1]) /
       (long)(pal2[n+1][0] - pal2[n][0]) + pal2[n][1])
      green.append((i - pal2[n][0]) *
       (long)(pal2[n+1][2] - pal2[n][2]) /
       (long)(pal2[n+1][0] - pal2[n][0]) + pal2[n][2])
      blue.append((i - pal2[n][0]) *
       (long)(pal2[n+1][3] - pal2[n][3]) /
       (long)(pal2[n+1][0] - pal2[n][0]) + pal2[n][3])
    self.red = red
    self.green = green
    self.blue = blue
    bmp = wx.EmptyBitmap(0, 0)
    bmp.x_origin = 0
    self.bitmaps = [bmp] * application.screen_height
    if sys.platform == 'win32':
      self.Bind(wx.EVT_ENTER_WINDOW, self.OnEnter)
  def OnEnter(self, event):
    if not application.w_phase:
      self.SetFocus()	# Set focus so we get mouse wheel events
  def OnPaint(self, event):
    dc = wx.BufferedPaintDC(self)
    dc.SetBackground(wx.Brush('Black'))
    dc.Clear()
    y = 0
    dc.SetPen(self.marginPen)
    x_origin = int(float(self.VFO) / self.sample_rate * self.data_width + 0.5)
    for i in range(0, self.margin):
      dc.DrawLine(0, y, self.graph_width, y)
      y += 1
    index = 0
    if conf.waterfall_scroll_mode:	# Draw the first few lines multiple times
      for i in range(self.top_key, 1, -1):
        b = self.bitmaps[index]
        x = b.x_origin - x_origin
        for j in range(0, i):
          dc.DrawBitmap(b, x, y)
          y += 1
        index += 1
    while y < self.height:
      b = self.bitmaps[index]
      x = b.x_origin - x_origin
      dc.DrawBitmap(b, x, y)
      y += 1
      index += 1
    dc.SetPen(self.tuningPen)
    dc.SetLogicalFunction(wx.XOR)
    dc.DrawLine(self.tune_tx, 0, self.tune_tx, self.height)
    if self.tune_rx:
      dc.DrawLine(self.tune_rx, 0, self.tune_rx, self.height)
  def SetHeight(self, height):
    self.height = height
    self.SetSize((self.graph_width, height))
  def OnGraphData(self, data, y_zero, y_scale):
    #T('graph start')
    row = ''		# Make a new row of pixels for a one-line image
    for x in data:	# x is -130 to 0, or so (dB)
      l = int((x + y_zero / 3 + 100) * y_scale / 10)
      l = max(l, 0)
      l = min(l, 255)
      row = row + "%c%c%c" % (chr(self.red[l]), chr(self.green[l]), chr(self.blue[l]))
    #T('graph string')
    bmp = wx.BitmapFromBuffer(len(row) / 3, 1, row)
    bmp.x_origin = int(float(self.VFO) / self.sample_rate * self.data_width + 0.5)
    self.bitmaps.insert(0, bmp)
    del self.bitmaps[-1]
    #self.ScrollWindow(0, 1, None)
    #self.Refresh(False, (0, 0, self.graph_width, self.top_size + self.margin))
    self.Refresh(False)
    #T('graph end')
  def SetTuningLine(self, tune_tx, tune_rx):
    dc = wx.ClientDC(self)
    dc.SetPen(self.tuningPen)
    dc.SetLogicalFunction(wx.XOR)
    dc.DrawLine(self.tune_tx, 0, self.tune_tx, self.height)
    if self.tune_rx:
      dc.DrawLine(self.tune_rx, 0, self.tune_rx, self.height)
    dc.DrawLine(tune_tx, 0, tune_tx, self.height)
    if tune_rx:
      dc.DrawLine(tune_rx, 0, tune_rx, self.height)
    self.tune_tx = tune_tx
    self.tune_rx = tune_rx
  def ChangeZoom(self, zoom, zoom_deltaf):
    pass

class WaterfallScreen(wx.SplitterWindow):
  """Create a splitter window with a graph screen and a waterfall screen"""
  def __init__(self, frame, width, data_width, graph_width):
    self.y_scale = conf.waterfall_y_scale
    self.y_zero = conf.waterfall_y_zero
    wx.SplitterWindow.__init__(self, frame)
    self.SetSizeHints(width, -1, width)
    self.SetMinimumPaneSize(1)
    self.SetSize((width, conf.waterfall_graph_size + 100))	# be able to set sash size
    self.pane1 = GraphScreen(self, data_width, graph_width, 1)
    self.pane2 = WaterfallPane(self, data_width, graph_width)
    self.SplitHorizontally(self.pane1, self.pane2, conf.waterfall_graph_size)
  def OnIdle(self, event):
    self.pane1.OnIdle(event)
    self.pane2.OnIdle(event)
  def SetTxFreq(self, tx_freq, rx_freq):
    self.pane1.SetTxFreq(tx_freq, rx_freq)
    self.pane2.SetTxFreq(tx_freq, rx_freq)
  def SetVFO(self, vfo):
    self.pane1.SetVFO(vfo)
    self.pane2.SetVFO(vfo) 
  def ChangeYscale(self, y_scale):		# Test if the shift key is down
    if wx.GetKeyState(wx.WXK_SHIFT):	# Set graph screen
      self.pane1.ChangeYscale(y_scale)
    else:			# Set waterfall screen
      self.y_scale = y_scale
      self.pane2.ChangeYscale(y_scale)
  def ChangeYzero(self, y_zero):		# Test if the shift key is down
    if wx.GetKeyState(wx.WXK_SHIFT):	# Set graph screen
      self.pane1.ChangeYzero(y_zero)
    else:			# Set waterfall screen
      self.y_zero = y_zero
      self.pane2.ChangeYzero(y_zero)
  def OnGraphData(self, data):
    self.pane1.OnGraphData(data)
    self.pane2.OnGraphData(data)

class WaterfallPane(GraphScreen):
  """Create a waterfall screen with an X axis and a waterfall display."""
  def __init__(self, frame, data_width, graph_width):
    GraphScreen.__init__(self, frame, data_width, graph_width)
    self.y_scale = conf.waterfall_y_scale
    self.y_zero = conf.waterfall_y_zero
    self.oldVFO = self.VFO
  def MakeDisplay(self):
    self.display = WaterfallDisplay(self, self.originX, 0, self.graph_width, 5, self.chary)
    self.display.VFO = self.VFO
    self.display.data_width = self.data_width
  def SetVFO(self, vfo):
    GraphScreen.SetVFO(self, vfo)
    self.display.VFO = vfo
    if self.oldVFO != vfo:
      self.oldVFO = vfo
      self.Refresh()
  def MakeYTicks(self, dc):
    pass
  def ChangeYscale(self, y_scale):
    self.y_scale = y_scale
  def ChangeYzero(self, y_zero):
    self.y_zero = y_zero
  def OnGraphData(self, data):
    i1 = (self.data_width - self.graph_width) / 2
    i2 = i1 + self.graph_width
    self.display.OnGraphData(data[i1:i2], self.y_zero, self.y_scale)

class ScopeScreen(wx.Window):
  """Create an oscilloscope screen (mostly used for debug)."""
  def __init__(self, parent, width, data_width, graph_width):
    wx.Window.__init__(self, parent, pos = (0, 0),
       size=(width, -1), style = wx.NO_BORDER)
    self.SetBackgroundColour(conf.color_graph)
    self.font = wx.Font(16, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.SetFont(self.font)
    self.Bind(wx.EVT_SIZE, self.OnSize)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    self.horizPen = wx.Pen(conf.color_gl, 1, wx.SOLID)
    self.y_scale = conf.scope_y_scale
    self.y_zero = conf.scope_y_zero
    self.running = 1
    self.doResize = False
    self.width = width
    self.height = 100
    self.originY = self.height / 2
    self.data_width = data_width
    self.graph_width = graph_width
    w = self.charx = self.GetCharWidth()
    h = self.chary = self.GetCharHeight()
    tick = max(2, h * 3 / 10)
    self.originX = w * 3
    self.width = self.originX + self.graph_width + tick + self.charx * 2
    self.line = [(0,0), (1,1)]	# initial fake graph data
    self.fpout = None #open("jim96.txt", "w")
  def OnIdle(self, event):
    if self.doResize:
      self.ResizeGraph()
  def OnSize(self, event):
    self.doResize = True
    event.Skip()
  def ResizeGraph(self, event=None):
    # Change the height of the graph.  Changing the width interactively is not allowed.
    w, h = self.GetClientSize()
    self.height = h
    self.originY = h / 2
    self.doResize = False
    self.Refresh()
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    dc.SetFont(self.font)
    self.MakeYTicks(dc)
    self.MakeXTicks(dc)
    self.MakeText(dc)
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawLines(self.line)
  def MakeYTicks(self, dc):
    chary = self.chary
    originX = self.originX
    x3 = self.x3 = originX + self.graph_width	# end of graph data
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawLine(originX, 0, originX, self.originY * 3)	# y axis
    # Find the size of the Y scale markings
    themax = 2.5e9 * 10.0 ** - ((160 - self.y_scale) / 50.0)	# value at top of screen
    themax = int(themax)
    l = []
    for j in (5, 6, 7, 8):
      for i in (1, 2, 5):
        l.append(i * 10 ** j)
    for yvalue in l:
      n = themax / yvalue + 1			# Number of lines
      ypixels = self.height / n
      if n < 20:
        break
    dc.SetPen(self.horizPen)
    for i in range(1, 1000):
      y = self.originY - ypixels * i
      if y < chary:
        break
      # Above axis
      dc.DrawLine(originX, y, x3, y)	# y line
      # Below axis
      y = self.originY + ypixels * i
      dc.DrawLine(originX, y, x3, y)	# y line
    self.yscale = float(ypixels) / yvalue
    self.yvalue = yvalue
  def MakeXTicks(self, dc):
    originY = self.originY
    x3 = self.x3
    # Draw the X axis
    dc.SetPen(wx.BLACK_PEN)
    dc.DrawLine(self.originX, originY, x3, originY)
    # Find the size of the X scale markings in microseconds
    for i in (20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000):
      xscale = i			# X scale in microseconds
      if application.sample_rate * xscale * 0.000001 > self.width / 30:
        break
    # Draw the X lines
    dc.SetPen(self.horizPen)
    for i in range(1, 999):
      x = int(self.originX + application.sample_rate * xscale * 0.000001 * i + 0.5)
      if x > x3:
        break
      dc.DrawLine(x, 0, x, self.height)	# x line
    self.xscale = xscale
  def MakeText(self, dc):
    if self.running:
      t = "   RUN"
    else:
      t = "   STOP"
    if self.xscale >= 1000:
      t = "%s    X: %d millisec/div" % (t, self.xscale / 1000)
    else:
      t = "%s    X: %d microsec/div" % (t, self.xscale)
    t = "%s   Y: %.0E/div" % (t, self.yvalue)
    dc.DrawText(t, self.originX, self.height - self.chary)
  def OnGraphData(self, data):
    if not self.running:
      if self.fpout:
        for cpx in data:
          re = int(cpx.real)
          im = int(cpx.imag)
          ab = int(abs(cpx))
          ph = math.atan2(im, re) * 360. / (2.0 * math.pi)
          self.fpout.write("%12d %12d %12d %12.1d\n" % (re, im, ab, ph))
      return		# Preserve data on screen
    line = []
    x = self.originX
    ymax = self.height
    for cpx in data:	# cpx is complex raw samples +/- 0 to 2**31-1
      y = cpx.real
      #y = abs(cpx)
      y = self.originY - int(y * self.yscale + 0.5)
      if y > ymax:
        y = ymax
      elif y < 0:
        y = 0
      line.append((x, y))
      x = x + 1
    self.line = line
    self.Refresh()
  def ChangeYscale(self, y_scale):
    self.y_scale = y_scale
    self.doResize = True
  def ChangeYzero(self, y_zero):
    self.y_zero = y_zero
  def SetTxFreq(self, tx_freq, rx_freq):
    pass

class FilterScreen(GraphScreen):
  """Create a graph of the receive filter response."""
  def __init__(self, parent, data_width, graph_width):
    GraphScreen.__init__(self, parent, data_width, graph_width)
    self.y_scale = conf.filter_y_scale
    self.y_zero = conf.filter_y_zero
    self.VFO = 0
    self.txFreq = 0
    self.data = []
    self.sample_rate = QS.get_filter_rate()
  def NewFilter(self):
    self.data = QS.get_filter()
    #self.data = QS.get_tx_filter()
  def OnGraphData(self, data):
    GraphScreen.OnGraphData(self, self.data)
  def ChangeHwFrequency(self, tune, vfo, source, event):
    GraphScreen.SetTxFreq(self, tune, tune)
    application.freqDisplay.Display(tune)
  def SetTxFreq(self, tx_freq, rx_freq):
    pass

class HelpScreen(wx.html.HtmlWindow):
  """Create the screen for the Help button."""
  def __init__(self, parent, width, height):
    wx.html.HtmlWindow.__init__(self, parent, -1, size=(width, height))
    self.y_scale = 0
    self.y_zero = 0
    if "gtk2" in wx.PlatformInfo:
      self.SetStandardFonts()
    self.SetFonts("", "", [10, 12, 14, 16, 18, 20, 22])
    # read in text from file help.html in the directory of this module
    self.LoadFile('help.html')
  def OnGraphData(self, data):
    pass
  def ChangeYscale(self, y_scale):
    pass
  def ChangeYzero(self, y_zero):
    pass
  def OnIdle(self, event):
    pass
  def SetTxFreq(self, tx_freq, rx_freq):
    pass
  def OnLinkClicked(self, link):
    webbrowser.open(link.GetHref(), new=2)

class QMainFrame(wx.Frame):
  """Create the main top-level window."""
  def __init__(self, width, height):
    fp = open('__init__.py')		# Read in the title
    title = fp.readline().strip()[1:]
    fp.close()
    wx.Frame.__init__(self, None, -1, title, wx.DefaultPosition,
        (width, height), wx.DEFAULT_FRAME_STYLE, 'MainFrame')
    self.SetBackgroundColour(conf.color_bg)
    self.Bind(wx.EVT_CLOSE, self.OnBtnClose)
  def OnBtnClose(self, event):
    application.OnBtnClose(event)
    self.Destroy()

## Note: The new amplitude/phase adjustments have ideas provided by Andrew Nilsson, VK6JBL
class QAdjustPhase(wx.Frame):
  """Create a window with amplitude and phase adjustment controls"""
  f_ampl = "Amplitude adjustment %.6f"
  f_phase = "Phase adjustment degrees %.6f"
  def __init__(self, parent, width, rx_tx):
    self.rx_tx = rx_tx		# Must be "rx" or "tx"
    if rx_tx == 'tx':
      self.is_tx = 1
      t = "Adjust Sound Card Transmit Amplitude and Phase"
    else:
      self.is_tx = 0
      t = "Adjust Sound Card Receive Amplitude and Phase"
    wx.Frame.__init__(self, application.main_frame, -1, t, pos=(50, 100), style=wx.CAPTION)
    panel = wx.Panel(self)
    self.MakeControls(panel, width)
    self.Show()
  def MakeControls(self, panel, width):		# Make controls for phase/amplitude adjustment
    self.old_amplitude, self.old_phase = application.GetAmplPhase(self.is_tx)
    self.new_amplitude, self.new_phase = self.old_amplitude, self.old_phase
    sl_max = width * 4 / 10		# maximum +/- value for slider
    self.ampl_scale = float(conf.rx_max_amplitude_correct) / sl_max
    self.phase_scale = float(conf.rx_max_phase_correct) / sl_max
    font = wx.Font(12, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    chary = self.GetCharHeight()
    y = chary * 3 / 10
    # Print available data points
    if conf.bandAmplPhase.has_key("panadapter"):
      self.band = "panadapter"
    else:
      self.band = application.lastBand
    app_vfo = (application.VFO + 500) / 1000
    ap = application.bandAmplPhase
    if not ap.has_key(self.band):
      ap[self.band] = {}
    if not ap[self.band].has_key(self.rx_tx):
      ap[self.band][self.rx_tx] = []
    lst = ap[self.band][self.rx_tx]
    freq_in_list = False
    if lst:
      t = "Band %s: VFO" % self.band
      for l in lst:
        vfo = (l[0] + 500) / 1000
        if vfo == app_vfo:
          freq_in_list = True
        t = t + (" %d" % vfo)
    else:
      t = "Band %s: No data." % self.band
    txt = wx.StaticText(panel, -1, t, pos=(0, y))
    txt.SetFont(font)
    y += txt.GetSizeTuple()[1]
    self.t_ampl = wx.StaticText(panel, -1, self.f_ampl % self.old_amplitude, pos=(0, y))
    self.t_ampl.SetFont(font)
    y += self.t_ampl.GetSizeTuple()[1]
    self.ampl1 = wx.Slider(panel, -1, 0, -sl_max, sl_max,
      pos=(0, y), size=(width, -1))
    y += self.ampl1.GetSizeTuple()[1]
    self.ampl2 = wx.Slider(panel, -1, 0, -sl_max, sl_max,
      pos=(0, y), size=(width, -1))
    y += self.ampl2.GetSizeTuple()[1]
    self.PosAmpl(self.old_amplitude)
    self.t_phase = wx.StaticText(panel, -1, self.f_phase % self.old_phase, pos=(0, y))
    self.t_phase.SetFont(font)
    y += self.t_phase.GetSizeTuple()[1]
    self.phase1 = wx.Slider(panel, -1, 0, -sl_max, sl_max,
      pos=(0, y), size=(width, -1))
    y += self.phase1.GetSizeTuple()[1]
    self.phase2 = wx.Slider(panel, -1, 0, -sl_max, sl_max,
      pos=(0, y), size=(width, -1))
    y += self.phase2.GetSizeTuple()[1]
    sv = QuiskPushbutton(panel, self.OnBtnSave, 'Save %d' % app_vfo)
    ds = QuiskPushbutton(panel, self.OnBtnDiscard, 'Destroy %d' % app_vfo)
    cn = QuiskPushbutton(panel, self.OnBtnCancel, 'Cancel')
    w, h = ds.GetSizeTuple()
    sv.SetSize((w, h))
    cn.SetSize((w, h))
    y += h / 4
    x = (width - w * 3) / 4
    sv.SetPosition((x, y))
    ds.SetPosition((x*2 + w, y))
    cn.SetPosition((x*3 + w*2, y))
    sv.SetBackgroundColour('light blue')
    ds.SetBackgroundColour('light blue')
    cn.SetBackgroundColour('light blue')
    if not freq_in_list:
      ds.Disable()
    y += h
    y += h / 4
    self.ampl1.SetBackgroundColour('aquamarine')
    self.ampl2.SetBackgroundColour('orange')
    self.phase1.SetBackgroundColour('aquamarine')
    self.phase2.SetBackgroundColour('orange')
    self.PosPhase(self.old_phase)
    self.SetClientSizeWH(width, y)
    self.ampl1.Bind(wx.EVT_SCROLL, self.OnChange)
    self.ampl2.Bind(wx.EVT_SCROLL, self.OnAmpl2)
    self.phase1.Bind(wx.EVT_SCROLL, self.OnChange)
    self.phase2.Bind(wx.EVT_SCROLL, self.OnPhase2)
  def PosAmpl(self, ampl):	# set pos1, pos2 for amplitude
    pos2 = round(ampl / self.ampl_scale)
    remain = ampl - pos2 * self.ampl_scale
    pos1 = round(remain / self.ampl_scale * 50.0)
    self.ampl1.SetValue(pos1)
    self.ampl2.SetValue(pos2)
  def PosPhase(self, phase):	# set pos1, pos2 for phase
    pos2 = round(phase / self.phase_scale)
    remain = phase - pos2 * self.phase_scale
    pos1 = round(remain / self.phase_scale * 50.0)
    self.phase1.SetValue(pos1)
    self.phase2.SetValue(pos2)
  def OnChange(self, event):
    ampl = self.ampl_scale * self.ampl1.GetValue() / 50.0 + self.ampl_scale * self.ampl2.GetValue()
    if abs(ampl) < self.ampl_scale * 3.0 / 50.0:
      ampl = 0.0
    self.t_ampl.SetLabel(self.f_ampl % ampl)
    phase = self.phase_scale * self.phase1.GetValue() / 50.0 + self.phase_scale * self.phase2.GetValue()
    if abs(phase) < self.phase_scale * 3.0 / 50.0:
      phase = 0.0
    self.t_phase.SetLabel(self.f_phase % phase)
    QS.set_ampl_phase(ampl, phase, self.is_tx)
    self.new_amplitude, self.new_phase = ampl, phase
  def OnAmpl2(self, event):		# re-center the fine slider when the coarse slider is adjusted
    ampl = self.ampl_scale * self.ampl1.GetValue() / 50.0 + self.ampl_scale * self.ampl2.GetValue()
    self.PosAmpl(ampl)
    self.OnChange(event)
  def OnPhase2(self, event):	# re-center the fine slider when the coarse slider is adjusted
    phase = self.phase_scale * self.phase1.GetValue() / 50.0 + self.phase_scale * self.phase2.GetValue()
    self.PosPhase(phase)
    self.OnChange(event)
  def DeleteEqual(self):	# Remove entry with the same VFO
    ap = application.bandAmplPhase
    lst = ap[self.band][self.rx_tx]
    vfo = (application.VFO + 500) / 1000
    for i in range(len(lst)-1, -1, -1):
      if (lst[i][0] + 500) / 1000 == vfo:
        del lst[i]
  def OnBtnSave(self, event):
    data = (application.VFO, application.rxFreq, self.new_amplitude, self.new_phase)
    self.DeleteEqual()
    ap = application.bandAmplPhase
    lst = ap[self.band][self.rx_tx]
    lst.append(data)
    lst.sort()
    application.w_phase = None
    self.Destroy()
  def OnBtnDiscard(self, event):
    self.DeleteEqual()
    self.OnBtnCancel()
  def OnBtnCancel(self, event=None):
    QS.set_ampl_phase(self.old_amplitude, self.old_phase, self.is_tx)
    application.w_phase = None
    self.Destroy()

class Spacer(wx.Window):
  """Create a bar between the graph screen and the controls"""
  def __init__(self, parent):
    wx.Window.__init__(self, parent, pos = (0, 0),
       size=(-1, 6), style = wx.NO_BORDER)
    self.Bind(wx.EVT_PAINT, self.OnPaint)
    r, g, b = parent.GetBackgroundColour().Get()
    dark = (r * 7 / 10, g * 7 / 10, b * 7 / 10)
    light = (r + (255 - r) * 5 / 10, g + (255 - g) * 5 / 10, b + (255 - b) * 5 / 10)
    self.dark_pen = wx.Pen(dark, 1, wx.SOLID)
    self.light_pen = wx.Pen(light, 1, wx.SOLID)
    self.width = application.screen_width
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    w = self.width
    dc.SetPen(self.dark_pen)
    dc.DrawLine(0, 0, w, 0)
    dc.DrawLine(0, 1, w, 1)
    dc.DrawLine(0, 2, w, 2)
    dc.SetPen(self.light_pen)
    dc.DrawLine(0, 3, w, 3)
    dc.DrawLine(0, 4, w, 4)
    dc.DrawLine(0, 5, w, 5)

class App(wx.App):
  """Class representing the application."""
  freq60 = (5330500, 5346500, 5366500, 5371500, 5403500)
  StateNames = [		# Names of state attributes to save and restore
  'bandState', 'bandAmplPhase', 'lastBand', 'VFO', 'txFreq', 'mode',
  'vardecim_set', 'filterAdjBw1',
  ]
  def __init__(self):
    global application
    application = self
    self.init_path = None
    if sys.stdout.isatty():
      wx.App.__init__(self, redirect=False)
    else:
      wx.App.__init__(self, redirect=True)
  def QuiskText(self, *args, **kw):			# Make our text control available to widget files
    return QuiskText(*args, **kw)
  def QuiskPushbutton(self, *args, **kw):	# Make our buttons available to widget files
    return QuiskPushbutton(*args, **kw)
  def  QuiskRepeatbutton(self, *args, **kw):
    return QuiskRepeatbutton(*args, **kw)
  def QuiskCheckbutton(self, *args, **kw):
    return QuiskCheckbutton(*args, **kw)
  def QuiskCycleCheckbutton(self, *args, **kw):
    return QuiskCycleCheckbutton(*args, **kw)
  def RadioButtonGroup(self, *args, **kw):
    return RadioButtonGroup(*args, **kw)
  def OnInit(self):
    """Perform most initialization of the app here (called by wxPython on startup)."""
    wx.lib.colourdb.updateColourDB()	# Add additional color names
    import quisk_widgets		# quisk_widgets needs the application object
    quisk_widgets.application = self
    del quisk_widgets
    global conf		# conf is the module for all configuration data
    import quisk_conf_defaults as conf
    setattr(conf, 'config_file_path', ConfigPath)
    if os.path.isfile(ConfigPath):	# See if the user has a config file
      setattr(conf, 'config_file_exists', True)
      d = {}
      d.update(conf.__dict__)		# make items from conf available
      execfile(ConfigPath, d)		# execute the user's config file
      for k, v in d.items():		# add user's config items to conf
        if k[0] != '_':				# omit items starting with '_'
          setattr(conf, k, v)
    else:
      setattr(conf, 'config_file_exists', False)
    if conf.invertSpectrum:
      QS.invert_spectrum(1)
    self.bandState = {}
    self.bandState.update(conf.bandState)
    self.bandAmplPhase = conf.bandAmplPhase
    # Open hardware file
    global Hardware
    if hasattr(conf, "Hardware"):	# Hardware defined in config file
      Hardware = conf.Hardware(self, conf)
    else:
      Hardware = conf.quisk_hardware.Hardware(self, conf)
    # Initialization - may be over-written by persistent state
    self.clip_time0 = 0		# timer to display a CLIP message on ADC overflow
    self.smeter_db_count = 0	# average the S-meter
    self.smeter_db_sum = 0
    self.smeter_db = 0
    self.smeter_sunits = -87.0
    self.timer = time.time()		# A seconds clock
    self.heart_time0 = self.timer	# timer to call HeartBeat at intervals
    self.smeter_db_time0 = self.timer
    self.smeter_sunits_time0 = self.timer
    self.band_up_down = 0			# Are band Up/Down buttons in use?
    self.lastBand = 'Audio'
    self.filterAdjBw1 = 1000
    self.VFO = 0
    self.ritFreq = 0
    self.txFreq = 0				# Transmit frequency as +/- sample_rate/2
    self.rxFreq = 0				# Receive  frequency as +/- sample_rate/2
    self.oldRxFreq = 0			# Last value of self.rxFreq
    self.screen = None
    self.audio_volume = 0.0		# Set output volume, 0.0 to 1.0
    self.sidetone_volume = 0.0	# Set sidetone volume, 0.0 to 1.0
    self.sound_error = 0
    self.sound_thread = None
    self.mode = conf.default_mode
    self.bottom_widgets = None
    self.color_list = None
    self.color_index = 0
    self.vardecim_set = None
    self.w_phase = None
    self.zoom = 1.0
    self.zoom_deltaf = 0
    self.zooming = False
    self.split_rxtx = False	# Are we in split Rx/Tx mode?
    dc = wx.ScreenDC()		# get the screen size
    (self.screen_width, self.screen_height) = dc.GetSizeTuple()
    del dc
    self.Bind(wx.EVT_IDLE, self.OnIdle)
    self.Bind(wx.EVT_QUERY_END_SESSION, self.OnEndSession)
    # Restore persistent program state
    if conf.persistent_state:
      self.init_path = os.path.join(os.path.dirname(ConfigPath), '.quisk_init.pkl')
      try:
        fp = open(self.init_path, "rb")
        d = pickle.load(fp)
        fp.close()
        for k, v in d.items():
          if k in self.StateNames:
            if k == 'bandState':
              self.bandState.update(v)
            else:
              setattr(self, k, v)
      except:
        pass #traceback.print_exc()
      for k, (vfo, tune, mode) in self.bandState.items():	# Historical: fix bad frequencies
        try:
          f1, f2 = conf.BandEdge[k]
          if not f1 <= vfo + tune <= f2:
            self.bandState[k] = conf.bandState[k]
        except KeyError:
          pass
    if self.bandAmplPhase and type(self.bandAmplPhase.values()[0]) is not DictType:
      print """Old sound card amplitude and phase corrections must be re-entered (sorry).
The new code supports multiple corrections per band."""
      self.bandAmplPhase = {}
    if Hardware.VarDecimGetChoices():	# Hardware can change the decimation.
      self.sample_rate = Hardware.VarDecimSet()	# Get the sample rate.
      self.vardecim_set = self.sample_rate
    else:		# Use the sample rate from the config file.
      self.sample_rate = conf.sample_rate
    if not hasattr(conf, 'playback_rate'):
      if conf.use_sdriq or conf.use_rx_udp:
        conf.playback_rate = 48000
      else:
        conf.playback_rate = conf.sample_rate
    # Find the data width from a list of prefered sizes; it is the width of returned graph data.
    # The graph_width is the width of data_width that is displayed.
    width = self.screen_width * conf.graph_width
    percent = conf.display_fraction		# display central fraction of total width
    percent = int(percent * 100.0 + 0.4)
    width = width * 100 / percent
    for x in fftPreferedSizes:
      if x > width:
        self.data_width = x
        break
    else:
      self.data_width = fftPreferedSizes[-1]
    self.graph_width = self.data_width * percent / 100
    if self.graph_width % 2 == 1:		# Both data_width and graph_width are even numbers
      self.graph_width += 1
    # The FFT size times the average_count controls the graph refresh rate
    factor = float(self.sample_rate) / conf.graph_refresh / self.data_width
    ifactor = int(factor + 0.5)
    if conf.fft_size_multiplier >= ifactor:	# Use large FFT and average count 1
      fft_mult = ifactor
      average_count = 1
    elif conf.fft_size_multiplier > 0:		# Specified fft_size_multiplier
      fft_mult = conf.fft_size_multiplier
      average_count = int(factor / fft_mult + 0.5)
      if average_count < 1:
        average_count = 1
    else:			# Calculate the split between fft size and average
      if self.sample_rate <= 240000:
        maxfft = 8000		# Maximum fft size
      else:
        maxfft = 15000
      fft1 = maxfft / self.data_width
      if fft1 >= ifactor:
        fft_mult = ifactor
        average_count = 1
      else:
        av1 = int(factor / fft1 + 0.5)
        if av1 < 1:
          av1 = 1
        err1 = factor / (fft1 * av1)
        av2 = av1 + 1
        fft2 = int(factor / av2 + 0.5)
        err2 = factor / (fft2 * av2)
        if 0.9 < err1 < 1.1 or abs(1.0 - err1) <= abs(1.0 - err2):
          fft_mult = fft1
          average_count = av1
        else:
          fft_mult = fft2
          average_count = av2
    self.fft_size = self.data_width * fft_mult
    # print 'data, graph,fft', self.data_width, self.graph_width, self.fft_size
    self.width = self.screen_width * 8 / 10
    self.height = self.screen_height * 5 / 10
    self.main_frame = frame = QMainFrame(self.width, self.height)
    self.SetTopWindow(frame)
    # Record the basic application parameters
    if sys.platform == 'win32':
      h = self.main_frame.GetHandle()
    else:
      h = 0
    QS.record_app(self, conf, self.data_width, self.fft_size,
                 average_count, self.sample_rate, h)
    #print 'FFT size %d, FFT mult %d, average_count %d' % (
    #    self.fft_size, self.fft_size / self.data_width, average_count)
    #print 'Refresh %.2f Hz' % (float(self.sample_rate) / self.fft_size / average_count)
    QS.record_graph(0, 0, 1.0)
    # Make all the screens and hide all but one
    self.graph = GraphScreen(frame, self.data_width, self.graph_width)
    self.screen = self.graph
    width = self.graph.width
    button_width = width	# calculate the final button width
    self.config_screen = ConfigScreen(frame, width, self.fft_size)
    self.config_screen.Hide()
    self.waterfall = WaterfallScreen(frame, width, self.data_width, self.graph_width)
    self.waterfall.Hide()
    self.scope = ScopeScreen(frame, width, self.data_width, self.graph_width)
    self.scope.Hide()
    self.filter_screen = FilterScreen(frame, self.data_width, self.graph_width)
    self.filter_screen.Hide()
    self.help_screen = HelpScreen(frame, width, self.screen_height / 10)
    self.help_screen.Hide()
    # Make a vertical box to hold all the screens and the bottom box
    vertBox = self.vertBox = wx.BoxSizer(wx.VERTICAL)
    frame.SetSizer(vertBox)
    # Add the screens
    vertBox.Add(self.config_screen, 1)
    vertBox.Add(self.graph, 1)
    vertBox.Add(self.waterfall, 1)
    vertBox.Add(self.scope, 1)
    vertBox.Add(self.filter_screen, 1)
    vertBox.Add(self.help_screen, 1)
    # Add the spacer
    vertBox.Add(Spacer(frame), 0, wx.EXPAND)
    # Add the bottom box
    hBoxA = wx.BoxSizer(wx.HORIZONTAL)
    vertBox.Add(hBoxA, 0, wx.EXPAND)
    # End of vertical box.  Add items to the horizontal box.
    # Add two sliders on the left
    margin = 3
    self.sliderVol = SliderBoxV(frame, 'Vol', 300, 1000, self.ChangeVolume)
    button_width -= self.sliderVol.width + margin * 2
    self.ChangeVolume()		# set initial volume level
    hBoxA.Add(self.sliderVol, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, margin)
    if Hardware.use_sidetone:
      self.sliderSto = SliderBoxV(frame, 'STo', 300, 1000, self.ChangeSidetone)
      button_width -= self.sliderSto.width + margin * 2
      self.ChangeSidetone()
      hBoxA.Add(self.sliderSto, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, margin)
    # Add the sizer for the middle
    gap = 2
    gbs = wx.GridBagSizer(gap, gap)
    self.gbs = gbs
    button_width -= gap * 15
    hBoxA.Add(gbs, 1, wx.EXPAND, 0)
    gbs.SetEmptyCellSize((5, 5))
    button_width -= 5
    # Add three sliders on the right
    self.sliderYs = SliderBoxV(frame, 'Ys', 0, 160, self.ChangeYscale, True)
    button_width -= self.sliderYs.width + margin * 2
    hBoxA.Add(self.sliderYs, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, margin)
    self.sliderYz = SliderBoxV(frame, 'Yz', 0, 160, self.ChangeYzero, True)
    button_width -= self.sliderYz.width + margin * 2
    hBoxA.Add(self.sliderYz, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, margin)
    self.sliderZo = SliderBoxV(frame, 'Zo', 0, 1000, self.OnChangeZoom)
    button_width -= self.sliderZo.width + margin * 2
    hBoxA.Add(self.sliderZo, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, margin)
    self.sliderZo.SetValue(0)
    button_width /= 12		# This is our final button size
    bw = button_width
    button_width, button_height = self.MakeButtons(frame, gbs, button_width, gap)
    ww = self.graph.width
    self.main_frame.SetSizeHints(ww, 100)
    if button_width > bw:		# The button width was increased
      ww += (button_width - bw) * 12
    self.main_frame.SetClientSizeWH(ww, self.screen_height * 5 / 10)
    self.MakeTopRow(frame, gbs, button_width, button_height)
    if conf.quisk_widgets:
      self.bottom_widgets = conf.quisk_widgets.BottomWidgets(self, Hardware, conf, frame, gbs, vertBox)
    if QS.open_key(conf.key_method):
      print 'open_key failed for name "%s"' % conf.key_method
    if hasattr(conf, 'mixer_settings'):
      for dev, numid, value in conf.mixer_settings:
        err_msg = QS.mixer_set(dev, numid, value)
        if err_msg:
          print "Mixer", err_msg
    # Create transmit audio filters
    if conf.microphone_name:
      filtI, filtQ = self.MakeFilterCoef(conf.mic_sample_rate, 540, 2700, 1650)
      QS.set_tx_filters(filtI, filtQ, ())
    # Open the hardware.  This must be called before open_sound().
    self.config_text = Hardware.open()
    if not self.config_text:
      self.config_text = "Missing config_text"
    if conf.use_rx_udp:
      self.add_version = True		# Add firmware version to config text
    else:
      self.add_version = False
    QS.capt_channels (conf.channel_i, conf.channel_q)
    QS.play_channels (conf.channel_i, conf.channel_q)
    QS.micplay_channels (conf.mic_play_chan_I, conf.mic_play_chan_Q)
    # Note: Subsequent calls to set channels must not name a higher channel number.
    #       Normally, these calls are only used to reverse the channels.
    QS.open_sound(conf.name_of_sound_capt, conf.name_of_sound_play, self.sample_rate,
                conf.data_poll_usec, conf.latency_millisecs,
                conf.microphone_name, conf.tx_ip, conf.tx_audio_port,
                conf.mic_sample_rate, conf.mic_channel_I, conf.mic_channel_Q,
				conf.mic_out_volume, conf.name_of_mic_play, conf.mic_playback_rate)
    tune, vfo = Hardware.ReturnFrequency()	# Request initial frequency
    #### Change below here
    if tune is None:			# Change to last-used frequency
      self.bandBtnGroup.SetLabel(self.lastBand, do_cmd=True)
    else:
      for band, (f1, f2) in conf.BandEdge.items():
        if f1 <= tune <= f2:	# Change to the correct band and frequency
          self.bandBtnGroup.SetLabel(band, do_cmd=True)
          break
      self.ChangeHwFrequency(tune - vfo, vfo, 'FreqEntry')
    #### Change above here
    # Note: The filter rate is not valid until after the call to open_sound().
    # Create FM audio filter
    frate = QS.get_filter_rate()	# filter rate
    filtI, filtQ = self.MakeFmFilterCoef(frate, 600, 340, 2800)
    QS.set_fm_filters(filtI)
    # Record filter rate for the filter screen
    self.filter_screen.sample_rate = frate
    #if info[8]:		# error message
    #  self.sound_error = 1
    #  self.config_screen.err_msg = info[8]
    #  print info[8]
    if self.sound_error:
      self.screenBtnGroup.SetLabel('Config', do_cmd=True)
      frame.Show()
    else:
      self.screenBtnGroup.SetLabel(conf.default_screen, do_cmd=True)
      frame.Show()
      self.Yield()
      self.sound_thread = SoundThread()
      self.sound_thread.start()
    return True
  def OnIdle(self, event):
    if self.screen:
      self.screen.OnIdle(event)
  def OnEndSession(self, event):
    event.Skip()
    self.OnBtnClose(event)
  def OnBtnClose(self, event):
    if self.sound_thread:
      self.sound_thread.stop()
    for i in range(0, 20):
      if threading.activeCount() == 1:
        break
      time.sleep(0.1)
  def OnExit(self):
    QS.close_rx_udp()
    Hardware.close()
    if self.init_path:		# save current program state
      d = {}
      for n in self.StateNames:
        d[n] = getattr(self, n)
      try:
        fp = open(self.init_path, "wb")
        pickle.dump(d, fp)
        fp.close()
      except:
        pass #traceback.print_exc()
  def MakeTopRow(self, frame, gbs, button_width, button_height):
    # Down button
    b_down = QuiskRepeatbutton(frame, self.OnBtnDownBand, "Down",
             self.OnBtnUpDnBandDone, use_right=True)
    gbs.Add(b_down, (0, 4), flag=wx.ALIGN_CENTER)
    # Up button
    b_up = QuiskRepeatbutton(frame, self.OnBtnUpBand, "Up",
             self.OnBtnUpDnBandDone, use_right=True)
    gbs.Add(b_up, (0, 5), flag=wx.ALIGN_CENTER)
    # RIT button
    self.ritButton = QuiskCheckbutton(frame, self.OnBtnRit, "RIT")
    gbs.Add(self.ritButton, (0, 7), flag=wx.ALIGN_CENTER)
    bw, bh = b_down.GetMinSize()		# make these buttons the same size
    bw = (bw + button_width) / 2
    b_down.SetSizeHints        (bw, button_height, bw * 5, button_height)
    b_up.SetSizeHints          (bw, button_height, bw * 5, button_height)
    self.ritButton.SetSizeHints(bw, button_height, bw * 5, button_height)
    # RIT slider
    self.ritScale = wx.Slider(frame, -1, self.ritFreq, -2000, 2000, size=(-1, -1), style=wx.SL_LABELS)
    self.ritScale.Bind(wx.EVT_SCROLL, self.OnRitScale)
    gbs.Add(self.ritScale, (0, 8), (1, 3), flag=wx.EXPAND)
    sw, sh = self.ritScale.GetSize()
    # Frequency display
    h = max(button_height, sh)		# larger of button and slider height
    self.freqDisplay = FrequencyDisplay(frame, gbs, button_width * 25 / 10, h)
    self.freqDisplay.Display(self.txFreq + self.VFO)
    # Frequency entry
    e = wx.TextCtrl(frame, -1, '', style=wx.TE_PROCESS_ENTER)
    font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    e.SetFont(font)
    w, h = e.GetSizeTuple()
    border = (self.freqDisplay.height_and_border - h) / 2
    e.SetMinSize((1, 1))
    e.SetBackgroundColour(conf.color_entry)
    gbs.Add(e, (0, 3), flag = wx.EXPAND | wx.TOP | wx.BOTTOM, border=border)
    frame.Bind(wx.EVT_TEXT_ENTER, self.FreqEntry, source=e)
    # S-meter
    self.smeter = QuiskText(frame, 'ZZS 9   -100.00 dBZZ', bh, wx.ALIGN_CENTER)
    gbs.Add(self.smeter, (0, 11), (1, 2), flag=wx.EXPAND)
  def MakeButtons(self, frame, gbs, button_width, gap):
    # There are six columns, a small gap column, and then six more columns
    ### Left bank of buttons
    flag = wx.EXPAND
    # Band buttons are put into a box sizer that spans the first six buttons
    self.bandBtnGroup = RadioButtonGroup(frame, self.OnBtnBand, conf.bandLabels, None)
    band_buttons = self.bandBtnGroup.buttons
    szr = wx.BoxSizer(wx.HORIZONTAL)
    gbs.Add(szr, (1, 0), (1, 6))
    band_length = 0
    for b in band_buttons:	# Get the total length
      szr.Add(b, 0)
      w, h = b.GetMinSize()
      band_length += w
    band_size = (band_length - gap * 5) / 6 + 1			# Button size needed by band buttons
    # Receive button row: Mute, AGC
    left_buttons = []
    b = QuiskCheckbutton(frame, self.OnBtnMute, text='Mute')
    left_buttons.append(b)
    b = QuiskCycleCheckbutton(frame, self.OnBtnAGC, ('AGC', 'AGC 1', 'AGC 2'))
    left_buttons.append(b)
    b.SetLabel('AGC 1', True)
    b = QuiskCycleCheckbutton(frame, self.OnBtnNB, ('NB', 'NB 1', 'NB 2', 'NB 3'))
    left_buttons.append(b)
    try:
      labels = Hardware.rf_gain_labels
    except:
      labels = ()
    if labels:
      b = self.BtnRfGain = QuiskCycleCheckbutton(frame, Hardware.OnButtonRfGain, labels)
    else:
      b = QuiskCheckbutton(frame, None, text='RfGain')
      b.Enable(False)
      self.BtnRfGain = None
    left_buttons.append(b)
    b = QuiskCheckbutton(frame, None, text='')
    left_buttons.append(b)
    b = QuiskCheckbutton(frame, None, text='')
    left_buttons.append(b)
    for col in range(0, 6):
      gbs.Add(left_buttons[col], (2, col), flag=flag)
    # Transmit button row: Spot
    b = QuiskCycleCheckbutton(frame, self.OnBtnSpot,
         ('Spot', 'Spot -6db', 'Spot 0db'), color=conf.color_test)
    if not hasattr(Hardware, 'OnSpot'):
      b.Enable(False)
    left_buttons.append(b)
    b = self.splitButton = QuiskCheckbutton(frame, self.OnBtnSplit, "Split")
    if conf.mouse_tune_method:		# Mouse motion changes the VFO frequency
      b.Enable(False)
    left_buttons.append(b)
    b = QuiskCheckbutton(frame, self.OnBtnFDX, 'FDX', color=conf.color_test)
    if not conf.add_fdx_button:
      b.Enable(False)
    left_buttons.append(b)
    b = QuiskCheckbutton(frame, None, text='')
    left_buttons.append(b)
    if 0:	# Display a color chooser
      b = QuiskRepeatbutton(frame, self.OnBtnColor, 'Color', use_right=True)
    else:
      b = QuiskCheckbutton(frame, None, text='')
    left_buttons.append(b)
    b = QuiskCheckbutton(frame, self.OnBtnTest1, 'Test 1', color=conf.color_test)
    left_buttons.append(b)
    for col in range(0, 6):
      gbs.Add(left_buttons[col + 6], (3, col), flag=flag)
    ### Right bank of buttons
    labels = [('CWL', 'CWU'), ('LSB', 'USB'), 'AM', 'FM', conf.add_extern_demod, '']
    if conf.add_imd_button:
      labels[-1] = ('IMD', 'IMD -3dB', 'IMD -6dB')
    self.modeButns = RadioButtonGroup(frame, self.OnBtnMode, labels, None)
    right_buttons = self.modeButns.GetButtons()
    if conf.add_imd_button:
      right_buttons[-1].color = conf.color_test
    labels = ('0', '0', '0', '0', '0', '_filter_')
    self.filterButns = RadioButtonGroup(frame, self.OnBtnFilter, labels, None)
    right_buttons += self.filterButns.GetButtons()
    labels = (('Graph', 'GraphP1', 'GraphP2'), 'WFall', ('Scope', 'Scope'), 'Config', 'RX Filter', 'Help')
    self.screenBtnGroup = RadioButtonGroup(frame, self.OnBtnScreen, labels, conf.default_screen)
    right_buttons += self.screenBtnGroup.GetButtons()
    col = 7
    for i in range(0, 6):
      gbs.Add(right_buttons[i], (1, col), flag=flag)
      gbs.Add(right_buttons[i+6], (2, col), flag=flag)
      gbs.Add(right_buttons[i+12], (3, col), flag=flag)
      col += 1
    bsize = 0		# Find size of largest button
    for b in left_buttons + right_buttons:
      w, height = b.GetMinSize()
      if bsize < w:
        bsize = w
    # Perhaps increase the requested button width
    button_width = max(bsize, band_size, button_width)
    # Adjust size of buttons
    for b in left_buttons + right_buttons:
      b.SetMinSize((button_width, height))
    # Adjust size of band buttons
    width = button_width * 6 + gap * 5		# Final size of band button row
    add = width - band_length
    add = add / len(band_buttons)			# Amount to add to each band button to fill space
    for b in band_buttons[0:-1]:
      w, h = b.GetMinSize()
      w += add
      b.SetMinSize((w, h))
      width -= w
    band_buttons[-1].SetMinSize((width, h))
    # return the button size
    return button_width, height
  def NewSmeter(self):
    #avg_seconds = 5.0				# seconds for S-meter average
    avg_seconds = 1.0
    self.smeter_db_count += 1		# count for average
    x = QS.get_smeter()
    self.smeter_db_sum += x		# sum for average
    if self.timer - self.smeter_db_time0 > avg_seconds:		# average time reached
      self.smeter_db = self.smeter_db_sum / self.smeter_db_count
      self.smeter_db_count = self.smeter_db_sum = 0 
      self.smeter_db_time0 = self.timer
    if self.smeter_sunits < x:		# S-meter moves to peak value
      self.smeter_sunits = x
    else:			# S-meter decays at this time constant
      self.smeter_sunits -= (self.smeter_sunits - x) * (self.timer - self.smeter_sunits_time0)
    self.smeter_sunits_time0 = self.timer
    s = self.smeter_sunits / 6.0	# change to S units; 6db per S unit
    s += Hardware.correct_smeter	# S-meter correction for the gain, band, etc.
    if s < 0:
      s = 0
    if s >= 9.5:
      s = (s - 9.0) * 6
      t = "S9 + %.0f   %.2f dB" % (s, self.smeter_db)
    else:
      t = "S %.0f   %.2f dB" % (s, self.smeter_db)
    self.smeter.SetLabel(t)
  def MakeFilterButtons(self, args):
    # Change the filter selections depending on the mode: CW, SSB, etc.
    # Do not change the adjustable filter buttons.
    buttons = self.filterButns.GetButtons()
    for i in range(0, len(buttons) - 1):
      buttons[i].SetLabel(str(args[i]))
      buttons[i].Refresh()
  def MakeFilterCoef(self, rate, N, bw, center):
    """Make an I/Q filter with rectangular passband."""
    K = bw * N / rate
    filtI = []
    filtQ = []
    pi = math.pi
    sin = math.sin
    cos = math.cos
    tune = 2. * pi * center / rate
    for k in range(-N/2, N/2 + 1):
      # Make a lowpass filter
      if k == 0:
        z = float(K) / N
      else:
        z = 1.0 / N * sin(pi * k * K / N) / sin(pi * k / N)
      # Apply a windowing function
      if 1:	# Blackman window
        w = 0.42 + 0.5 * cos(2. * pi * k / N) + 0.08 * cos(4. * pi * k / N)
      elif 0:	# Hamming
        w = 0.54 + 0.46 * cos(2. * pi * k / N)
      elif 0:	# Hanning
        w = 0.5 + 0.5 * cos(2. * pi * k / N)
      else:
        w = 1
      z *= w
      # Make a bandpass filter by tuning the low pass filter to new center frequency.
      # Make two quadrature filters.
      if tune:
        z *= 2.0 * cmath.exp(-1j * tune * k)
        filtI.append(z.real)
        filtQ.append(z.imag)
      else:
        filtI.append(z)
        filtQ.append(z)
    return filtI, filtQ
  def MakeFmFilterCoef(self, rate, N, f1, f2):
    """Make an audio filter with FM de-emphasis; remove CTCSS tones."""
    bw = f2 - f1
    center = (f1 + f2) / 2
    N2 = N / 2				# Half the number of points
    K2 = bw * N / rate / 2	# Half the bandwidth in points
    filtI = []
    filtQ = []
    passb = [0] * (N + 1)		# desired passband response
    idft = [0] * (N + 1)		# inverse DFT of desired passband
    pi = math.pi
    sin = math.sin
    cos = math.cos
    tune = 2. * pi * center / rate
    # indexing can be from - N2 thru + N2 inclusive; total points is 2 * N2 + 1
    # indexing can be from 0 thru 2 * N2 inclusive; total points is 2 * N2 + 1
    for j in range(-K2, K2 + 1):		# Filter shape is -6 bB per octave
      jj = j + N2
      freq = center - bw / 2.0 * float(j) / K2
      passb[jj] = float(center) / freq * 0.3
    for k in range(-N2 + 1, N2 + 1):		# Take inverse DFT of passband response
      kk = k + N2
      x = 0 + 0J
      for m in range(-N2, N2 + 1):
        mm = m + N2
        if passb[mm]:
          x += passb[mm] * cmath.exp(1J * 2.0 * pi * m * k / N)
      x /= N
      idft[kk] = x
    idft[0] = idft[-1]		# this value is missing
    for k in range(-N2, N2 + 1):
      kk = k + N2
      z = idft[kk]
      # Apply a windowing function
      if 1:	# Blackman window
        w = 0.42 + 0.5 * cos(2. * pi * k / N) + 0.08 * cos(4. * pi * k / N)
      elif 0:	# Hamming
        w = 0.54 + 0.46 * cos(2. * pi * k / N)
      elif 0:	# Hanning
        w = 0.5 + 0.5 * cos(2. * pi * k / N)
      else:
        w = 1
      z *= w
      # Make a bandpass filter by tuning the low pass filter to new center frequency.
      # Make two quadrature filters.
      if tune:
        z *= 2.0 * cmath.exp(-1j * tune * k)
        filtI.append(z.real)
        filtQ.append(z.imag)
      else:
        filtI.append(z.real)
        filtQ.append(z.real)
    return filtI, filtQ
  def OnBtnFilter(self, event, bw=None):
    if event is None:	# called by application
      self.filterButns.SetLabel(str(bw))
    else:		# called by button
      btn = event.GetEventObject()
      bw = int(btn.GetLabel())
    mode = self.mode
    if mode in ("CWL", "CWU"):
      N = 1000
      center = max(conf.cwTone, bw/2)
    elif mode in ('LSB', 'USB'):
      N = 540
      center = 300 + bw / 2
    else:	# AM and FM
      N = 140
      center = 0
    frate = QS.get_filter_rate()
    filtI, filtQ = self.MakeFilterCoef(frate, N, bw, center)
    QS.set_filters(filtI, filtQ, bw)
    if self.screen is self.filter_screen:
      self.screen.NewFilter()
  def OnBtnScreen(self, event, name=None):
    if event is not None:
      win = event.GetEventObject()
      name = win.GetLabel()
    self.screen.Hide()
    if name == 'Config':
      self.screen = self.config_screen
    elif name[0:5] == 'Graph':
      self.screen = self.graph
      self.screen.SetTxFreq(self.txFreq, self.rxFreq)
      self.freqDisplay.Display(self.VFO + self.txFreq)
      self.screen.PeakHold(name)
    elif name == 'WFall':
      self.screen = self.waterfall
      self.screen.SetTxFreq(self.txFreq, self.rxFreq)
      self.freqDisplay.Display(self.VFO + self.txFreq)
      sash = self.screen.GetSashPosition()
    elif name == 'Scope':
      if win.direction:				# Another push on the same button
        self.scope.running = 1 - self.scope.running		# Toggle run state
      else:				# Initial push of button
        self.scope.running = 1
      self.screen = self.scope
    elif name == 'RX Filter':
      self.screen = self.filter_screen
      self.freqDisplay.Display(self.screen.txFreq)
      self.screen.NewFilter()
    elif name == 'Help':
      self.screen = self.help_screen
    self.screen.Show()
    self.vertBox.Layout()	# This destroys the initialized sash position!
    self.sliderYs.SetValue(self.screen.y_scale)
    self.sliderYz.SetValue(self.screen.y_zero)
    if name == 'WFall':
      self.screen.SetSashPosition(sash)
  def ChangeYscale(self, event):
    self.screen.ChangeYscale(self.sliderYs.GetValue())
  def ChangeYzero(self, event):
    self.screen.ChangeYzero(self.sliderYz.GetValue())
  def OnChangeZoom(self, event):
    x = self.sliderZo.GetValue()
    if x < 50:
      self.zoom = 1.0	# change back to not-zoomed mode
      self.zoom_deltaf = 0
      self.zooming = False
    else:
      a = 1000.0 * self.sample_rate / (self.sample_rate - 2500.0)
      self.zoom = 1.0 - x / a
      if not self.zooming:
        self.zoom_deltaf = self.txFreq		# set deltaf when zoom mode starts
        self.zooming = True
    zoom = self.zoom
    deltaf = self.zoom_deltaf
    self.graph.ChangeZoom(zoom, deltaf)
    self.waterfall.pane1.ChangeZoom(zoom, deltaf)
    self.waterfall.pane2.ChangeZoom(zoom, deltaf)
    self.waterfall.pane2.display.ChangeZoom(zoom, deltaf)
    self.screen.SetTxFreq(self.txFreq, self.rxFreq)
  def OnBtnMute(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      QS.set_volume(0)
    else:
      QS.set_volume(self.audio_volume)
  def OnBtnDecimation(self, event):
    i = event.GetSelection()
    rate = Hardware.VarDecimSet(i)
    self.vardecim_set = rate
    if rate != self.sample_rate:
      self.sample_rate = rate
      self.graph.sample_rate = rate
      self.waterfall.pane1.sample_rate = rate
      self.waterfall.pane2.sample_rate = rate
      self.waterfall.pane2.display.sample_rate = rate
      average_count = float(rate) / conf.graph_refresh / self.fft_size
      average_count = int(average_count + 0.5)
      average_count = max (1, average_count)
      QS.change_rate(rate, average_count)
      tune = self.txFreq
      vfo = self.VFO
      self.txFreq = self.VFO = -1		# demand change
      self.ChangeHwFrequency(tune, vfo, 'NewDecim')
  def ChangeVolume(self, event=None):
    # Caution: event can be None
    value = self.sliderVol.GetValue()
    # Simulate log taper pot
    x = (10.0 ** (float(value) * 0.003000434077) - 1) / 1000.0
    self.audio_volume = x	# audio_volume is 0 to 1.000
    QS.set_volume(x)
  def ChangeSidetone(self, event=None):
    # Caution: event can be None
    value = self.sliderSto.GetValue()
    # Simulate log taper pot
    x = (10.0 ** (float(value) * 0.003) - 1) / 1000.0
    self.sidetone_volume = x
    QS.set_sidetone(x, self.ritFreq, conf.keyupDelay)
  def OnRitScale(self, event=None):	# Called when the RIT slider is moved
    # Caution: event can be None
    if self.ritButton.GetValue():
      value = self.ritScale.GetValue()
      value = int(value)
      self.ritFreq = value
      QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
      QS.set_sidetone(self.sidetone_volume, self.ritFreq, conf.keyupDelay)
  def OnBtnSplit(self, event):	# Called when the Split check button is pressed
    self.split_rxtx = self.splitButton.GetValue()
    if self.split_rxtx:
      self.rxFreq = self.oldRxFreq
      d = self.sample_rate * 49 / 100	# Move rxFreq on-screen
      if self.rxFreq < -d:
        self.rxFreq = -d
      elif self.rxFreq > d:
        self.rxFreq = d
    else:
      self.oldRxFreq = self.rxFreq
      self.rxFreq = self.txFreq
    self.screen.SetTxFreq(self.txFreq, self.rxFreq)
    QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
  def OnBtnRit(self, event=None):	# Called when the RIT check button is pressed
    # Caution: event can be None
    if self.ritButton.GetValue():
      self.ritFreq = self.ritScale.GetValue()
    else:
      self.ritFreq = 0
    QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
    QS.set_sidetone(self.sidetone_volume, self.ritFreq, conf.keyupDelay)
  def SetRit(self, freq):
    if freq:
      self.ritButton.SetValue(1)
    else:
      self.ritButton.SetValue(0)
    self.ritScale.SetValue(freq)
    self.OnBtnRit()
  def OnBtnFDX(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      QS.set_fdx(1)
    else:
      QS.set_fdx(0)
  def OnBtnSpot(self, event):
    btn = event.GetEventObject()
    QS.set_spot_mode(btn.index)
    Hardware.OnSpot(btn.index)
  def OnBtnTest1(self, event):
    btn = event.GetEventObject()
    if btn.GetValue():
      QS.add_tone(10000)
    else:
      QS.add_tone(0)
  def OnBtnTest2(self, event):
    return
  def OnBtnColor(self, event):
    if not self.color_list:
      clist = wx.lib.colourdb.getColourInfoList()
      self.color_list = [(0, clist[0][0])]
      self.color_index = 0
      for i in range(1, len(clist)):
        if  self.color_list[-1][1].replace(' ', '') != clist[i][0].replace(' ', ''):
          #if 'BLUE' in clist[i][0]:
            self.color_list.append((i, clist[i][0]))
    btn = event.GetEventObject()
    if btn.shift:
      del self.color_list[self.color_index]
    else:
      self.color_index += btn.direction
    if self.color_index >= len(self.color_list):
      self.color_index = 0
    elif self.color_index < 0:
      self.color_index = len(self.color_list) -1
    color = self.color_list[self.color_index][1]
    print self.color_index, color
    self.main_frame.SetBackgroundColour(color)
    self.main_frame.Refresh()
    self.screen.Refresh()
    btn.SetBackgroundColour(color)
    btn.Refresh()
  def OnBtnAGC(self, event):
    btn = event.GetEventObject()
    # Set AGC: agcInUse, agcAttack, agcRelease
    if btn.index == 1:
      QS.set_agc(1, 1.0, 0.01)
    elif btn.index == 2:
      QS.set_agc(2, 1.0, 0.1)
    else:
      QS.set_agc(0, 0, 0)
  def OnBtnNB(self, event):
    index = event.GetEventObject().index
    QS.set_noise_blanker(index)
  def FreqEntry(self, event):
    freq = event.GetString()
    if not freq:
      return
    try:
      if '.' in freq:
        freq = int(float(freq) * 1E6 + 0.1)
      else:
        freq = int(freq)
    except ValueError:
      win = event.GetEventObject()
      win.Clear()
      win.AppendText("Error")
    else:
      for band, (f1, f2) in conf.BandEdge.items():
        if f1 <= freq <= f2:	# Change to the correct band based on frequency
          self.bandBtnGroup.SetLabel(band, do_cmd=True)
          break
      tune = freq % 10000
      vfo = freq - tune
      self.ChangeHwFrequency(tune, vfo, 'FreqEntry')
  def ChangeHwFrequency(self, tune, vfo, source='', band='', event=None):
    """Change the VFO and tuning frequencies, and notify the hardware.

    tune:   the new tuning frequency in +- sample_rate/2;
    vfo:    the new vfo frequency in Hertz; this is the RF frequency at zero Hz audio
    source: a string indicating the source or widget requesting the change;
    band:   if source is "BtnBand", the band requested;
    event:  for a widget, the event (used to access control/shift key state).

    Try to update the hardware by calling Hardware.ChangeFrequency().
    The hardware will reply with the updated frequencies which may be different
    from those requested; use and display the returned tune and vfo.

    If tune or vfo is None, query the hardware for the current frequency.
    """
    change = 0
    if tune is None or vfo is None:
      tune, vfo = Hardware.ReturnFrequency()
      if tune is None or vfo is None:		# hardware did not change the frequency
        return change
    else:
      tune, vfo = Hardware.ChangeFrequency(vfo + tune, vfo, source, band, event)
    tune -= vfo
    if tune != self.txFreq:
      change = 1
      self.txFreq = tune
      if not self.split_rxtx:
        self.rxFreq = self.txFreq
      self.screen.SetTxFreq(self.txFreq, self.rxFreq)
      QS.set_tune(self.rxFreq + self.ritFreq, self.txFreq)
    if vfo != self.VFO:
      change = 1
      self.VFO = vfo
      self.graph.SetVFO(vfo)
      self.waterfall.SetVFO(vfo)
      if self.w_phase:		# Phase adjustment screen can not change its VFO
        self.w_phase.Destroy()
        self.w_phase = None
      ampl, phase = self.GetAmplPhase(0)
      QS.set_ampl_phase(ampl, phase, 0)
      ampl, phase = self.GetAmplPhase(1)
      QS.set_ampl_phase(ampl, phase, 1)
    if change:
      self.freqDisplay.Display(self.txFreq + self.VFO)
    return change
  def OnBtnMode(self, event, mode=None):
    if event is None:	# called by application
      self.modeButns.SetLabel(mode)
    else:		# called by button
      mode = self.modeButns.GetLabel()
    Hardware.ChangeMode(mode)
    self.mode = mode
    if mode in ('CWL', 'CWU'):
      if mode == 'CWL':
        QS.set_rx_mode(0)
        self.SetRit(conf.cwTone)
      else:					# CWU
        QS.set_rx_mode(1)
        self.SetRit(-conf.cwTone)
      self.MakeFilterButtons(conf.FilterBwCW)
      self.OnBtnFilter(None, 1000)
    elif mode in ('LSB', 'USB'):
      if mode == 'LSB':
        QS.set_rx_mode(2)	# LSB
      else:
        QS.set_rx_mode(3)	# USB
      self.SetRit(0)
      self.MakeFilterButtons(conf.FilterBwSSB)
      self.OnBtnFilter(None, 2800)
    elif mode == 'AM':
      QS.set_rx_mode(4)
      self.SetRit(0)
      self.MakeFilterButtons(conf.FilterBwAM)
      self.OnBtnFilter(None, 6000)
    elif mode == 'FM':
      QS.set_rx_mode(5)
      self.SetRit(0)
      self.MakeFilterButtons(conf.FilterBwFM)
      self.OnBtnFilter(None, 12000)
    elif mode[0:3] == 'IMD':
      QS.set_rx_mode(10 + self.modeButns.GetSelectedButton().index)	# 10, 11, 12
      self.SetRit(0)
      self.MakeFilterButtons(conf.FilterBwIMD)
      self.OnBtnFilter(None, 2800)
    elif mode == conf.add_extern_demod:	# External demodulation
      QS.set_rx_mode(6)
      self.SetRit(0)
      self.MakeFilterButtons(conf.FilterBwEXT)
      self.OnBtnFilter(None, 12000)
  def OnBtnBand(self, event):
    band = self.lastBand	# former band in use
    try:
      f1, f2 = conf.BandEdge[band]
      if f1 <= self.VFO + self.txFreq <= f2:
        self.bandState[band] = (self.VFO, self.txFreq, self.mode)
    except KeyError:
      pass
    btn = event.GetEventObject()
    band = btn.GetLabel()	# new band
    self.lastBand = band
    try:
      vfo, tune, mode = self.bandState[band]
    except KeyError:
      vfo, tune, mode = (0, 0, 'LSB')
    if band == '60':
      freq = vfo + tune
      if btn.direction:
        vfo = self.VFO
        if 5100000 < vfo < 5600000:
          if btn.direction > 0:		# Move up
            for f in self.freq60:
              if f > vfo + self.txFreq:
                freq = f
                break
            else:
              freq = self.freq60[0]
          else:			# move down
            l = list(self.freq60)
            l.reverse()
            for f in l: 
              if f < vfo + self.txFreq:
                freq = f
                break
              else:
                freq = self.freq60[-1]
      half = self.sample_rate / 2 * self.graph_width / self.data_width
      while freq - vfo <= -half + 1000:
        vfo -= 10000
      while freq - vfo >= +half - 5000:
        vfo += 10000
      tune = freq - vfo
    elif band == 'Time':
      vfo, tune, mode = conf.bandTime[btn.index]
    self.OnBtnMode(None, mode)
    self.txFreq = self.VFO = -1		# demand change
    self.ChangeHwFrequency(tune, vfo, 'BtnBand', band=band)
    Hardware.ChangeBand(band)
  def OnBtnUpDnBandDelta(self, event, is_band_down):
    sample_rate = int(self.sample_rate * self.zoom)
    oldvfo = self.VFO
    btn = event.GetEventObject()
    if btn.direction > 0:		# left button was used, move a bit
      d = int(sample_rate / 9)
    else:						# right button was used, move to edge
      d = int(sample_rate * 45 / 100)
    if is_band_down:
      d = -d
    vfo = self.VFO + d
    if sample_rate > 40000:
      vfo = (vfo + 5000) / 10000 * 10000	# round to even number
      delta = 10000
    elif sample_rate > 5000:
      vfo = (vfo + 500) / 1000 * 1000
      delta = 1000
    else:
      vfo = (vfo + 50) / 100 * 100
      delta = 100
    if oldvfo == vfo:
      if is_band_down:
        d = -delta
      else:
        d = delta
    else:
      d = vfo - oldvfo
    self.VFO += d
    self.txFreq -= d
    self.rxFreq -= d
    # Set the display but do not change the hardware
    self.graph.SetVFO(self.VFO)
    self.waterfall.SetVFO(self.VFO)
    self.screen.SetTxFreq(self.txFreq, self.rxFreq)
    self.freqDisplay.Display(self.txFreq + self.VFO)
  def OnBtnDownBand(self, event):
    self.band_up_down = 1
    self.OnBtnUpDnBandDelta(event, True)
  def OnBtnUpBand(self, event):
    self.band_up_down = 1
    self.OnBtnUpDnBandDelta(event, False)
  def OnBtnUpDnBandDone(self, event):
    self.band_up_down = 0
    tune = self.txFreq
    vfo = self.VFO
    self.txFreq = self.VFO = 0		# Force an update
    self.ChangeHwFrequency(tune, vfo, 'BtnUpDown')
  def GetAmplPhase(self, is_tx):
    if conf.bandAmplPhase.has_key("panadapter"):
      band = "panadapter"
    else:
      band = self.lastBand
    try:
      if is_tx:
        lst = self.bandAmplPhase[band]["tx"]
      else:
        lst = self.bandAmplPhase[band]["rx"]
    except KeyError:
      return (0.0, 0.0)
    length = len(lst)
    if length == 0:
      return (0.0, 0.0)
    elif length == 1:
      return lst[0][2], lst[0][3]
    elif self.VFO < lst[0][0]:		# before first data point
      i1 = 0
      i2 = 1
    elif lst[length - 1][0] < self.VFO:	# after last data point
      i1 = length - 2
      i2 = length - 1
    else:
      # Binary search for the bracket VFO
      i1 = 0
      i2 = length
      index = (i1 + i2) / 2
      for i in range(length):
        diff = lst[index][0] - self.VFO
        if diff < 0:
          i1 = index
        elif diff > 0:
          i2 = index
        else:		# equal VFO's
          return lst[index][2], lst[index][3]
        if i2 - i1 <= 1:
          break
        index = (i1 + i2) / 2
    d1 = self.VFO - lst[i1][0]		# linear interpolation
    d2 = lst[i2][0] - self.VFO
    dx = d1 + d2
    ampl = (d1 * lst[i2][2] + d2 * lst[i1][2]) / dx
    phas = (d1 * lst[i2][3] + d2 * lst[i1][3]) / dx
    return ampl, phas
  def PostStartup(self):	# called once after sound attempts to start
    self.config_screen.OnGraphData(None)	# update config in case sound is not running
  def OnReadSound(self):	# called at frequent intervals
    self.timer = time.time()
    if self.screen == self.scope:
      data = QS.get_graph(0, 1.0, 0)	# get raw data
      if data:
        self.scope.OnGraphData(data)			# Send message to draw new data
        return 1		# we got new graph/scope data
    else:
      data = QS.get_graph(1, self.zoom, float(self.zoom_deltaf))	# get FFT data
      if data:
        #T('')
        self.NewSmeter()			# update the S-meter
        if self.screen == self.graph:
          self.waterfall.OnGraphData(data)		# save waterfall data
          self.graph.OnGraphData(data)			# Send message to draw new data
        elif self.screen == self.config_screen:
          pass
        else:
          self.screen.OnGraphData(data)			# Send message to draw new data
        #T('graph data')
        #application.Yield()
        #T('Yield')
        return 1		# We got new graph/scope data
    if QS.get_overrange():
      self.clip_time0 = self.timer
      self.freqDisplay.Clip(1)
    if self.clip_time0:
      if self.timer - self.clip_time0 > 1.0:
        self.clip_time0 = 0
        self.freqDisplay.Clip(0)
    if self.timer - self.heart_time0 > 0.10:		# call hardware to perform background tasks
      self.heart_time0 = self.timer
      if self.screen == self.config_screen:
        self.screen.OnGraphData()			# Send message to draw new data
      Hardware.HeartBeat()
      if self.add_version and Hardware.GetFirmwareVersion() is not None:
        self.add_version = False
        self.config_text = "%s, firmware version 1.%d" % (self.config_text, Hardware.GetFirmwareVersion())
      if not self.band_up_down:
        # Poll the hardware for changed frequency.  This is used for hardware
        # that can change its frequency independently of Quisk; eg. K3.
        if self.ChangeHwFrequency(None, None):	# Returns true for a change
          try:
            f1, f2 = conf.BandEdge[self.lastBand]
            if f1 <= self.VFO + self.txFreq <= f2:
              self.bandState[self.lastBand] = (self.VFO, self.txFreq, self.mode)
              return
          except KeyError:
            pass
          # Frequency is not within the current band.  Change to the correct band based on frequency.
          for band, (f1, f2) in conf.BandEdge.items():
            if f1 <= self.VFO + self.txFreq <= f2:
              self.lastBand = band
              self.bandBtnGroup.SetLabel(band, do_cmd=True)
              break

def main():
  """If quisk is installed as a package, you can run it with quisk.main()."""
  App()
  application.MainLoop()

if __name__ == '__main__':
  main()

