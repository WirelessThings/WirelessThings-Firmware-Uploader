#!/usr/bin/env python
# -*- coding: utf-8 -*-

""" Firmware Uploader

    Author: Marcos Amorim
    Copyright 2016 Ciseco Ltd.

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
from time import sleep
import argparse
import AT
import logging
import FW

class FWUploader() :

    isRFu = False

    def __init__(self):
        #self._readConfig() #TODO
        self._checkArgs()
        self._initLogging()

    def _checkArgs(self):
        parser = argparse.ArgumentParser(description="FW Uploader")
        #TODO: Put default values on a config file
        parser.add_argument("-b", "--baudrate",
                            help="Sets the baudrate",
                            type=int,
                            default=9600
                            )
        parser.add_argument("-D", "--device",
                            help="Sets the device to be used",
                            default="/dev/ttyAMA0"
                            )
        parser.add_argument("-f", "--filename",
                            help="Sets the bin file",
                            required=True
                            )
        parser.add_argument("-t", "--timeout",
                            help="Sets the timeout",
                            type=int,
                            default=1
                            )
        parser.add_argument('-g', '--gpio',
                            type=int,
                            help='GPIO pin to set AT Mode'
                            )
        parser.add_argument('-d', '--debug',
                            help="Enable debug output to console",
                            action='store_true'
                            )
        parser.add_argument("-v", "--verify",
                            help="Use the method to verify the firmware",
                            action="store_true"
                            )

        self.args = parser.parse_args()

        if self.args.baudrate != 9600 :
            self.logger.debug("Baudrate different from 9600")
            self.isRFu = True

    def _readConfig(self):
        pass

    def _initLogging(self):
        logging.getLogger().setLevel(logging.NOTSET)
        self.logger = logging.getLogger('FW Uploader')
        _ch = logging.StreamHandler()

        if (self.args.debug):
            _ch.setLevel(logging.DEBUG)
        else:
            _ch.setLevel(logging.WARN)    # this should be WARN by default
            self.logger.setLevel(100)

        _formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        _ch.setFormatter(_formatter)
        self.logger.addHandler(_ch)

        # disable logging if no options are enabled
#        if (self.args.debug == False):
#            self.config.getboolean('Debug', 'console_debug') == False and
#            self.config.getboolean('Debug', 'file_debug') == False):
#            self.logger.debug("Disabling loggers")
            # disable debug output
#            self.logger.setLevel(100)
#            return
        # set console level


    def _restartClasses(self, baudrate):
        try :
            self.ser = serial.Serial(self.args.device, baudrate, timeout=self.args.timeout)
        except serial.SerialException as e:
            self.logger.error ("Failed to open port {}: {}".format(self.args.device, e.strerror))
            sys.exit(1)

        try :
            if self.args.gpio:
                self.at = AT.AT(self.ser, self.logger, self.args.gpio)
            else:
                self.at = AT.AT(self.ser, self.logger)
        except Exception as e:
            self.logger.error ("Failed to create AT class: {}".format(e))
            sys.exit(1)

        try :
            self.fw = FW.FW(self.at, self.ser, self.logger)
        except serial.SerialException as e:
            self.logger.error ("Failed to create FW class: {}".format(e))
            sys.exit(1)

    def on_execute(self):
        self._restartClasses(self.args.baudrate)

        self.logger.info("Writing new firmware file {} to device {} with baudrate {}...".format(self.args.filename, self.args.device, self.args.baudrate));
        self.logger.info("Reading firmware file...")

        self.firmwareFile = self.fw.prepareFirmwareFile(self.args.filename)
        if not self.firmwareFile:
            self.at.endSerial()
            sys.exit(1)

        self.firmwareLines = len(self.firmwareFile)
        self.logger.info("Read {} lines from firmware file".format(self.firmwareLines))

        if not self.at.enterATMode(): #if comm fails
            self.logger.debug ("Failed enter AT mode, checking if device is in bootloader mode")

            self.ser.close()
            self._restartClasses(9600)

            if self.fw.checkBootloaderVersion():
                self.logger.debug ("Device in bootloader mode")
                self.recordAndVerify()

            self.logger.debug ("Device not in bootloader mode.")
            self.fw.error("Failed to enter on AT mode")

        if not self.fw.checkFWVersion() :
            self.fw.error("Unable to check the FW version")

        ################### Enters program download mode ######################
        if not self.fw.enterProgramMode() :
            self.fw.error("enterProgramMode: Invalid response received")

        sleep(0.1) ######### need to wait for the reboot of the device ###############

        if not self.fw.checkBootloaderVersion() :
            self.fw.error("checkBootloaderVersion: Error on enter in Bootloader mode")

        self.recordAndVerify()

    def recordAndVerify(self) :
        if not self.fw.enterWriteMode() :
            self.fw.error("recordAndVerify: Error on enter in Write Mode")

        self.logger.debug ("recordAndVerify: Writing FW on {}... Please wait..".format(self.args.device))

        lines = self.fw.sendFirmware(self.firmwareFile, self.args.debug)
        if  lines != self.firmwareLines:
            self.fw.error ("recordAndVerify: Error while uploading file. Line {}".format(lines))

        self.logger.debug ("recordAndVerify: Sent {} of {} lines...".format(lines, self.firmwareLines)) #debug

        if not self.fw.waitResponse("R"):
            self.fw.error("recordAndVerify: 'R' sent. Invalid response received")

        if not self.fw.waitResponse("y"):
            self.fw.error("recordAndVerify: 'y' sent. Invalid response received")

        if self.args.verify:
            if not self.fw.enterVerifyMode():
                self.fw.error("recordAndVerify: Error on enter in Verify Mode")

            self.logger.info("recordAndVerify: Start the Verify process...")
            lines = self.fw.sendFirmware(self.firmwareFile, self.args.debug)

            if  lines != self.firmwareLines:
                self.fw.error ("recordAndVerify: Error while verifying file. Line {}".format(lines))

            self.logger.debug ("recordAndVerify: Verified {} of {} lines...".format(lines, self.firmwareLines)) #debug

        if not self.fw.sendCommit() :
            self.fw.error("recordAndVerify: Error sending commit")

        self.logger.info("All OK, XRF successfully reprogrammed!")
        self.logger.info("Waiting for device to settle...")
        sleep(2)

        if self.isRFu: #if is RFu, change the port baudrate to given baudrate
            self.ser.close()
            self._restartClasses(self.args.baudrate)

        self.ser.flushInput()

        if not self.at.enterATMode() :
            self.fw.error("recordAndVerify: Error entering AT mode")

        if not self.fw.checkFWVersion() :
            self.fw.error("recordAndVerify: Error checking FW version")

        sleep(0.1)
        self.at.endSerial()
        self.logger.info("Success!")
        sys.exit(0)

if __name__ == "__main__":
    app = FWUploader()
    app.on_execute()
