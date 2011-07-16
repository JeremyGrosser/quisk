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
    b = app.QuiskCycleCheckbutton(frame, self.OnBtnSpot,
       ('Spot', 'Spot -6db', 'Spot 0db'), color=conf.color_test)
    gbs.Add(b, (4, 0), flag=wx.EXPAND)
    bw, bh = b.GetMinSize()
    b = app.QuiskCheckbutton(frame, self.OnBtnPTT, text='PTT', color='red')
    gbs.Add(b, (4, 1), (1, 2), flag=wx.EXPAND)
    self.info_text = app.QuiskText(frame, 'Info', bh)
    gbs.Add(self.info_text, (4, 7), (1, 6), flag=wx.EXPAND)
  def OnBtnSpot(self, event):
    btn = event.GetEventObject()
    QS.set_spot_mode(btn.index)
  def OnBtnPTT(self, event):
    if event.GetEventObject().GetValue():
      self.hardware.OnPTT(1)
    else:
      self.hardware.OnPTT(0)

