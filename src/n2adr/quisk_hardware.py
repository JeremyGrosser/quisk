# This is the hardware module used at my shack.  It is a complicated module
# that controls various hardware.  See the other hardware files for more
# basic use.

import sys, struct, math, socket, select, thread, time
import _quisk as QS

DEBUG = 0

from quisk_hardware_model import Hardware as BaseHardware

UseSdriq = None
UseRxudp = None
Application = None
Config = None

# This hardware file controls my station.  There are several
# possible transmitters and receivers that can be selected.
class Hardware(BaseHardware):
  def __init__(self, app, conf):
    BaseHardware.__init__(self, app, conf)
    global UseSdriq, UseRxudp, Application, Config
    Application = app
    Config = conf
    UseSdriq = conf.use_sdriq
    UseRxudp = conf.use_rx_udp
    self.use_sidetone = 1
    self.vfo_frequency = 0		# current vfo frequency
    # Select receiver
    if conf.use_rx_udp:
      from n2adr import hardware_transceiver
      self.receiver = hardware_transceiver.Hardware(app, conf)
      self.rf_gain_labels = ('RF 0 dB', 'RF +16', 'RF -20', 'RF -10')
    elif UseSdriq:
      from sdriqpkg import quisk_hardware as quisk_hardware_sdriq
      self.receiver = quisk_hardware_sdriq.Hardware(app, conf)
      self.rf_gain_labels = self.receiver.rf_gain_labels
    else:
      self.receiver = HwRxEthVfo()
      self.rf_gain_labels = ('RF 0 dB', 'RF +16', 'RF -20', 'RF -10')
    # Select transmitter
    if conf.use_rx_udp:
      self.transmitter = self.receiver		# this is a transceiver
    elif Config.tx_ip:
      self.transmitter =  HwTx2007()
    else:
      self.transmitter =  BaseHardware(app, conf)
    # Other hardware
    self.anttuner = AntennaTuner()	# Control the antenna tuner
    self.lpfilter = LowPassFilter()		# Control LP filter box
    self.hpfilter = HighPassFilter()	# Control HP filter box
    #self.antenna = AntennaControl(self.AntCtrlAddress)		# Control antenna
  def open(self):
    if self.transmitter is not self.receiver:
      self.transmitter.open()
    self.anttuner.open()
    return self.receiver.open()
  def close(self):
    if self.transmitter is not self.receiver:
      self.transmitter.close()
    self.anttuner.close()
    self.receiver.close()
  def ReturnFrequency(self):	# Return the current tuning and VFO frequency
    return None, None		# frequencies have not changed
  def ChangeFilterFrequency(self, tx_freq):
    # Change the filters but not the receiver; used for panadapter
    if tx_freq and tx_freq > 0:
      self.anttuner.SetTxFreq(tx_freq)
      self.lpfilter.SetTxFreq(tx_freq)
      self.hpfilter.SetTxFreq(tx_freq)
      #self.antenna.SetTxFreq(tx_freq)
  def ChangeFrequency(self, tx_freq, vfo_freq, source='', band='', event=None):
    self.receiver.ChangeFrequency(tx_freq, vfo_freq, source, band, event)
    if self.transmitter is not self.receiver:
      self.transmitter.ChangeFrequency(tx_freq, vfo_freq, source, band, event)
    if tx_freq and tx_freq > 0:
      self.anttuner.SetTxFreq(tx_freq)
      self.lpfilter.SetTxFreq(tx_freq)
      self.hpfilter.SetTxFreq(tx_freq)
      #self.antenna.SetTxFreq(tx_freq)
    return tx_freq, vfo_freq
  def ChangeMode(self, mode):
    # mode is a string: "USB", "AM", etc.
    #if mode[0:3] == 'IMD':
    #  QS.set_fdx(1)
    #else:
    #  QS.set_fdx(0)
    self.receiver.ChangeMode(mode)
    self.transmitter.ChangeMode(mode)
  def ChangeBand(self, band):
    # band is a string: "60", "40", "WWV", etc.
    self.receiver.ChangeBand(band)
    self.transmitter.ChangeBand(band)
    self.anttuner.ChangeBand(band)
    self.lpfilter.ChangeBand(band)
    self.hpfilter.ChangeBand(band)
    #self.antenna.ChangeBand(band)
  def HeartBeat(self):	# Called at about 10 Hz by the main
    self.receiver.HeartBeat()
    if self.transmitter != self.receiver:
      self.transmitter.HeartBeat()
    self.anttuner.HeartBeat()
    self.lpfilter.HeartBeat()
    self.hpfilter.HeartBeat()
    #self.antenna.HeartBeat()
  def OnSpot(self, mode):
    self.anttuner.OnSpot(mode)
    self.transmitter.OnSpot(mode)
  def OnButtonRfGain(self, event):
    if UseSdriq:
      self.receiver.OnButtonRfGain(event)
    else:
      if self.hpfilter:
        self.hpfilter.OnButtonRfGain(event)
  def GetFirmwareVersion(self):
    if UseRxudp:
      return self.receiver.firmware_version
    return 0
  def VarDecimGetChoices(self):
    return self.receiver.VarDecimGetChoices()
  def VarDecimGetLabel(self):
    return self.receiver.VarDecimGetLabel()
  def VarDecimGetIndex(self):
    return self.receiver.VarDecimGetIndex()
  def VarDecimSet(self, index=None):
    return self.receiver.VarDecimSet(index)

