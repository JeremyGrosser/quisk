# This is a sample quisk_conf.py configuration file for a SoftRock Rx/Tx Ensemble.

# Please do not change this sample file.
# Instead copy it to your own .quisk_conf.py and make changes there.
# See quisk_conf_defaults.py for more information.

# Attach your SoftRock Rx/Tx Ensemble to the line in and line out of a high quality
# sound card.  Set name_of_sound_capt and name_of_mic_play to this card.  You need
# a second (lower quality) sound card to play radio audio named name_of_sound_play.
# This is sufficient for CW.  To transmit SSB, you need a capture sound card named
# microphone_name.  The microphone_name and name_of_sound_play can be the same device.

from softrock import hardware_usb as quisk_hardware
from softrock import widgets_tx   as quisk_widgets

# In Linux, ALSA soundcards have these names.  The "hw" devices are the raw
# hardware devices, and should be used for soundcard capture.
#name_of_sound_capt = "hw:0"
#name_of_sound_capt = "hw:1"
#name_of_sound_capt = "plughw"
#name_of_sound_capt = "plughw:1"
#name_of_sound_capt = "default"

# Vendor and product ID's for the SoftRock
usb_vendor_id = 0x16c0
usb_product_id = 0x05dc
softrock_model = "RxTxEnsemble"

# If you want to monitor the hardware key state, enter a poll time in milliseconds.
key_poll_msec = 0

#sample_rate = 96000				# ADC hardware sample rate in Hertz
#name_of_sound_capt = "hw:0"			# Name of soundcard capture hardware device.
#name_of_sound_play = ""			# Name of soundcard playback hardware device.

# Microphone capture:
#microphone_name = "hw:1"			# Name of microphone capture device
#name_of_mic_play = name_of_sound_capt		# Name of play device if CW or mic I/Q is sent to a sound card
#mic_playback_rate = sample_rate		# Playback rate must be a multiple 1, 2, ... of mic_sample_rate
#mic_out_volume = 0.6				# Transmit sound output volume (after all processing) as a fraction 0.0 to 1.0

