# These are the configuration parameters for receiving the
# 10.7 MHz IF output of the AOR AR8600 receiver with my
# transceiver.  This results in a 100 kHz to 3 GHz
# wide range receiver with pan adapter.
#
# Note:  The AR8600 IF output in WFM mode seems to tune in 10kHz increments
#        no matter what the step size, even though the display reads a
#        different frequency.

# Please do not change this sample file.
# Instead copy it to your own .quisk_conf.py and make changes there.
# See quisk_conf_defaults.py for more information.

import time
import _quisk as QS
import serial			# From the pyserial package

from n2adr import quisk_widgets

default_mode = 'FM'				# Start in FM mode
use_rx_udp = 1					# Get ADC samples from UDP
rx_udp_ip = "192.168.2.196"		# Sample source IP address
rx_udp_port = 0xBC77			# Sample source UDP port
rx_udp_clock = 122880000  		# ADC sample rate in Hertz
rx_udp_decimation = 8 * 8 * 8	# Decimation from clock to UDP sample rate
sample_rate = int(float(rx_udp_clock) / rx_udp_decimation + 0.5)	# Don't change this
name_of_sound_capt = ""			# We do not capture from the soundcard
name_of_sound_play = "hw:0"		# Play back on this soundcard at 48 kHz
channel_i = 0					# Soundcard index of left channel
channel_q = 1					# Soundcard index of right channel
data_poll_usec = 10000			# data poll time in microseconds
playback_rate = 48000			# radio sound playback rate

# Define the Hardware class in this config file instead of a separate file.

# Use the Transceiver hardware as the base class
from n2adr import quisk_hardware as TransceiverHardware
BaseHardware = TransceiverHardware.Hardware

class Hardware(BaseHardware):
  def __init__(self, app, conf):
    BaseHardware.__init__(self, app, conf)
    self.vfo_frequency = 0		# current vfo frequency
    self.tty_name = '/dev/ttyS0'		# serial port name for AR8600
    self.serial = None			# the open serial port
    self.timer = 0.02			# time between AR8600 commands in seconds
    self.time0 = 0				# time of last AR8600 command
    self.serial_out = []		# send commands slowly
  def open(self):
    self.serial = serial.Serial(port=self.tty_name, baudrate=9600,
          stopbits=serial.STOPBITS_TWO, xonxoff=1, timeout=0)
    self.SendAR8600('MD0\r')		# set WFM mode so the IF output is available
    # The AR8600 inverts the spectrum of the 2 meter and 70 cm bands.
    # Other bands may not be inverted, so we may need to test the frequency.
    # But this is not currently implemented.
    QS.invert_spectrum(1)
    t = BaseHardware.open(self)		# save the message
    BaseHardware.ChangeFrequency(self, 0, 10700000)
    return t
  def close(self):
    BaseHardware.close(self)
    if self.serial:
      self.serial.write('EX\r')
      time.sleep(1)			# wait for output to drain, but don't block
      self.serial.close()
      self.serial = None
  def ChangeFrequency(self, tx_freq, vfo_freq, source='', band='', event=None):
    BaseHardware.ChangeFilterFrequency(self, tx_freq)
    vfo_freq = (vfo_freq + 5000) / 10000 * 10000		# round frequency
    if vfo_freq != self.vfo_frequency and vfo_freq >= 100000:
      self.vfo_frequency = vfo_freq
      self.SendAR8600('RF%010d\r' % vfo_freq)
    return tx_freq, vfo_freq
  def SendAR8600(self, msg):	# Send commands to the AR8600, but not too fast
    if self.serial:
      if time.time() - self.time0 > self.timer:
        self.serial.write(msg)			# send message now
        self.time0 = time.time()
      else:
        self.serial_out.append(msg)		# send message later
  def HeartBeat(self):	# Called at about 10 Hz by the main
    BaseHardware.HeartBeat(self)
    if self.serial:
      chars = self.serial.read(1024)
      #if chars:
      #  print chars
      if self.serial_out and time.time() - self.time0 > self.timer:
        self.serial.write(self.serial_out[0])
        self.time0 = time.time()
        del self.serial_out[0]