class HwTx2007:
  tx_program_port = 0x553A
  tx_dds_clock = 89999784.E0
  def __init__(self):
    self.vfo_frequency = 0
    self.tx_frequency = 0
    self.mode = None
    self.thread_running = 0
    self.want_prog_num = 0
    self.got_ack = None				# last received ACK number
    self.got_status = None			# last received status
    self.thread_msg = ''
    self.is_spot = 0			# Are we in Spot mode?
  def open(self):
    self.tx_program_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.tx_program_socket.setblocking(0)
    self.tx_program_socket.connect((Config.tx_ip, self.tx_program_port))
  def close(self):
    self.tx_program_socket.close()
  def RequestStatus(self, wait=1):	# Request status
    self.got_status = None
    while 1:		# Get all status responses
      if not self.RecvTx(0.0):
        break
    if wait:	# wait for a response
      self.got_status = None	# Get the new status
      if self.SendTx('\001s') != 2:
        return	# Failure
      self.RecvTx(0.500)
      if not self.got_status:
        self.RecvTx(0.500)
        if not self.got_status:
          return		# Failure
      return 1	# Success
    else:
      if self.SendTx('\001s') == 2:
        return 1	# Success
  def RecvTx(self, seconds):	# receive data, wait seconds (e.g. 0.400)
    s = self.tx_program_socket
    if not s:
      return ''
    try:
      r, w, x = select.select([s], [], [], seconds)
    except:
      return ''
    if r:
      try:
        data = s.recv(1024)
      except:
        return ''
    else:
      return ''
    if data:
      if data[0] == '\003' and len(data) >= 10 and data[1] == '\001':	# got Status
        self.got_status = map(ord, data[2:])
      elif data[0] == '\004':	# got ACK
        self.got_ack = ord(data[1])
    return data
  def SendTx(self, msg):
    s = self.tx_program_socket
    if not s:
      return 0
    try:
      return s.send(msg)
    except:
      return 0
  def ProgramTx(self, prog_num):	# Send an FGPA program to the transmitter
    BLOCK_SIZE = 512			# data size
    s = self.tx_program_socket
    if not s:
      return 0
    if sys.platform[0:3] == 'win':
      FILE1 = "C:/Documents and Settings/jim/My Documents/Altera/duc1cw/duc1cw.rbf"
      FILE2 = "C:/Documents and Settings/jim/My Documents/Altera/fpga2tone/fpga2tone.rbf"
      FILE3 = "C:/Documents and Settings/jim/My Documents/Altera/duc1/duc1.rbf"
    else:
      FILE1 = "/C/Documents and Settings/jim/My Documents/Altera/duc1cw/duc1cw.rbf"
      FILE2 = "/C/Documents and Settings/jim/My Documents/Altera/fpga2tone/fpga2tone.rbf"
      FILE3 = "/C/Documents and Settings/jim/My Documents/Altera/duc1/duc1.rbf"
    if prog_num == 0:		# Remove FPGA program
      self.SendTx('\002p\000')
      self.SendTx('\003\001')
      return 1
    elif prog_num == 1:
      fp = file(FILE1, "rb")
    elif prog_num == 2:
      fp = file(FILE2, "rb")
    elif prog_num == 3:
      fp = file(FILE3, "rb")
    else:
      return 0
    block = 0
    while 1:		# Throw away any pending data
      if not self.RecvTx(0.0):
        break
    self.got_ack = None
    data = '\002p%c' % chr(prog_num)
    self.SendTx(data)		# WRQ program number
    theend = 0
    while 1:
      if self.want_prog_num != prog_num:	# Change in program
        return 0
      self.RecvTx(0.500)
      if self.got_ack != block:
        self.SendTx(data)
        self.RecvTx(0.500)
        if self.got_ack != block:
          fp.close()
          return 0
        self.RecvTx(0.100)
      if theend:
        break
      block = (block + 1) % 256
      data = '\003' + chr(block) + fp.read(BLOCK_SIZE)
      self.SendTx(data)		# send DATA
      if len(data) < BLOCK_SIZE + 2:
        theend = 1
    fp.close()
    # Success; send frequency
    if self.tx_frequency:
      self.ChangeFrequency(self.tx_frequency, self.vfo_frequency)
    return 1
  def ChangeProgNum(self):
    # status[6] is the current program number.
    # status[7] is a flag field and 0x3 must be set to indicate successful programming.
    # prog_num zero means no program and then status[7] is irrelevant.
    try:
      for i in range(0, 5):
        if self.RequestStatus():
          if self.got_status[6] == 0:
            self.thread_msg = 'Program number is zero'
          if self.want_prog_num == 0 and self.got_status[6] == 0:
            break		# Success
          if self.want_prog_num == self.got_status[6] and self.got_status[7] & 0x3 == 0x3:
            break		# Success
          self.ProgramTx(self.want_prog_num)	# Re-program
      else:
        self.ProgramTx(0)
        return 1		# Failure
    finally:
      self.thread_running = 0
  def ChangeFrequency(self, tx_freq, vfo_freq, source='', band='', event=None):
    self.vfo_frequency = vfo_freq
    if tx_freq and tx_freq > 0:
      self.tx_frequency = tx_freq
      if self.is_spot:
        pass
      elif self.mode == 'USB':	# USB/LSB centered in passband
        tx_freq += 1650			# move to carrier frequency
      elif self.mode == 'LSB':
        tx_freq -= 1650
      # Make two frequencies.  The first is the primary.
      delta1 = float(tx_freq) / self.tx_dds_clock * 4294967296
      delta2 = (tx_freq + 1000.0) / self.tx_dds_clock * 4294967296
      s = struct.pack("<bcLL", 2, 'f',
            0xFFFFFFFF & long(delta1 + 0.5), 0xFFFFFFFF & long(delta2 + 0.5))
      try:
        self.tx_program_socket.send(s)
      except:
        pass
  def OnSpot(self, mode):
    self.is_spot = mode
    self.ChangeFrequency(self.tx_frequency, self.vfo_frequency)	# Change in mode may change frequency offset
  def ChangeMode(self, mode):
    # mode is a string: "USB", "AM", etc.
    self.mode = mode
    self.ChangeFrequency(self.tx_frequency, self.vfo_frequency)	# Change in mode may change frequency offset
    if mode in ("CWL", "CWU"):
      self.want_prog_num = 1
    elif mode == "xxIMD":
      self.want_prog_num = 2
    elif mode in ("USB", "LSB"):
      self.want_prog_num = 3
    elif mode[0:3] == "IMD":
      self.want_prog_num = 3
    else:
      return		# Don't bother to change program
    if not self.thread_running:
      self.thread_running = 1
      thread.start_new_thread(self.ChangeProgNum, ())
  def ChangeBand(self, band):
    pass
  def HeartBeat(self):
    if self.thread_msg:
      print self.thread_msg
      self.thread_msg = ''

