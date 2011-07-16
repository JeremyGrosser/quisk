#     from n2adr import quisk_hardware

from quisk_hardware_model import Hardware as BaseHardware
from funcube import FCD

class Hardware(BaseHardware):
    def __init__(self, app, conf):
        BaseHardware.__init__(self, app, conf)
        self.fcd = FCD()
        self.tune = 0
    
    def open(self):			# Called once to open the Hardware
        BaseHardware.open(self)
        self.fcd.open()
        self.fcd.set_freq(97300000)
        return 'Capture from Funcube Dongle'

    def close(self):
        BaseHardware.close(self)
        self.fcd.close()

    def ChangeFrequency(self, tune, vfo, source='', band='', event=None):
        vfo = self.fcd.set_freq(vfo)
        self.tune = tune
        return tune, vfo

    def ReturnFrequency(self):
        return (self.tune, self.fcd.get_freq())
