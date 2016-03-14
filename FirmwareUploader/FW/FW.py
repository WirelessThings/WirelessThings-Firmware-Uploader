#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" FW Class

    Author: Marcos Amorim
    Copyright 2015 Ciseco Ltd.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

"""

import serial
import sys
from time import time, sleep
import AT
import logging

class FW():

    _device = "COM3"
    _timeout = 1.5 #timeout for receiving bytes functions

    def __init__(self, atHandle=None, serialHandle=None, logger=None, gpioPin=None, event=None):
        if logger == None:
            logging.basicConfig(level=logging.DEBUG)
            self.logger = logging.getLogger()
        else:
            self.logger = logger

        self.event = event

        self._serial = serialHandle or self.startSerial(self._device, 9600, self._timeout)
        if not self._serial:
            sys.exit(1)

        self._at = atHandle or AT.AT(self._serial, self.logger, gpioPin, self.event)

    def startSerial(self, port, baudrate, timeout) :
        """
            Starts the serial port with
            the specified parameters
        """
        try :
            ser = serial.Serial(port, baudrate, timeout=timeout)
        except serial.SerialException as e:
            self.logger.error ("Failed to open port {}: {}".format(self._device,e.strerror))
            return False

        return ser

    def error(self, message, code=1) :
        """
            Sends an error message, close the serial and
            exits the program
        """
        self.logger.error(message)
        self._at.endSerial()
        sys.exit(code)

    def sendStrWaitingResponse(self, send, response, retries=3) :
        """
            Sends an string through the serial port and
            waits for their response
        """
        retry = 0
        received = False
        while not received and retry < retries:
            self._serial.flushInput();
            self._serial.write(send)
            received = self._serial.read()
            retry += 1

            if received in response:
                break
                
        return received

    def checkFWVersion(self, tout=_timeout):
        """
            Sends the AT command to check
            the current version of the FW
        """
        return self._at.sendATWaitForResponse("ATVR")

    def enterProgramMode(self):
        """
            Sends the AT command to make device
            enter on the Program Mode
        """
        return self._at.sendATWaitForOK("ATPG")

    def exitATMode(self):
        """
            Sends the AT command to make device
            exit the AT Mode
        """
        return self._at.sendATWaitForOK("ATDN")

    def checkBootloaderVersion(self):
        """
            Checks the Bootloader Version of the device
        """

        return self.sendStrWaitingResponse("~Y",["3","4"])

    def checkBootloaderSubVersion(self):
        """
            Checks the Bootloader Version of the device
        """
        return self.sendStrWaitingResponse("S",["d","D"])

    def enterWriteMode(self) :
        """
        Starts write mode
        """
        if self.sendStrWaitingResponse("W", "W"):
            return True
        else :
            return False

    def enterVerifyMode(self) :
        """
        Starts verify mode
        """
        if self.sendStrWaitingResponse("V","V"):
            return True
        else :
            return False

    def waitResponse(self, response) :
        """
        Waits on the serial for the response
        until timeout or response received
        """
        data = None
        data = self._serial.read()
        if data == response :
            return True
        else :
            return False

    def sendFirmware(self, fwFile, debug=True) :
        """
        Sends the firmware file stored before to
        the device line by line, then returns the
        total number of lines are sent (or false if fails)
        """
        currentLine = 0
        self._at._sleep(1.5)
        fwLength = len(fwFile)
        i = 10

        for fwLine in fwFile :
            data = None
            data = self._serial.read()
            if data == None:
                self.logger.debug ("FW: returned blank expecting R")
                break
            elif data != "R" :
                self.logger.debug ("FW: sendFirmware data = {}".format(ord(data)))
                break

            currentLine += 1
            self._serial.write(fwLine) #send the line
            data = None
            data = self._serial.read()
            # TODO: try to improve this part, be more readable
            if data == None:
                self.logger.debug ("FW: returned blank expecting A")
                break
            elif data != "A" :
                if data == "N" : # retry once
                    self._serial.write(fwLine)
                    data = None
                    data = self._serial.read()
                    if data == "A" :
                        continue
                    elif data in ["n","N"] :    #if still not working, restarts the device
                        self.logger.debug ("FW: Restarting device...")
                        self._at.endSerial()
                        #TODO reset and try again (not tested yet)
                        sys.exit(1)
                    else :    #if doesn't receive any acceptable answer, exits the program
                        break

            if (currentLine >= ((fwLength*i)/100)) and debug :
                self.logger.debug ("FW: {}% Completed".format(i))    # debug
                i += 10

        return currentLine

    def restartSerial(self, port, baudrate, timeout) :
        """
        Restart the opened _serial with
        the new port, baud and timeout given
        """
        self._serial.close()
        try :
            self._serial = self.startSerial(port,baudrate,timeout=timeout)
        except serial.SerialException as e:
            self.logger.error ("FW: Failed to open port {}: {}".format(port,e.strerror))
            return False

        return self._serial

    def sendCommit(self) :
        """
            Sends the commit command "X"
        """
        try :
            self._serial.write("X")
            self.logger.debug ("FW: Commit sent")
            return True
        except :
            return False

    def prepareFirmwareFile(self, fwFileName) :
        """
            Store the content of the FW File (.bin file)
            to be written on the device
        """

        try :
            f = open(fwFileName, "r")
        except IOError as e:
            self.logger.error("FW: Could not open firmware file {} for reading: {}\n".format(fwFileName,e.strerror))
            return False
        firmware = [line.rstrip() for line in f] #rstrip() removes the whitespaces \f , \n , \r , \t , \v , \x and blank on the end of the line
        line = ""
        for line in firmware:
            if len(line) != 67 :
                self.logger.error("FW: Line with invalid length of {} in firmware file\n".format(len(line)))
                return False
        f.close()
        return firmware

            ##### not implemented
    """
    def checkStandardBaudrate(self, port):
        StdBaudrates = [9600, 115200]
        #StdBaudrates = [300, 600, 1200, 1800, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400]
        self.logger.debug("FW: Checking Baudrate")
        default_baudrate = self._serial.baudrate

        if self.enterATMode() :
            return default_baudrate

        for baud in StdBaudrates:
            self.logger.debug("FW: baud {} baudrate {}".format(baud, default_baudrate))
            if default_baudrate == baud : #already tested this speed in the first try, so skip it
                continue

            baudrate = baud
            self.endSerial()

            self.logger.debug("FW: Baudrate Setted to {}".format(baudrate))
            self.setupSerial(port, baudrate)

            if self.enterATMode() :
                return baudrate

#        if (baud == len(StdBaudrates)) :
        self.logger.debug("FW: Baudrate not supported")
        return False
#        else :
#            return baudrate

"""