class HwRxEthVfo(BaseHardware):		# Ethernet control of VFO frequency
  rx_dds_clock = 399997280.E0
  def __init__(self):
    self.vfo_frequency = 0
    self.tx_frequency = 0
    self.rx_socket = None
  def open(self):
    if Config.rx_ip:
      self.rx_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      self.rx_socket.setblocking(0)
      self.rx_socket.connect((Config.rx_ip, Config.rx_port))
    t = "Capture rate %d from sound card %s." % (Config.sample_rate, Config.name_of_sound_capt)
    return t
  def close(self):
    if self.rx_socket is not None:
      self.rx_socket.close()
      self.rx_socket = None
  def ChangeFrequency(self, tx_freq, vfo_freq, source='', band='', event=None):
    if vfo_freq != self.vfo_frequency:
      self.vfo_frequency = vfo_freq
      rx_phase = int(4.0 * vfo_freq / self.rx_dds_clock * math.pow(2.0, 32) + 0.5)
      #tx_phase = int(4.0 * tx_freq / self.rx_dds_clock * math.pow(2.0, 32) + 0.5)
      s = struct.pack("<LLHHHHL", rx_phase, 0, 0xFFFF, 255, 255, 0, rx_phase)
      try:
        self.rx_socket.send(s)
      except:
        pass
  def ChangeBand(self, band):
    pass
  def ChangeMode(self, mode):
    pass
  def HeartBeat(self):
    pass

