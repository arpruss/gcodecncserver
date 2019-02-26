from __future__ import print_function
import time
import os
import re
import sys

from serial import Serial
from serial.tools import list_ports

class FakeSerial(object):
    def __init__(self, name):
        if name == 'stdout':
            self.handle = sys.stdout
        elif name == 'stderr':
            self.handle = sys.stderr
        else:
            self.handle = open(name, "w")
        
    def flushInput(self):
        return
        
    def write(self, data):
        self.handle.write(data)
        
    def close(self):
        if self.handle is not sys.stdout:
            self.handle.close()
            
    def readline(self):
        return "ok"
        
    def read(self):
        return b'ok\n'
            
class GCodeSender(object):

    HISTORY_LENGTH = 256
    RESEND = re.compile(r'(^rs [Nn]?|^Resend:)\s*([0-9]+)')
    OK = re.compile(r'^ok\b')

    def __init__(self, port, speed=115200, quiet=False, xonxoff=False):
        if port == 'auto':
            port = GCodeSender.detectPort()
        if port.startswith('file:'):
            self.serial = FakeSerial(port[5:])
        else:
            self.serial = Serial(port, speed, xonxoff=xonxoff)
        self.serial.flushInput()
        self.lineNumber = 1
        self.serial.write('\nM110 N1\n')
        self.history = []
        
    @staticmethod
    def detectPort():
        ports = list_ports.comports()
        for port in ports:
            if 'Bluetooth' not in port.description:
                return port.device
        for port in ports:
            return port.device
        return "file:stdout"
        
    def sendCommand(self, c):
        def checksum(text):
            cs = 0
            for c in text:
                cs ^= ord(c)
            return cs & 0xFF

        c = c.split(';')[0].strip()
                        
        command = 'N' + str(self.lineNumber) + ' ' + c
        command += '*' + str(checksum(command)) + '\n'
        
        if len(self.history) >= GCodeSender.HISTORY_LENGTH:
            self.history = self.history[-(GCodeSender.HISTORY_LENGTH-1):]
        self.history.append((self.lineNumber,command))
        
        # TODO: timeout
        self.serial.flushInput()
        self.serial.write(command)
        while True:
            line = self.serial.readline()
            if GCodeSender.OK.match(line):
                break
            m = GCodeSender.RESEND.match(line)
            if m:
                l = int(m.group(2))
                for h in self.history:
                    if h[0] == l:
                        self.serial.write(h[1])
                        break
            
        self.lineNumber += 1
    
    def sendCommands(self, cc):
        for c in cc:
            self.sendCommand(c)
    
if __name__ == '__main__':
    import sys
    
    sender = GCodeSender(sys.argv[1])
    sender.sendCommands(sys.argv[2].split('|'))
    