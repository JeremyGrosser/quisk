from distutils.core import setup, Extension
import sys

# You must define the version here.  A title string including
# the version will be written to __init__.py and read by quisk.py.

Version = '3.5.4'

fp = open("__init__.py", "w")	# write title string
fp.write("#QUISK version %s\n" % Version)
fp.close()

module1 = Extension ('quisk._quisk',
	#include_dirs = ['.'],
	#library_dirs = ['.'],
	libraries = ['asound', 'portaudio', 'fftw3', 'm'],
	sources = ['quisk.c', 'sound.c', 'sound_alsa.c', 'sound_portaudio.c',
		'is_key_down.c', 'microphone.c', 'utility.c',
		'filter.c', 'extdemod.c'],
	)

module2 = Extension ('quisk.sdriqpkg.sdriq',
	libraries = [':_quisk.so', 'm'],
	sources = ['sdriqpkg/sdriq.c'],
	include_dirs = ['.', '..'],
	runtime_library_dirs = ['.'],
	)

modulew1 = Extension ('quisk._quisk',
	include_dirs = ['../fftw3', 'C:/Program Files/Microsoft DirectX SDK (February 2010)/Include',],
	#'C:/Program Files/Microsoft Visual Studio 8/VC/include'],
	library_dirs = ['../fftw3'],
	libraries = ['fftw3-3', 'WS2_32', 'Dxguid', 'Dsound'],
	sources = ['quisk.c', 'sound.c', 'sound_directx.c',
		'is_key_down.c', 'microphone.c', 'utility.c',
		'filter.c', 'extdemod.c'],
	)

modulew2 = Extension ('quisk.sdriqpkg.sdriq',
	libraries = [':_quisk.pyd', ':ftd2xx.lib'],
	library_dirs = ['../ftdi/i386'],
	sources = ['sdriqpkg/sdriq.c'],
	include_dirs = ['.', '../ftdi'],
	#extra_link_args = ['--enable-auto-import'],
	)

if sys.platform == "win32":
  Modules = [modulew1, modulew2]
else:
  Modules = [module1, module2]

setup	(name = 'quisk',
	version = Version,
	scripts = ['quisk'],
	description = 'QUISK, which rhymes with "brisk", is a Software Defined Radio (SDR).',
	long_description = """QUISK is a Software Defined Radio (SDR).  
You supply a complex (I/Q) mixer to convert radio spectrum to an
intermediate frequency (IF) and send that IF to the left and right
inputs of the sound card in your computer.  The QUISK software will
read the sound card data, tune it, filter it, demodulate it, and send
the audio to the same sound card for output to external headphones or
speakers.

Quisk can also control and demodulate data from the SDR-IQ from RfSpace.

Quisk works with the quisk_lppan_k3 package by Leigh, WA5ZNU, to
control the N8LP LP-PAN panadapter and the Elecraft K3.
""",
	author = 'James C. Ahlstrom',
	author_email = 'jahlstr@gmail.com',
	url = 'http://james.ahlstrom.name/quisk/',
	packages = ['quisk', 'quisk.sdriqpkg', 'quisk.n2adr', 'quisk.softrock', 'quisk.usb'],
	package_dir =  {'quisk' : '.'},
	package_data = {'quisk' : ['*.txt', '*.html']},
	ext_modules = Modules,
	classifiers = [
		'Development Status :: 6 - Mature',
		'Environment :: X11 Applications',
		'Environment :: Win32 (MS Windows)',
		'Intended Audience :: End Users/Desktop',
		'License :: OSI Approved :: GNU General Public License (GPL)',
		'Natural Language :: English',
		'Operating System :: POSIX :: Linux',
		'Operating System :: Microsoft :: Windows',
		'Programming Language :: Python',
		'Programming Language :: C',
		'Topic :: Communications :: Ham Radio',
	],
)