class LowPassFilter:	# Control my low pass filter box
  address = ('192.168.2.194', 0x3A00 + 39)
  # Filters are numbered 1 thru 8 for bands: 80, 15, 60, 40, 30, 20, 17, short
  lpfnum = (1, 1, 1, 1, 1, 3,	# frequency 0 thru 5 MHz
               4, 4, 5, 5, 5,	# 6 thru 10
               6, 6, 6, 6, 7,	# 11 thru 15
               7, 7, 7, 2, 2,	# 16 thru 20
               2, 2, 8, 8, 8)	# 21 thru 25; otherwise the filter is 8
  def __init__(self):
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.setblocking(0)
    self.socket.connect(self.address)
    self.have_data = None
    self.want_data = '\00'
    self.old_tx_freq = 0
    self.timer = 0
  def ChangeBand(self, band):
    pass
  def SetTxFreq(self, tx_freq):
    if not self.socket:
      return
    # Filters are numbered 1 thru 8
    if abs(self.old_tx_freq - tx_freq) < 100000:
      return	# Ignore small tuning changes
    self.old_tx_freq = tx_freq
    try:		# Look up filter number based on MHz
      num = self.lpfnum[tx_freq / 1000000]
    except IndexError:
      num = 8
    self.want_data =  chr(num)
    self.timer = 0
  def HeartBeat(self):
    if not self.socket:
      return
    try:	# The HP filter box echoes its commands
      self.have_data = self.socket.recv(50)
    except socket.error:
      pass
    except socket.timeout:
      pass
    if self.have_data != self.want_data:
      if self.timer <= 10:
        self.timer += 1
        if self.timer == 10:
          print 'Low pass filter error'
      try:
        self.socket.send(self.want_data)
      except socket.error:
        pass
      except socket.timeout:
        pass

