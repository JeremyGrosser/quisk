# This is the config file from my shack, which controls various hardware.

import sys

from n2adr import quisk_hardware
from n2adr import quisk_widgets

if "win" in sys.platform:
  name_of_sound_capt = "Primary"
  name_of_sound_play = "Primary"
else:
  name_of_sound_capt = "hw:0"
  name_of_sound_play = name_of_sound_capt

default_screen = 'WFall'
waterfall_y_scale = 80
waterfall_y_zero  = 40
waterfall_graph_y_scale = 40
waterfall_graph_y_zero = 90
waterfall_graph_size = 160

bandState['40'] = ( 7190000, -5000, 'LSB')
microphone_name = ""
add_imd_button = 1
add_fdx_button = 1
add_extern_demod = "WFM"
latency_millisecs = 50

rxmeth = 1
txmeth = 1

if rxmeth == 0:			# sound card
  data_poll_usec = 5000
  sample_rate = 96000					# ADC hardware sample rate in Hertz
  rx_ip = '192.168.2.194'	# Ethernet Hambus control of VFO
  rx_port = 0x3A00 + 135
elif rxmeth == 1:		# Transceiver
  use_rx_udp = 1					# Get ADC samples from UDP
  rx_udp_ip = "192.168.2.196"		# Sample source IP address
  rx_udp_port = 0xBC77				# Sample source UDP port
  rx_udp_clock = 122880000  		# ADC sample rate in Hertz
  rx_udp_decimation = 8 * 8 * 8		# Decimation from clock to UDP sample rate
  sample_rate = int(float(rx_udp_clock) / rx_udp_decimation + 0.5)	# Don't change this
  name_of_sound_capt = ""			# We do not capture from the soundcard
  channel_i = 0						# Soundcard index of left channel
  channel_q = 1						# Soundcard index of right channel
  data_poll_usec = 10000
  playback_rate = 48000
elif rxmeth == 2:		# SDR-IQ
  use_sdriq = 1					# Use the SDR-IQ
  sdriq_name = "/dev/ft2450"		# Name of the SDR-IQ device to open
  sdriq_clock = 66666667.0		# actual sample rate (66666667 nominal)
  sdriq_decimation = 600			# Must be 360, 500, 600, or 1250
  sample_rate = int(float(sdriq_clock) / sdriq_decimation + 0.5)	# Don't change this
  name_of_sound_capt = ""			# We do not capture from the soundcard
  # Note: For the SDR-IQ, playback is stereo at 48000 Hertz.
  channel_i = 0					# Soundcard index of left channel
  channel_q = 1					# Soundcard index of right channel
  display_fraction = 0.85


if txmeth == 0:					# No transmit
  tx_ip = ""
elif txmeth == 1:				# Transceiver
  microphone_name = "hw:1"
  tx_ip = "192.168.2.196"
  key_method = ""		# Use internal method
  tx_audio_port = 0xBC79
  mic_out_volume = 1.0
elif txmeth == 2:				# SSB exciter
  microphone_name = "hw:1"
  tx_ip = "192.168.2.195"
  key_method = "192.168.2.195"	# Use UDP from this address
  tx_audio_port = 0x553B
  mic_out_volume = 0.6772
