# Please do not change this hardware control module for Quisk.
# It provides USB control of SoftRock hardware.

import struct, threading, time, traceback, math
from quisk_hardware_model import Hardware as BaseHardware
import _quisk as QS

# All USB access is through control transfers using pyusb.
#   byte_array      = dev.ctrl_transfer (IN,  bmRequest, wValue, wIndex, length, timout)
#   len(string_msg) = dev.ctrl_transfer (OUT, bmRequest, wValue, wIndex, string_msg, timout)

import usb.core, usb.util

DEBUG = 0

# I2C-address of the SI570;  Thanks to Joachim Schneider, DB6QS
si570_i2c_address = 0x55

# Thanks to Ethan Blanton, KB8OJH, for this patch for the Si570 (many SoftRocks):
# These are used by SetFreqByDirect(); see below.
# The Si570 DCO must be clamped between these values
SI570_MIN_DCO = 4.85e9
SI570_MAX_DCO = 5.67e9
# The Si570 has 6 valid HSDIV values.  Subtract 4 from HSDIV before
# stuffing it.  We want to find the highest HSDIV first, so start
# from 11.
SI570_HSDIV_VALUES = [11, 9, 7, 6, 5, 4]

IN =  usb.util.build_request_type(usb.util.CTRL_IN,  usb.util.CTRL_TYPE_VENDOR, usb.util.CTRL_RECIPIENT_DEVICE)
OUT = usb.util.build_request_type(usb.util.CTRL_OUT, usb.util.CTRL_TYPE_VENDOR, usb.util.CTRL_RECIPIENT_DEVICE)

UBYTE2 = struct.Struct('<H')
UBYTE4 = struct.Struct('<L')	# Thanks to Sivan Toledo

