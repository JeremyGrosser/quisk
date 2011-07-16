# Please do not change this widgets module for Quisk.  Instead copy
# it to your own quisk_widgets.py and make changes there.
#
# This module is used to add extra widgets to the QUISK screen.

import wx
import _quisk as QS
import math

class BottomWidgets:	# Add extra widgets to the bottom of the screen
  def __init__(self, app, hardware, conf, frame, gbs, vertBox):
    self.hardware = hardware
    b = app.QuiskPushbutton(frame, hardware.anttuner.OnAntTuner, 'Tune')
    bw, bh = b.GetMinSize()
    gbs.Add(b, (4, 0), flag=wx.EXPAND)
    b = app.QuiskPushbutton(frame, hardware.anttuner.OnAntTuner, 'L+')
    gbs.Add(b, (4, 1), flag=wx.EXPAND)
    b = app.QuiskPushbutton(frame, hardware.anttuner.OnAntTuner, 'L-')
    gbs.Add(b, (4, 2), flag=wx.EXPAND)
    b = app.QuiskPushbutton(frame, hardware.anttuner.OnAntTuner, 'C+')
    gbs.Add(b, (4, 3), flag=wx.EXPAND)
    b = app.QuiskPushbutton(frame, hardware.anttuner.OnAntTuner, 'C-')
    gbs.Add(b, (4, 4), flag=wx.EXPAND)
    b = app.QuiskPushbutton(frame, hardware.anttuner.OnAntTuner, 'Save')
    gbs.Add(b, (4, 5), flag=wx.EXPAND)
    self.swr_label = app.QuiskText(frame, 'Watts 000   SWR 10.1  Zh Ind 22 Cap 33   Freq 28100 (7777)', bh)
    gbs.Add(self.swr_label, (4, 7), (1, 5), flag=wx.EXPAND)
    b = app.QuiskCheckbutton(frame, None, text='')
    gbs.Add(b, (4, 12), flag=wx.EXPAND)
#  Example of a horizontal slider:
#    lab = wx.StaticText(frame, -1, 'Preamp', style=wx.ALIGN_CENTER)
#    gbs.Add(lab, (5,0), flag=wx.EXPAND)
#    sl = wx.Slider(frame, -1, 1024, 0, 2048)	# parent, -1, initial, min, max
#    gbs.Add(sl, (5,1), (1, 5), flag=wx.EXPAND)
#    sl.Bind(wx.EVT_SCROLL, self.OnPreamp)
#  def OnPreamp(self, event):
#    print event.GetPosition()
  def UpdateSwr(self, param1, param2, error):	# Called by Hardware
    if error:
      text = error
    else:
      freq = param1[7] * 256 + param2[7]
      power = (param1[5] * 256 + param2[5]) / 100.0
      swr = param2[6]	# swr code = 256 * p**2
      if power >= 2.0:
        swr = math.sqrt(swr / 256.0)
        swr = (1.0 + swr) / (1.0 - swr)
        if swr > 99.9:
          swr = 99.9
      else:
        swr = 0.0
      if param1[3] == 0:	# HiLoZ relay value
        t = "Zh"		# High
      else:
        t = "Zl"		# Low
      text = "Watts %.0f   SWR %.1f  %s Ind %d Cap %d   Freq %.0f (%d)" % (
         power, swr,  t, param1[1], param1[2], 20480000.0 / freq, freq)
    self.swr_label.SetLabel(text)