class HighPassFilter:	# Control my high pass filter box
  address = ('192.168.2.194', 0x3A00 + 21)
  def __init__(self):
    self.preamp = 0
    self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    self.socket.setblocking(0)
    self.socket.connect(self.address)
    self.have_data = None
    self.want_data = '\00\00\00'
    self.old_tx_freq = 0
    self.timer = 0
  def ChangeBand(self, band):
    if UseRxudp:
      btn = Application.BtnRfGain
      if btn:
        freq = Application.VFO + Application.txFreq
        if freq < 5000000:
          btn.SetLabel('RF -10', True)
        elif freq < 13000000:
          btn.SetLabel('RF 0 dB', True)
        else:
          btn.SetLabel('RF +16', True)
  def OnButtonRfGain(self, event):
    """Set my High Pass Filter Box preamp gain and attenuator state."""
    btn = event.GetEventObject()
    n = btn.index
    if n == 0:		# 0dB
      self.preamp = 0x00
    elif n == 1:	# +16
      self.preamp = 0x02
    elif n == 2:	# -20
      self.preamp = 0x0C
    elif n == 3:	# -10
      self.preamp = 0x04
    else:
      print 'Unknown RfGain'
    self.SetTxFreq(None)
  def SetTxFreq(self, tx_freq):
    """Set high pass filter and preamp/attenuator state"""
    # Filter cutoff in MHz: 0.0, 2.7, 3.95, 5.7, 12.6, 18.2, 22.4
    # Frequency MHz     Bits       Hex      Band
    # =============     ====       ===      ====
    #   0   to  2.70    PORTD, 0   0x01      160
    #  2.7  to  3.95    PORTB, 1   0x02       80
    #  3.95 to  5.70    PORTD, 7   0x80       60
    #  5.70 to 12.60    PORTB, 0   0x01       40, 30
    # 12.60 to 18.20    PORTD, 6   0x40       20, 17
    # 18.20 to 22.40    PORTB, 7   0x80       15
    # 22.40 to 99.99    PORTB, 6   0x40       12, 10
    # Other bits:  Preamp PORTD 0x02, Atten1 PORTD 0x04, Atten2 PORTD 0x08
    if not self.socket:
      return
    if tx_freq is None:
      tx_freq = self.old_tx_freq
    elif abs(self.old_tx_freq - tx_freq) < 100000:
      return	# Ignore small tuning changes
    self.old_tx_freq = tx_freq
    portb = portc = portd = 0
    if UseSdriq:
      if tx_freq < 15000000:	# Turn preamp on/off
        self.preamp = 0x00
      else:
        self.preamp = 0x02
    elif UseRxudp:
      pass		# self.preamp is already set
    else:		# turn preamp off
      self.preamp = 0x00
    if tx_freq < 12600000:
      if tx_freq < 3950000:
        if tx_freq < 2700000:
          portd = 0x01
        else:
          portb = 0x02
      elif tx_freq < 5700000:
        portd = 0x80
      else:
        portb = 0x01
    elif tx_freq < 18200000:
      portd = 0x40
    elif tx_freq < 22400000:
      portb = 0x80
    else:
      portb = 0x40
    portd |= self.preamp
    self.want_data =  chr(portb) + chr(portc) + chr(portd)
    self.timer = 0
  def HeartBeat(self):
    if not self.socket:
      return
    try:	# The HP filter box echoes its commands
      self.have_data = self.socket.recv(50)
    except socket.error:
      pass
    except socket.timeout:
      pass
    if self.have_data != self.want_data:
      if self.timer <= 10:
        self.timer += 1
        if self.timer == 10:
          print 'High pass filter error'
      try:
        self.socket.send(self.want_data)
      except socket.error:
        pass
      except socket.timeout:
        pass

class AntennaControl:	# Control my KI8BV dipole
  AntCtrlAddress = ('192.168.2.194', 0x3A00 + 33)
  index = {'20':0, '40':1, '60':2, '80':3}
  def __init__(self, address):
    if address:
      self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      self.socket.setblocking(0)
      self.socket.connect(address)
      self.have_data = None
      self.want_data = '\00'
      self.timer = 0
    else:
      self.socket = None
  def ChangeBand(self, band):
    if not self.socket:
      return
    self.timer = 0
    try:
      self.want_data = chr(self.index[band])
    except KeyError:
      self.want_data = chr(3)
  def SetTxFreq(self, tx_freq):
    pass
  def HeartBeat(self):
    if not self.socket:
      return
    try:	# The antenna control box echoes its commands
      self.have_data = self.socket.recv(50)
    except socket.error:
      pass
    except socket.timeout:
      pass
    if self.have_data != self.want_data:
      if self.timer <= 10:
        self.timer += 1
        if self.timer == 10:
          print 'Antenna control error'
      try:
        self.socket.send(self.want_data)
      except socket.error:
        pass
      except socket.timeout:
        pass

