# This is a sample quisk_conf.py configuration file for a SoftRock Rx Ensemble II.

# Please do not change this sample file.
# Instead copy it to your own .quisk_conf.py and make changes there.
# See quisk_conf_defaults.py for more information.

from softrock import hardware_usb as quisk_hardware

# In ALSA, soundcards have these names.  The "hw" devices are the raw
# hardware devices, and should be used for soundcard capture.
#name_of_sound_capt = "hw:0"
#name_of_sound_capt = "hw:1"
#name_of_sound_capt = "plughw"
#name_of_sound_capt = "plughw:1"
#name_of_sound_capt = "default"

# Vendor and product ID's for the SoftRock
usb_vendor_id = 0x16c0
usb_product_id = 0x05dc
softrock_model = "RxEnsemble2"

#sample_rate = 48000					# ADC hardware sample rate in Hertz
#name_of_sound_capt = "hw:0"				# Name of soundcard capture hardware device.
#name_of_sound_play = name_of_sound_capt		# Use the same device for play back