class Hardware(BaseHardware):
  def __init__(self, app, conf):
    BaseHardware.__init__(self, app, conf)
    self.usb_dev = None
    self.vfo = None
    self.key_thread = None
    self.name_of_mic_play = conf.name_of_mic_play	# True if we can transmit
  def open(self):			# Called once to open the Hardware
    # find our device
    self.usb_dev = usb.core.find(idVendor=self.conf.usb_vendor_id, idProduct=self.conf.usb_product_id)
    if self.usb_dev is None:
      text = 'USB device not found VendorID 0x%X ProductID 0x%X' % (
          self.conf.usb_vendor_id, self.conf.usb_product_id)
      self.application.sound_error = 1
    else:
      try:
        self.usb_dev.set_configuration()
        ret = self.usb_dev.ctrl_transfer(IN, 0x00, 0x0E00, 0, 2)
      except:
        text = "No permission to access the SoftRock USB interface"
        self.application.sound_error = 1
        self.usb_dev = None
      else:
        if len(ret) == 2:
          ver = "%d.%d" % (ret[1], ret[0])
        else:
          ver = 'unknown'
        text = 'Capture from SoftRock USB on %s, Firmware %s' % (self.conf.name_of_sound_capt , ver)
        if self.name_of_mic_play and self.conf.key_poll_msec:
          self.key_thread = KeyThread(self.usb_dev, self.conf.key_poll_msec / 1000.0)
          self.key_thread.start()
    if self.name_of_mic_play:
      self.application.bottom_widgets.info_text.SetLabel(text)
    if DEBUG:
      print 'Startup freq', self.GetStartupFreq()
      print 'Run freq', self.GetFreq()
      print 'Address 0x%X' % self.usb_dev.ctrl_transfer(IN, 0x41, 0, 0, 1)[0]
      sm = self.usb_dev.ctrl_transfer(IN, 0x3B, 0, 0, 2)
      sm = UBYTE2.unpack(sm)[0]
      print 'Smooth tune', sm
    return text
  def close(self):			# Called once to close the Hardware
    if self.key_thread:
      self.key_thread.stop()
      self.key_thread = None
  def ChangeFrequency(self, tune, vfo, source='', band='', event=None):
    if self.usb_dev and self.vfo != vfo:
      if self.conf.si570_direct_control:
        if self.SetFreqByDirect(vfo):
          self.vfo = vfo
      elif self.SetFreqByValue(vfo):
         self.vfo = vfo
      if DEBUG:
        print 'Change to', vfo
        print 'Run freq', self.GetFreq()
    return tune, vfo
  def ReturnFrequency(self):
    # Return the current tuning and VFO frequency.  If neither have changed,
    # you can return (None, None).  This is called at about 10 Hz by the main.
    # return (tune, vfo)	# return changed frequencies
    return None, None		# frequencies have not changed
  def ChangeMode(self, mode):		# Change the tx/rx mode
    # mode is a string: "USB", "AM", etc.
    pass
  def ChangeBand(self, band):
    # band is a string: "60", "40", "WWV", etc.
    pass
  def HeartBeat(self):	# Called at about 10 Hz by the main
    pass
  def OnPTT(self, ptt):
    if self.key_thread:
      self.key_thread.OnPTT(ptt)
    elif self.usb_dev:
      QS.set_key_down(ptt)
      try:
        self.usb_dev.ctrl_transfer(IN, 0x50, ptt, 0, 3)
      except usb.core.USBError:
        QS.set_key_down(0)
        if DEBUG: traceback.print_exc()
  def GetStartupFreq(self):	# return the startup frequency / 4
    if not self.usb_dev:
      return 0
    ret = self.usb_dev.ctrl_transfer(IN, 0x3C, 0, 0, 4)
    s = ret.tostring()
    freq = UBYTE4.unpack(s)[0]
    freq = int(freq * 1.0e6 / 2097152.0 / 4.0 + 0.5)
    return freq
  def GetFreq(self):	# return the running frequency / 4
    if not self.usb_dev:
      return 0
    ret = self.usb_dev.ctrl_transfer(IN, 0x3A, 0, 0, 4)
    s = ret.tostring()
    freq = UBYTE4.unpack(s)[0]
    freq = int(freq * 1.0e6 / 2097152.0 / 4.0 + 0.5)
    return freq
  def SetFreqByValue(self, freq):
    freq = int(freq/1.0e6 * 2097152.0 * 4.0 + 0.5)
    s = UBYTE4.pack(freq)
    try:
      self.usb_dev.ctrl_transfer(OUT, 0x32, si570_i2c_address + 0x700, 0, s)
    except usb.core.USBError:
      if DEBUG: traceback.print_exc()
    else:
      return True
  def SetFreqByDirect(self, freq):	# Thanks to Ethan Blanton, KB8OJH
    if freq == 0.0:
      return False
    # For now, find the minimum DCO speed that will give us the
    # desired frequency; if we're slewing in the future, we want this
    # to additionally yield an RFREQ ~= 512.
    freq = int(freq * 4)
    dco_new = None
    hsdiv_new = 0
    n1_new = 0
    for hsdiv in SI570_HSDIV_VALUES:
      n1 = int(math.ceil(SI570_MIN_DCO / (freq * hsdiv)))
      if n1 < 1:
        n1 = 1
      else:
        n1 = ((n1 + 1) / 2) * 2
      dco = (freq * 1.0) * hsdiv * n1
      # Since we're starting with max hsdiv, this can only happen if
      # freq was larger than we can handle
      if n1 > 128:
        continue
      if dco < SI570_MIN_DCO or dco > SI570_MAX_DCO:
        # This really shouldn't happen
        continue
      if not dco_new or dco < dco_new:
        dco_new = dco
        hsdiv_new = hsdiv
        n1_new = n1
    if not dco_new:
      # For some reason, we were unable to calculate a frequency.
      # Probably because the frequency requested is outside the range
      # of our device.
      return False		# Failure
    rfreq = dco_new / self.conf.si570_xtal_freq
    rfreq_int = int(rfreq)
    rfreq_frac = int(round((rfreq - rfreq_int) * 2**28))
    # It looks like the DG8SAQ protocol just passes r7-r12 straight
    # To the Si570 when given command 0x30.  Easy enough.
    # n1 is stuffed as n1 - 1, hsdiv is stuffed as hsdiv - 4.
    hsdiv_new = hsdiv_new - 4
    n1_new = n1_new - 1
    s = struct.Struct('>BBL').pack((hsdiv_new << 5) + (n1_new >> 2),
                                   ((n1_new & 0x3) << 6) + (rfreq_int >> 4),
                                   ((rfreq_int & 0xf) << 28) + rfreq_frac)
    self.usb_dev.ctrl_transfer(OUT, 0x30, si570_i2c_address + 0x700, 0, s)
    return True		# Success

class KeyThread(threading.Thread):
  """Create a thread to monitor the key state."""
  def __init__(self, dev, poll_secs):
    self.usb_dev = dev
    self.poll_secs = poll_secs
    self.ptt = 0
    self.key_down = 0
    threading.Thread.__init__(self)
    self.doQuit = threading.Event()
    self.doQuit.clear()
  def run(self):
    while not self.doQuit.isSet():
      try:
        if self.ptt:
          key_down = 1
        else:		# read key state
          ret = self.usb_dev.ctrl_transfer(IN, 0x51, 0, 0, 1)
          # bit 0x20 is the tip, bit 0x02 is the ring
          if ret[0] & 0x20:		# Tip: key is up
            key_down = 0
          else:			# key is down
            key_down = 1
        if key_down != self.key_down:
          self.key_down = key_down
          self.usb_dev.ctrl_transfer(IN, 0x50, key_down, 0, 3)
          QS.set_key_down(key_down)
      except usb.core.USBError:
        QS.set_key_down(0)
        if DEBUG: traceback.print_exc()
      time.sleep(self.poll_secs)
  def stop(self):
    """Set a flag to indicate that the thread should end."""
    self.doQuit.set()
  def OnPTT(self, ptt):
    self.ptt = ptt
