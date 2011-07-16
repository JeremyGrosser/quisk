# These are Quisk widgets

import sys
import wx, wx.lib.buttons, wx.lib.stattext
from types import *
# The main script will alter quisk_conf_defaults to include the user's config file.
import quisk_conf_defaults as conf

class FrequencyDisplay(wx.lib.stattext.GenStaticText):
  """Create a frequency display widget."""
  def __init__(self, frame, gbs, width, height):
    wx.lib.stattext.GenStaticText.__init__(self, frame, -1, '3',
         style=wx.ALIGN_CENTER|wx.ST_NO_AUTORESIZE)
    border = 4
    for points in range(30, 6, -1):
      font = wx.Font(points, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
      self.SetFont(font)
      w, h = self.GetTextExtent('333 444 555 Hz')
      if w < width and h < height - border * 2:
        break
    self.SetSizeHints(w, h, w * 5, h)
    self.height = h
    self.points = points
    border = self.border = (height - self.height) / 2
    self.height_and_border = h + border * 2
    self.SetBackgroundColour(conf.color_freq)
    gbs.Add(self, (0, 0), (1, 3),
       flag=wx.EXPAND | wx.TOP | wx.BOTTOM, border=border)
  def Clip(self, clip):
    """Change color to indicate clipping."""
    if clip:
      self.SetBackgroundColour('deep pink')
    else:
      self.SetBackgroundColour(conf.color_freq)
    self.Refresh()
  def Display(self, freq):
    """Set the frequency to be displayed."""
    freq = int(freq)
    if freq >= 0:
      t = str(freq)
      minus = ''
    else:
      t = str(-freq)
      minus = '- '
    l = len(t)
    if l > 9:
      txt = "%s%s %s %s %s" % (minus, t[0:-9], t[-9:-6], t[-6:-3], t[-3:])
    elif l > 6:
      txt = "%s%s %s %s" % (minus, t[0:-6], t[-6:-3], t[-3:])
    elif l > 3:
      txt = "%s%s %s" % (minus, t[0:-3], t[-3:])
    else:
      txt = minus + t
    self.SetLabel('%s Hz' % txt)

class SliderBoxV(wx.BoxSizer):
  """A vertical box containing a slider and a text heading"""
  # Note: A vertical wx slider has the max value at the bottom.  This is
  # reversed for this control.
  def __init__(self, parent, text, init, themax, handler, display=False):
    wx.BoxSizer.__init__(self, wx.VERTICAL)
    self.slider = wx.Slider(parent, -1, init, 0, themax, style=wx.SL_VERTICAL)
    self.slider.Bind(wx.EVT_SCROLL, handler)
    sw, sh = self.slider.GetSize()
    self.text = text
    self.themax = themax
    if display:		# Display the slider value when it is thumb'd
      self.text_ctrl = wx.StaticText(parent, -1, str(themax), style=wx.ALIGN_CENTER)
      w1, h1 = self.text_ctrl.GetSize()	# Measure size with max number
      self.text_ctrl.SetLabel(text)
      w2, h2 = self.text_ctrl.GetSize()	# Measure size with text
      self.width = max(w1, w2, sw)
      self.text_ctrl.SetSizeHints(self.width, -1, self.width)
      self.slider.Bind(wx.EVT_SCROLL_THUMBTRACK, self.Change)
      self.slider.Bind(wx.EVT_SCROLL_THUMBRELEASE, self.ChangeDone)
    else:
      self.text_ctrl = wx.StaticText(parent, -1, text)
      w2, h2 = self.text_ctrl.GetSize()	# Measure size with text
      self.width = max(w2, sw)
    self.Add(self.text_ctrl, 0, wx.ALIGN_CENTER)
    self.Add(self.slider, 1, wx.ALIGN_CENTER)
  def Change(self, event):
    event.Skip()
    self.text_ctrl.SetLabel(str(self.themax - self.slider.GetValue()))
  def ChangeDone(self, event):
    event.Skip()
    self.text_ctrl.SetLabel(self.text)
  def GetValue(self):
    return self.themax - self.slider.GetValue()
  def SetValue(self, value):
    # Set slider visual position; does not call handler
    self.slider.SetValue(self.themax - value)

class _QuiskText1(wx.lib.stattext.GenStaticText):
  # Self-drawn text for QuiskText.
  def __init__(self, parent, size_text, height, style):
    wx.lib.stattext.GenStaticText.__init__(self, parent, -1, '',
                 pos = wx.DefaultPosition, size = wx.DefaultSize,
                 style = wx.ST_NO_AUTORESIZE|style,
                 name = "QuiskText1")
    self.size_text = size_text
    self.pen = wx.Pen(conf.color_btn, 2)
    self.brush = wx.Brush(conf.color_freq)
    self.SetSizeHints(-1, height, -1, height)
  def _MeasureFont(self, dc, width, height):
    # Set decreasing point size until size_text fits in the space available
    for points in range(20, 6, -1):
      font = wx.Font(points, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
      dc.SetFont(font)
      w, h = dc.GetTextExtent(self.size_text)
      if w < width and h < height:
        break
    self.size_text = ''
    self.SetFont(font)
  def OnPaint(self, event):
    dc = wx.PaintDC(self)
    width, height = self.GetClientSize()
    if not width or not height:
      return
    dc.SetPen(self.pen)
    dc.SetBrush(self.brush)
    dc.DrawRectangle(1, 1, width-1, height-1)
    label = self.GetLabel()
    if not label:
      return
    if self.size_text:
      self._MeasureFont(dc, width-4, height-4)
    else:
      dc.SetFont(self.GetFont())
    if self.IsEnabled():
      dc.SetTextForeground(self.GetForegroundColour())
    else:
      dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
    style = self.GetWindowStyleFlag()
    w, h = dc.GetTextExtent(label)
    y = (height - h) / 2
    if y < 0:
      y = 0
    if style & wx.ALIGN_RIGHT:
      x = width - w - 4
    elif style & wx.ALIGN_CENTER:
      x = (width - w)/2
    else:
      x = 4
    dc.DrawText(label, x, y)

class QuiskText(wx.BoxSizer):
  # A one-line text display left/right/center justified and vertically centered.
  # The height of the control is fixed as "height".  The width is expanded.
  # The font is chosen so size_text fits in the client area.
  def __init__(self, parent, size_text, height, style=0):
    wx.BoxSizer.__init__(self, wx.HORIZONTAL)
    self.TextCtrl = _QuiskText1(parent, size_text, height, style)
    self.Add(self.TextCtrl, 1, flag=wx.ALIGN_LEFT|wx.ALIGN_CENTER_VERTICAL)
  def SetLabel(self, label):
    self.TextCtrl.SetLabel(label)

# Start of our button classes.  They are compatible with wxPython GenButton
# buttons.  Use the usual methods for access:
# GetLabel(self), SetLabel(self, label):	Get and set the label
# Enable(self, flag), Disable(self), IsEnabled(self):	Enable / Disable
# GetValue(self), SetValue(self, value):	Get / Set check button state True / False
# SetIndex(self, index):	For cycle buttons, set the label from its index

class QuiskButtons:
  """Base class for special buttons."""
  button_bezel = 3		# size of button bezel in pixels
  def InitButtons(self, text):
    self.SetBezelWidth(self.button_bezel)
    self.SetBackgroundColour(conf.color_btn)
    self.SetUseFocusIndicator(False)
    self.font = wx.Font(10, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    self.SetFont(self.font)
    if text:
      w, h = self.GetTextExtent(text)
    else:
      w, h = self.GetTextExtent("OK")
      self.Disable()	# create a size for null text, but Disable()
    w += self.button_bezel * 2 + self.GetCharWidth()
    h = h * 12 / 10
    h += self.button_bezel * 2
    self.SetSizeHints(w, h, w * 6, h, 1, 1)
  def DrawLabel(self, dc, width, height, dx=0, dy=0):	# Override to change Disable text color
      dc.SetFont(self.GetFont())
      if self.IsEnabled():
          dc.SetTextForeground(self.GetForegroundColour())
      else:
          dc.SetTextForeground(conf.color_disable)
          #dc.SetTextForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_GRAYTEXT))
      label = self.GetLabel()
      tw, th = dc.GetTextExtent(label)
      if not self.up:
          dx = dy = self.labelDelta
      dc.DrawText(label, (width-tw)/2+dx, (height-th)/2+dy)
  def OnKeyDown(self, event):
    pass
  def OnKeyUp(self, event):
    pass

class QuiskPushbutton(QuiskButtons, wx.lib.buttons.GenButton):
  """A plain push button widget."""
  def __init__(self, parent, command, text, use_right=False):
    wx.lib.buttons.GenButton.__init__(self, parent, -1, text)
    self.command = command
    self.Bind(wx.EVT_BUTTON, self.OnButton)
    self.InitButtons(text)
    self.direction = 1
    if use_right:
      self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
      self.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
  def OnButton(self, event):
    if self.command:
      self.command(event)
  def OnRightDown(self, event):
    self.direction = -1
    self.OnLeftDown(event) 
  def OnRightUp(self, event):
    self.OnLeftUp(event)
    self.direction = 1
      

class QuiskRepeatbutton(QuiskButtons, wx.lib.buttons.GenButton):
  """A push button that repeats when held down."""
  def __init__(self, parent, command, text, up_command=None, use_right=False):
    wx.lib.buttons.GenButton.__init__(self, parent, -1, text)
    self.command = command
    self.up_command = up_command
    self.timer = wx.Timer(self)
    self.Bind(wx.EVT_TIMER, self.OnTimer)
    self.Bind(wx.EVT_BUTTON, self.OnButton)
    self.InitButtons(text)
    self.repeat_state = 0		# repeater button inactive
    self.direction = 1
    if use_right:
      self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
      self.Bind(wx.EVT_RIGHT_UP, self.OnRightUp)
  def SendCommand(self, command):
    if command:
      event = wx.PyEvent()
      event.SetEventObject(self)
      command(event)
  def OnLeftDown(self, event):
    if self.IsEnabled():
      self.shift = event.ShiftDown()
      self.control = event.ControlDown()
      self.SendCommand(self.command)
      self.repeat_state = 1		# first button push
      self.timer.Start(milliseconds=300, oneShot=True)
    wx.lib.buttons.GenButton.OnLeftDown(self, event)
  def OnLeftUp(self, event):
    if self.IsEnabled():
      self.SendCommand(self.up_command)
      self.repeat_state = 0
      self.timer.Stop()
    wx.lib.buttons.GenButton.OnLeftUp(self, event)
  def OnRightDown(self, event):
    if self.IsEnabled():
      self.shift = event.ShiftDown()
      self.control = event.ControlDown()
      self.direction = -1
      self.OnLeftDown(event) 
  def OnRightUp(self, event):
    if self.IsEnabled():
      self.OnLeftUp(event)
      self.direction = 1
  def OnTimer(self, event):
    if self.repeat_state == 1:	# after first push, turn on repeats
      self.timer.Start(milliseconds=150, oneShot=False)
      self.repeat_state = 2
    if self.repeat_state:		# send commands until button is released
      self.SendCommand(self.command)
  def OnButton(self, event):
    pass	# button command not used

class QuiskCheckbutton(QuiskButtons, wx.lib.buttons.GenToggleButton):
  """A button that pops up and down, and changes color with each push."""
  # Check button; get the checked state with self.GetValue()
  def __init__(self, parent, command, text, color=None):
    wx.lib.buttons.GenToggleButton.__init__(self, parent, -1, text)
    self.InitButtons(text)
    self.Bind(wx.EVT_BUTTON, self.OnButton)
    self.button_down = 0		# used for radio buttons
    self.command = command
    if color is None:
      self.color = conf.color_check_btn
    else:
      self.color = color
  def SetValue(self, value, do_cmd=False):
    wx.lib.buttons.GenToggleButton.SetValue(self, value)
    self.button_down = value
    if value:
      self.SetBackgroundColour(self.color)
    else:
      self.SetBackgroundColour(conf.color_btn)
    if do_cmd and self.command:
      event = wx.PyEvent()
      event.SetEventObject(self)
      self.command(event)
  def OnButton(self, event):
    if self.GetValue():
      self.SetBackgroundColour(self.color)
    else:
      self.SetBackgroundColour(conf.color_btn)
    if self.command:
      self.command(event)

class QFilterButtonWindow(wx.Frame):
  """Create a window with controls for the button"""
  def __init__(self, button):
    self.button = button
    l = self.valuelist = []
    value = 10
    incr = 10
    for i in range(0, 101):
      l.append(value)
      value += incr
      if value == 100:
        incr = 20
      elif value == 500:
        incr = 50
      elif value == 1000:
        incr = 100
      elif value == 5000:
        incr = 500
      elif value == 10000:
        incr = 1000
    x, y = button.GetPositionTuple()
    x, y = button.GetParent().ClientToScreenXY(x, y)
    w, h = button.GetSize()
    height = h * 10
    size = (w, height)
    if sys.platform == 'win32':
      pos = (x, y - height)
      t = 'Filter'
    else:
      pos = (x, y - height - h)
      t = ''
    wx.Frame.__init__(self, button.GetParent(), -1, t, pos, size,
      wx.FRAME_TOOL_WINDOW|wx.FRAME_FLOAT_ON_PARENT|wx.CLOSE_BOX|wx.CAPTION|wx.SYSTEM_MENU)
    self.SetBackgroundColour(conf.color_freq)
    self.Bind(wx.EVT_CLOSE, self.OnClose)
    value = int(button.GetLabel())
    try:
      index = 100 - self.valuelist.index(value)
    except ValueError:
      index = 0
    self.slider = wx.Slider(self, -1, index, 0, 100, (0, 0), (w/2, height), wx.SL_VERTICAL)
    self.slider.Bind(wx.EVT_SCROLL, self.OnSlider)
    self.Show()
    self.slider.SetFocus()
  def OnSlider(self, event):
    value = self.slider.GetValue()
    value = 100 - value
    value = self.valuelist[value]
    self.button.SetLabel(str(value))
    self.button.Refresh()
    self.button.SetValue(True, True)
    application.filterAdjBw1 = value
  def OnClose(self, event):
    self.button.adjust = None
    self.Destroy()

class QuiskFilterButton(QuiskCheckbutton):
  """An adjustable check button; right-click to adjust."""
  def __init__(self, parent, command, text, color=None):
    if color is None:
      color = conf.color_adjust_btn
    QuiskCheckbutton.__init__(self, parent, command, text, color)
    self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
    self.adjust = None
  def OnRightDown(self, event):
    self.OnButton(event)
    if self.adjust:
      self.adjust.Destroy()
      self.adjust = None
    else:
      self.adjust = QFilterButtonWindow(self)

class QuiskCycleCheckbutton(QuiskCheckbutton):
  """A button that cycles through its labels with each push.

  The button is up for labels[0], down for all other labels.  Change to the
  next label for each push.  If you call SetLabel(), the label must be in the list.
  The self.index is the index of the current label.
  """
  def __init__(self, parent, command, labels, color=None, is_radio=False):
    self.labels = list(labels)		# Be careful if you change this list
    self.index = 0		# index of selected label 0, 1, ...
    self.direction = 0	# 1 for up, -1 for down, 0 for no change to index
    self.is_radio = is_radio	# Is this a radio cycle button?
    if color is None:
      color = conf.color_cycle_btn
    QuiskCheckbutton.__init__(self, parent, command, labels[0], color)
    self.Bind(wx.EVT_RIGHT_DOWN, self.OnRightDown)
    self.Bind(wx.EVT_LEFT_DCLICK, self.OnLeftDclick)
  def SetLabel(self, label, do_cmd=False):
    self.index = self.labels.index(label)
    QuiskCheckbutton.SetLabel(self, label)
    QuiskCheckbutton.SetValue(self, self.index)
    if do_cmd and self.command:
      event = wx.PyEvent()
      event.SetEventObject(self)
      self.command(event)
  def SetIndex(self, index, do_cmd=False):
    self.index = index
    QuiskCheckbutton.SetLabel(self, self.labels[index])
    QuiskCheckbutton.SetValue(self, index)
    if do_cmd and self.command:
      event = wx.PyEvent()
      event.SetEventObject(self)
      self.command(event)
  def OnButton(self, event):
    if not self.is_radio or self.button_down:
      self.direction = 1
      self.index += 1
      if self.index >= len(self.labels):
        self.index = 0
      self.SetIndex(self.index)
    else:
      self.direction = 0
    if self.command:
      self.command(event)
  def OnRightDown(self, event):		# Move left in the list of labels
    if not self.is_radio or self.GetValue():
      self.index -= 1
      if self.index < 0:
        self.index = len(self.labels) - 1
      self.SetIndex(self.index)
      self.direction = -1
      if self.command:
        self.command(event)
  def OnLeftDclick(self, event):	# Left double-click: Set index zero
    if not self.is_radio or self.GetValue():
      self.index = 0
      self.SetIndex(self.index)
      self.direction = 1
      if self.command:
        self.command(event)

class RadioButtonGroup:
  """This class encapsulates a group of radio buttons.  This class is not a button!

  The "labels" is a list of labels for the toggle buttons.  An item
  of labels can be a list/tuple, and the corresponding button will
  be a cycle button.  If a label is 'var', the button is a check-adjust button.
  """
  def __init__(self, parent, command, labels, default):
    self.command = command
    self.buttons = []
    self.button = None
    for text in labels:
      if type(text) in (ListType, TupleType):
        b = QuiskCycleCheckbutton(parent, self.OnButton, text, is_radio=True)
        for t in text:
          if t == default and self.button is None:
            b.SetLabel(t)
            self.button = b
      elif text == '_filter_':
        b = QuiskFilterButton(parent, self.OnButton, str(application.filterAdjBw1))
        if text == default and self.button is None:
          b.SetValue(True)
          self.button = b
      else:
        b = QuiskCheckbutton(parent, self.OnButton, text)
        if text == default and self.button is None:
          b.SetValue(True)
          self.button = b
      self.buttons.append(b)
  def SetLabel(self, label, do_cmd=False):
    self.button = None
    for b in self.buttons:
      if self.button is not None:
        b.SetValue(False)
      elif isinstance(b, QuiskCycleCheckbutton):
        try:
          index = b.labels.index(label)
        except ValueError:
          b.SetValue(False)
          continue
        else:
          b.SetIndex(index)
          self.button = b
          b.SetValue(True)
      elif b.GetLabel() == label:
        b.SetValue(True)
        self.button = b
      else:
        b.SetValue(False)
    if do_cmd and self.command and self.button:
      event = wx.PyEvent()
      event.SetEventObject(self.button)
      self.command(event)
  def GetButtons(self):
    return self.buttons
  def OnButton(self, event):
    win = event.GetEventObject()
    for b in self.buttons:
      if b is win:
        self.button = b
        b.SetValue(True)
      else:
        b.SetValue(False)
    if self.command:
      self.command(event)
  def GetLabel(self):
    if not self.button:
      return None
    return self.button.GetLabel()
  def GetSelectedButton(self):		# return the selected button
    return self.button

class FreqSetter(wx.TextCtrl):
  def __init__(self, parent, x, y, label, fmin, fmax, freq, command):
    self.pos = (x, y)
    self.label = label
    self.fmin = fmin
    self.fmax = fmax
    self.command = command
    self.font = wx.Font(16, wx.FONTFAMILY_SWISS, wx.NORMAL, wx.FONTWEIGHT_NORMAL)
    t = wx.StaticText(parent, -1, label, pos=(x, y))
    t.SetFont(self.font)
    freq_w, freq_h = t.GetTextExtent(" 662 000 000")
    tw, th = t.GetSizeTuple()
    x += tw + 20
    wx.TextCtrl.__init__(self, parent, size=(freq_w, freq_h), pos=(x, y),
      style=wx.TE_RIGHT|wx.TE_PROCESS_ENTER)
    self.SetFont(self.font)
    self.Bind(wx.EVT_TEXT, self.OnText)
    self.Bind(wx.EVT_TEXT_ENTER, self.OnEnter)
    w, h = self.GetSizeTuple()
    x += w + 1
    self.butn = b = wx.SpinButton(parent, size=(freq_h, freq_h), pos=(x, y))
    w, h = b.GetSizeTuple()
    self.end_pos = (x + w, y + h)
    b.Bind(wx.EVT_SPIN, self.OnSpin)	# The spin button frequencies are in kHz
    b.SetMin(fmin / 1000)
    b.SetMax(fmax / 1000)
    self.SetValue(freq)
  def OnText(self, event):
    self.SetBackgroundColour('pink')
  def OnEnter(self, event):
    text = wx.TextCtrl.GetValue(self)
    text = text.replace(' ', '')
    if '-' in text:
      return
    try:
      if '.' in text:
        freq = int(float(text) * 1000000 + 0.5)
      else:
        freq = int(text)
    except:
      return
    self.SetValue(freq)
    self.command(self)
  def OnSpin(self, event):
    freq = self.butn.GetValue() * 1000
    self.SetValue(freq)
    self.command(self)
  def SetValue(self, freq):
    if freq < self.fmin:
      freq = self.fmin
    elif freq > self.fmax:
      freq = self.fmax
    self.butn.SetValue(freq / 1000)
    v = str(freq)
    i = len(v)
    if i > 6:
      wx.TextCtrl.SetValue(self, "%s %s %s" % (v[0:i-6], v[-6:-3], v[-3:]))
    elif i > 3:
      wx.TextCtrl.SetValue(self, "%s %s" % (v[0:i-3], v[-3:]))
    else:
      wx.TextCtrl.SetValue(self, v)
    self.SetBackgroundColour(conf.color_entry)
  def GetValue(self):
    value = wx.TextCtrl.GetValue(self)
    value = value.replace(' ', '')
    try:
      value = int(value)
    except:
      value = 7000
    return value
