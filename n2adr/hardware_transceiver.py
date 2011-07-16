# This is a sample hardware file for my 2010 transceiver.
# Use this for the HiQSDR.

import struct, socket
import _quisk as QS

from quisk_hardware_model import Hardware as BaseHardware

class Hardware(BaseHardware):
  def __init__(self, app, conf):
    BaseHardware.__init__(self, app, conf)
    self.use_sidetone = 1
    self.got_udp_status = ''	# status from UDP receiver
	# want_udp_status is a string with numbers in little-endian order:
	#	[0:2]		'St'
	#	[2:6]		Rx tune phase
	#	[6:10]		Tx tune phase
	#	[10:11]		Tx output level 0 to 255
	#	[11:12]		Tx control bits
    #		0	No transmit
    #		1	CW
    #		2	SSB and IMD
    #	[12:13]		Rx control bits
    #		Second stage decimation less one, 1-39, six bits
    #	[13:14]		zero
    self.rx_phase = 0
    self.tx_phase = 0
    self.tx_level = 0
    self.tx_control = 0
    self.rx_control = 0
    self.index = 0
    self.mode = None
    self.firmware_version = None	# firmware version is initially unknown
    self.is_spot = 0			# Are we in Spot mode?
    self.rx_udp_socket = None
    self.vfo_frequency = 0		# current vfo frequency
    self.tx_frequency = 0
    self.decimations = []		# supported decimation rates
    for dec in (40, 20, 10, 8, 5, 4, 2):
      self.decimations.append(dec * 64)
    if self.conf.fft_size_multiplier == 0:
      self.conf.fft_size_multiplier = 7		# Set size needed by VarDecim
  def open(self):
    self.rx_udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.rx_udp_socket.setblocking(0)
    # conf.rx_udp_port is used for returning ADC samples
    # conf.rx_udp_port + 1 is used for control
    self.rx_udp_socket.connect((self.conf.rx_udp_ip, self.conf.rx_udp_port + 1))
    return QS.open_rx_udp(self.conf.rx_udp_ip, self.conf.rx_udp_port)
  def close(self):
    if self.rx_udp_socket:
      self.rx_udp_socket.close()
      self.rx_udp_socket = None
  def ReturnFrequency(self):	# Return the current tuning and VFO frequency
    return None, None		# frequencies have not changed
  def ChangeFrequency(self, tx_freq, vfo_freq, source='', band='', event=None):
    if vfo_freq != self.vfo_frequency:
      self.vfo_frequency = vfo_freq
      self.rx_phase = int(float(vfo_freq) / self.conf.rx_udp_clock * 2.0**32 + 0.5) & 0xFFFFFFFF
    if tx_freq and tx_freq > 0:
      self.tx_frequency = tx_freq
      tx = tx_freq
      if self.is_spot:
        pass
      elif self.mode == 'USB':		# USB/LSB centered in passband
        tx += 1650			# move to carrier frequency
      elif self.mode == 'LSB':
        tx -= 1650
      self.tx_phase = int(float(tx) / self.conf.rx_udp_clock * 2.0**32 + 0.5) & 0xFFFFFFFF
    self.NewUdpStatus()
    return tx_freq, vfo_freq
  def ChangeMode(self, mode):
    # mode is a string: "USB", "AM", etc.
    self.mode = mode
    if mode in ("CWL", "CWU"):
      self.tx_control = 1
    elif mode in ("USB", "LSB", "AM", "FM"):
      self.tx_control = 2
    elif mode[0:3] == 'IMD':
      self.tx_control = 2
    else:
      self.tx_control = 0
    self.ChangeFrequency(self.tx_frequency, self.vfo_frequency)	# Change in mode may change frequency offset
  def ChangeBand(self, band):
    # band is a string: "60", "40", "WWV", etc.
    if band == '60':	# This band has a 50 watt maximum
      self.tx_level = 52
    else:
      self.tx_level = 120
    self.NewUdpStatus()
  def HeartBeat(self):
    try:	# receive the old status if any
      self.got_udp_status = self.rx_udp_socket.recv(1024)
    except:
      pass
    if self.want_udp_status[0:13] != self.got_udp_status[0:13]:
      try:
        self.rx_udp_socket.send(self.want_udp_status)
      except:
        pass
    elif self.firmware_version is None:
      self.firmware_version = ord(self.got_udp_status[13])	# Firmware version is returned here
  def GetFirmwareVersion(self):
    return self.firmware_version
  def OnSpot(self, mode):
    self.is_spot = mode
    self.ChangeFrequency(self.tx_frequency, self.vfo_frequency)	# Change in mode may change frequency offset
  def VarDecimGetChoices(self):		# return text labels for the control
    clock = self.conf.rx_udp_clock
    l = []			# a list of sample rates
    for dec in self.decimations:
      l.append(str(int(float(clock) / dec / 1e3 + 0.5)))
    return l
  def VarDecimGetLabel(self):		# return a text label for the control
    return "Sample rate ksps"
  def VarDecimGetIndex(self):		# return the current index
    return self.index
  def VarDecimSet(self, index=None):		# set decimation, return sample rate
    if index is None:		# initial call to set decimation before the call to open()
      rate = self.application.vardecim_set		# May be None or from different hardware
      try:
        dec = int(float(self.conf.rx_udp_clock / rate + 0.5))
        self.index = self.decimations.index(dec)
      except:
        try:
          self.index = self.decimations.index(self.conf.rx_udp_decimation)
        except:
          self.index = 0
    else:
      self.index = index
    dec = self.decimations[self.index]
    self.rx_control = dec / 64 - 1		# Second stage decimation less one
    self.NewUdpStatus()
    return int(float(self.conf.rx_udp_clock) / dec + 0.5)
  def NewUdpStatus(self, do_tx=False):
    s = "St"
    s = s + struct.pack("<L", self.rx_phase)
    s = s + struct.pack("<L", self.tx_phase)
    s = s + chr(self.tx_level) + chr(self.tx_control)
    s = s + chr(self.rx_control) + chr(0)
    self.want_udp_status = s
    if do_tx:
      try:
        self.rx_udp_socket.send(s)
      except:
        pass
