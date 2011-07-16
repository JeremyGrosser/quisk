#!/usr/bin/env python
import decimal
import sys

from hid import *

class FCDException(Exception):
    pass

class FCD(object):
    VID = 0x04d8
    PID = 0xfb56

    def __init__(self, path=None):
        self.path = path
        self.dev = None

    def _create_buffer(self, data):
        Buffer = c_ubyte * len(data)
        b = Buffer()
        memset(b, 0x00, len(data))
        for i, x in enumerate(data):
            b[i] = ord(x)
        return b

    def find_device(self):
        devs = libhidapi.hid_enumerate(self.VID, self.PID)
        dev = devs[0]

        while True:
            if dev.vendor_id == self.VID and \
               dev.product_id == self.PID:
                self.path = dev.path
                break
            if not dev.next:
                break
            dev = dev.next[0]

        libhidapi.hid_free_enumeration(devs)
        return

    def open(self):
        self.find_device()
        if self.path is None:
            print 'No funcube dongle found!'
            return False

        self.dev = libhidapi.hid_open_path(self.path)
        if self.dev:
            return True
        else:
            return False

    def read(self):
        if not self.dev:
            raise FCDException('Cannot read without opening the device first!')

        buf = HIDBuffer()
        memset(buf, 0x00, len(buf))
        libhidapi.hid_read(self.dev, buf, len(buf))
        #print '<<', repr(''.join([chr(x) for x in buf]))
        return ''.join([chr(x) for x in buf])

    def write(self, data):
        if not self.dev:
            raise FCDException('Cannot write without opening the device first!')

        data = '\x00' + data
        buf = self._create_buffer(data)
        #print '>>', repr(''.join([chr(x) for x in buf]))
        return libhidapi.hid_write(self.dev, buf, len(data))

    def close(self):
        if self.dev:
            libhidapi.hid_close(self.dev)

    def send_command(self, cmd, data=''):
        data = chr(cmd) + data
        data = data.ljust(64, '\x00')
        self.write(data)

    def get_mode(self):
        self.send_command(1)
        data = self.read()
        return data[2:].rstrip('\x00')

    def _freq_to_int(self, freq):
        freq = struct.unpack('<BBBB', freq)
        res = 0
        for i, x in enumerate(freq):
            res += x << (i * 8)
        return res

    def get_freq(self):
        self.send_command(102)
        data = self.read()
        return self._freq_to_int(data[2:6])

    def set_freq(self, freq):
        '''
        Set the frequency in Hz, returns actual frequency set
        '''
        f1 = freq & 0xFF
        f2 = (freq >> 8) & 0xFF
        f3 = (freq >> 16) & 0xFF
        f4 = (freq >> 24) & 0xFF
        freq = struct.pack('<BBBB', f1, f2, f3, f4)
        self.send_command(101, freq)
        data = self.read()
        return self._freq_to_int(data[2:6])

def main():
    decimal.getcontext().prec = 28

    fcd = FCD()
    fcd.open()

    if len(sys.argv) < 2:
        freq = decimal.Decimal(fcd.get_freq())
    else:
        freq = decimal.Decimal(sys.argv[1])
        freq = freq * 1000000
        freq = int(freq)
        freq = fcd.set_freq(freq)

    freq = decimal.Decimal(freq) / 1000000
    print freq, 'MHz'
    fcd.close()
    return 0

if __name__ == '__main__':
    sys.exit(main())