class AntennaTuner:		# Control an AT-200PC autotuner made by LDG
  def __init__(self):
    self.serial = None
    self.rx_state = 0
    self.is_standby = None
    self.tx_freq = 0
    self.old_tx_freq = 0
    self.set_L = -9
    self.set_C = -9
    self.set_HiLoZ = -9
    self.param1 = [None] * 20	# Parameters returned by the AT-200PC
    self.param2 = [None] * 20
    self.param1[5] = self.param2[5] = self.param2[6] = 0		# power and SWR
    self.param1[7] = self.param2[7] = 1		# Frequency
    self.param1[1] = self.param1[2] = 0		# Inductor, Capacitor
    self.req_swr = 50			# Requested SWR: 50 thru 56 for 1.1, 1.3, 1.5, 1.7, 2.0, 2.5, 3.0
    self.live_update = 0		# Request live update 1 or 0
    self.antenna = 2			# Select antenna 1 or 2
    self.standby = 0			# Set standby mode 1 or 0
    self.timer = 0
    if sys.platform == "win32":
      self.tty_name = "COM4"		# Windows name of serial port for the AT-200PC
    else:
      self.tty_name = "/dev/ttyUSB0"	# Linux name of serial port for the AT-200PC
    self.error = "Port %s not open" % self.tty_name
    Application.StateNames.append('TunerLC')	# save and restore this variable
  def HeartBeat(self):
    # Open the serial port
    if not self.serial:
      import serial
      try:
        self.serial = serial.Serial(port=self.tty_name, timeout=0)
      except serial.SerialException:
        pass
      else:
        self.error = "Waiting for AT200PC"
        self.serial.setRTS(0)			# turn off the RTS pin on the serial interface
      return
    self.Read()			# Receive from the AT-200PC
    # Call main application with new SWR data
    if Application.bottom_widgets:
      Application.bottom_widgets.UpdateSwr(self.param1, self.param2, self.error)
    if self.error:		# Send a couple parameters, see if we get a response
      if self.req_swr - 50 != self.param1[16]:
        self.Write(chr(self.req_swr))	# Send threshold SWR
      elif self.param1[17] != 0:
        self.Write(chr(59))			# Turn off AutoTune
      else:
        self.error = ''
      return
    if self.param1[4] != self.antenna - 1:		# Check correct antenna
      self.Write(chr(9 + self.antenna))
    elif self.is_standby != self.standby:		# Check standby state
      self.Write(chr(45 - self.standby))
    elif self.param1[19] != self.live_update:	# Check live update state
      self.Write(chr(64 - self.live_update))
    elif self.set_L >= 0 and self.set_HiLoZ >= 0 and (	# Check L and Hi/Lo relay
         self.param1[1] != self.set_L or self.param1[3] != self.set_HiLoZ):
      if self.set_HiLoZ:
        self.Write(chr(65) + chr(self.set_L + 128))
      else:
        self.Write(chr(65) + chr(self.set_L))
    elif self.param1[2] != self.set_C and self.set_C >= 0:	# Set C
      self.Write(chr(66) + chr(self.set_C))
    elif self.live_update:	# If our window shows, request an update
      self.timer += 1
      if self.timer > 20:
        self.timer = 0
        self.Write(chr(40))		# Request ALLUPDATE
  def Write(self, s):		# Write a command string to the AT-200PC
    if DEBUG:
      print 'Send', ord(s[0])
    if self.serial:
      self.serial.setRTS(1)	# Wake up the AT-200PC
      time.sleep(0.003)		# Wait 3 milliseconds
      self.serial.write(s)
      self.serial.setRTS(0)
  def Read(self):	# Receive characters from the AT-200PC
    chars = self.serial.read(1024)
    for ch in chars:
      if self.rx_state == 0:	# Read first of 4 characters; must be decimal 165
        if ord(ch) == 165:
          self.rx_state = 1
      elif self.rx_state == 1:	# Read second byte
        self.rx_state = 2
        self.rx_byte1 = ord(ch)
      elif self.rx_state == 2:	# Read third byte
        self.rx_state = 3
        self.rx_byte2 = ord(ch)
      elif self.rx_state == 3:	# Read fourth byte
        self.rx_state = 0
        byte3 = ord(ch)
        byte1 = self.rx_byte1
        byte2 = self.rx_byte2
        if DEBUG:
          print 'Received', byte1, byte2, byte3
        if byte1 > 19:			# Impossible command value
          continue
        if byte1 == 1 and self.set_L < 0:	# reported inductor value
          self.set_L = byte2
        if byte1 == 2 and self.set_C < 0:	# reported capacitor value
          self.set_C = byte2
        if byte1 == 3 and self.set_HiLoZ < 0:	# reported Hi/Lo relay
          self.set_HiLoZ = byte2
        if byte1 == 13:				# Start standby
          self.is_standby = 1
        elif byte1 == 14:			# Start active
          self.is_standby = 0
        self.param1[byte1] = byte2
        self.param2[byte1] = byte3
  def open(self):
    # TunerLC is a list of (freq, L, C).  Use -L for Low Z, +L for High Z.
    if not hasattr(Application, 'TunerLC'):
      Application.TunerLC = [(0, 0, 0), (4900000, 0, 0), (6000000, 0, 0), (99999999, 0, 0)]
  def close(self):
    if self.serial:
      self.serial.close()
      self.serial = None
  def xxReqSetFreq(self, tx_freq):
    # Set relays for this frequency.  The frequency must exist in the tuner.
    if self.serial and not self.standby and tx_freq > 1500000:
      ticks = int(20480.0 / tx_freq * 1e6 + 0.5)
      self.Write(chr(67) + chr((ticks & 0xFF00) >> 8) + chr(ticks & 0xFF))
  def SetTxFreq(self, tx_freq):
    if tx_freq is None:
      self.set_C = 0
      self.set_L = 0
      self.set_HiLoZ = 0
      return
    self.tx_freq = tx_freq
    if abs(self.old_tx_freq - tx_freq) < 20000:
      return	# Ignore small tuning changes
    self.old_tx_freq = tx_freq
    i1 = 0
    i2 = len(Application.TunerLC) - 1
    while 1:	# binary partition
      i = (i1 + i2) / 2
      if Application.TunerLC[i][0] < tx_freq:
        i1 = i
      else:
        i2 = i
      if i2 - i1 <= 1:
        break
    # The correct setting is between i1 and i2; interpolate
    F1 = Application.TunerLC[i1][0]
    F2 = Application.TunerLC[i2][0]
    L1 = Application.TunerLC[i1][1]
    L2 = Application.TunerLC[i2][1]
    C1 = Application.TunerLC[i1][2]
    C2 = Application.TunerLC[i2][2]
    frac = (float(tx_freq) - F1) / (F2 - F1)
    C = C1 + (C2 - C1) * frac
    self.set_C = int(C + 0.5)
    L = L1 + (L2 - L1) * frac
    if L < 0:
      L = -L
      self.set_HiLoZ = 1
    else:
      self.set_HiLoZ = 0
    self.set_L = int(L + 0.5)
  def ChangeBand(self, band):
    pass ##self.ReqSetFreq(self.tx_freq)
  def OnSpot(self, mode):
    # mode 0 == OFF, 1 == On low, 2 == On high
    if self.serial:
      if mode == 1:
        self.live_update = 1
        self.timer = 999
      elif mode == 0:
        self.live_update = 0
  def OnAntTuner(self, event):	# A button was pressed
    #for t in Application.TunerLC:
    #  print t
    if self.serial:
      btn = event.GetEventObject()
      text = btn.GetLabel()
      if text == 'Tune':
        if not self.standby:
          #self.Write(chr(5))		# Request memory tune
          self.Write(chr(6))		# Request full tune
          self.set_C = -9
          self.set_L = -9
          self.set_HiLoZ = -9
      elif text == 'Save':
        self.Write(chr(46))
        if self.set_HiLoZ == 0:		# High Z
          L = self.set_L
        else:						# Low Z
          L = -self.set_L
        for i in range(len(Application.TunerLC)):	# Record new freq and L/C
          if abs(Application.TunerLC[i][0] - self.tx_freq) < 1000:
            Application.TunerLC[i] = (self.tx_freq, L, self.set_C)
            break
        else:
          Application.TunerLC.append((self.tx_freq, L, self.set_C))
          Application.TunerLC.sort()
      elif text == 'L+':
        self.set_L += 1
      elif text == 'L-':
        self.set_L -= 1
      elif text == 'C+':
        self.set_C += 1
      elif text == 'C-':
        self.set_C -= 1
