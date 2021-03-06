# This is a sample quisk_conf.py configuration file for a SoftRock or
# other hardware with a fixed VFO frequency.

# Please do not change this sample file.
# Instead copy it to your own .quisk_conf.py and make changes there.
# See quisk_conf_defaults.py for more information.

import quisk_hardware_fixed as quisk_hardware

# In ALSA, soundcards have these names.  The "hw" devices are the raw
# hardware devices, and should be used for soundcard capture.
#name_of_sound_capt = "hw:0"
#name_of_sound_capt = "hw:1"
#name_of_sound_capt = "plughw"
#name_of_sound_capt = "plughw:1"
#name_of_sound_capt = "default"

softrock_model = "fixed"			# Fixed frequency SoftRock
fixed_vfo_freq = 7056000			# This is the fixed VFO frequency in Hertz
sample_rate = 96000					# ADC hardware sample rate in Hertz
name_of_sound_capt = "hw:0"			# Name of soundcard capture hardware device.
name_of_sound_play = name_of_sound_capt		# Use the same device for play back
channel_i = 0						# Soundcard index of in-phase channel:  0, 1, 2, ...
channel_q = 1						# Soundcard index of quadrature channel:  0, 1, 2, ...

