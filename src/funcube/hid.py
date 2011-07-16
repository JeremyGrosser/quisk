from ctypes import *
import struct

class hid_device_info(Structure):
    pass

hid_device_info._fields_ = [
        ('path', c_char_p),
        ('vendor_id', c_ushort),
        ('product_id', c_ushort),
        ('serial_number', c_wchar_p),
        ('release_number', c_ushort),
        ('manufacturer_string', c_wchar_p),
        ('product_string', c_wchar_p),
        ('usage_page', c_ushort),
        ('usage', c_ushort),
        ('interface_number', c_int),
        ('next', POINTER(hid_device_info)),
]

HIDBuffer = c_ubyte * 65

libhidapi = cdll.LoadLibrary('libhidapi.so')

libhidapi.hid_enumerate.argtypes = (c_ushort, c_ushort)
libhidapi.hid_enumerate.restype = POINTER(hid_device_info)

libhidapi.hid_free_enumeration.argtypes = (POINTER(hid_device_info),)

libhidapi.hid_open.argtypes = (c_ushort, c_ushort, c_wchar_p)
libhidapi.hid_open.restype = c_void_p

libhidapi.hid_open_path.argtypes = (c_char_p,)
libhidapi.hid_open_path.restype = c_void_p

libhidapi.hid_write.argtypes = (c_void_p, POINTER(HIDBuffer), c_size_t)
libhidapi.hid_write.restype = c_int

libhidapi.hid_read.argtypes = (c_void_p, POINTER(HIDBuffer), c_size_t)
libhidapi.hid_read.restype = c_int

libhidapi.hid_close.argtypes = (c_void_p,)
