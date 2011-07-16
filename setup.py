from distutils.core import setup, Extension
import sys

# You must define the version here.  A title string including
# the version will be written to __init__.py and read by quisk.py.

Version = '3.5.4'

fp = open("__init__.py", "w")   # write title string
fp.write("#QUISK version %s\n" % Version)
fp.close()

if sys.platform == 'win32':
    ext_modules = [
        Extension('_quisk',
            include_dirs=['../fftw3', 'C:/Program Files/Microsoft DirectX SDK (February 2010)/Include'],
            library_dirs=['../fftw3'],
            libraries=['fftw3-3', 'WS2_32', 'Dxguid', 'Dsound'],
            sources=[
                'ext/_quisk/quisk.c',
                'ext/_quisk/sound.c',
                'ext/_quisk/sound_directx.c',
                'ext/_quisk/is_key_down.c',
                'ext/_quisk/microphone.c',
                'ext/_quisk/utility.c',
                'ext/_quisk/filter.c',
                'ext/_quisk/extdemod.c'
            ]),
        Extension('sdriqpkg.sdriq',
            libraries=[':_quisk.pyd', ':ftd2xx.lib'],
            library_dirs=['../ftdi/i386'],
            sources=['ext/sdriqpkg/sdriq.c'],
            include_dirs=['../ftdi']),
    ]
else:
    ext_modules = [
        Extension('_quisk',
            libraries=['asound', 'portaudio', 'fftw3', 'm'],
            sources=[
                'ext/_quisk/quisk.c',
                'ext/_quisk/sound.c',
                'ext/_quisk/sound_alsa.c',
                'ext/_quisk/sound_portaudio.c',
                'ext/_quisk/is_key_down.c',
                'ext/_quisk/microphone.c',
                'ext/_quisk/utility.c',
                'ext/_quisk/filter.c',
                'ext/_quisk/extdemod.c',
            ])
        Extension('sdriqpkg.sdriq',
            libraries=[':_quisk.so', 'm'],
            include_dirs=['ext/_quisk'],
            sources=['ext/sdriqpkg/sdriq.c']),
    ]


setup(name='quisk',
    version=Version,
    scripts=['src/quisk'],
    description='QUISK, which rhymes with "brisk", is a Software Defined Radio (SDR).',
    long_description="""QUISK is a Software Defined Radio (SDR).  
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
    author='James C. Ahlstrom',
    author_email='jahlstr@gmail.com',
    url='http://james.ahlstrom.name/quisk/',
    packages=[
        'quisk',
        'quisk.sdriqpkg',
        'quisk.n2adr',
        'quisk.softrock',
        'quisk.usb'
    ],
    package_dir={'quisk' : 'src'},
    ext_package='quisk',
    ext_modules=ext_modules,
    classifiers=[
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


