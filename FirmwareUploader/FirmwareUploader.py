#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" Firmware Uploader

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

import Tkinter as tk
import ttk
from ScrolledText import *
import sys
import os
import argparse
import json
import urllib2
import httplib
import ConfigParser
import tkMessageBox
import threading
import Queue
import string
import glob
from time import sleep, asctime, time
import logging
from collections import OrderedDict
import serial
import FW
import AT

"""
    Big TODO list

    Create a release notes online to be displayed at Release Notes Screen

    DONE If more than one Device was found on Search, list all to user selects the port

    Scrollbar on Search Listbox (??)

    Searching Screen UI

    Improve serial port detection method (for Linux and Mac)

    Any TODO's below
"""


INTRO = """Welcome to Firmware Uploader


Please Select the Comm Port and Baudrate below"""

COMM = """COM Port"""

CONFIG = """Select your device config options"""

END = """Your device has been configured"""

RELEASENOTES = """Serial V0.94, USB V0.56, LLAP0.77

* ATID changes will now take place immediately, previously
it took one message before the new setting was used.

* Corrected ATEA command - where the random nonce had
unfortunate results.
"""

ERRDEV = """Device Error"""
USBMODE = """You are using an USB Device.
Please connect this device via Serial Interface
to update the firmware"""

COMMERROR = """Communication Error"""

COMMTIMEOUT = """Communication Timeout"""

OLDDEVICE = """This Device is too old for this program"""

OLDBOOTLOADER = """Bootloader update needed first"""

BOOTLOADERNOTSUPPORTED = """Device using bootloader v4 is not supported yet"""

NODEVREPLY = """No reply from the Device.
Would you like to retry?"""

BOOTLOADERMODE = """Bootloader Mode"""

BOOTLOADER = """Device in bootloader Mode.
Click OK to proceed"""

CHOOSEMODE = """Your device supports more than one mode

Please choose an option below"""

UNABLEFINDDEVICE = """Unable to Identify your Device Firmware"""

CHOOSEDEVICEBELOW = """Please select your device listed below"""

CHOOSEDEVICEBELOW1 = """This firmware is used by more than one device type.

Please select your device below"""

PREPARING = """Preparing to start Upload"""

DOWNLOADING = """Downloading Firmware (1/3)"""
DWNLDCOMPLETE = """Download Complete (1/3)"""

UPLOADING = """Uploading Firmware (2/3)"""
UPLOADCOMPLETE = """Upload Complete (2/3)"""

VERIFYING = """Verifying Firmware (3/3)"""
VERIFYCOMPLETE = """Verification Complete (3/3)"""

UPPROGRESS = """Uploading in progress"""
CLICKDEBUG = """Click "Debug" to show more info"""

UPFINISHED = """Upload Finished"""

ERRUPLOADING = """Error during Uploading Firmware"""

WINDOWS = False
LINUX = False
MACOSX = False

STEP = 5

class FirmwareUploader:
    """
        Firmware Uploader Class
        Handles display of wizard interface for upload firmwares
        to WirelessThings Devices
    """

    _version = "1.0"

    _configFileDefault = "FirmwareUploader_defaults.cfg"
    _configFile = "FirmwareUploader.cfg"

    _columns = 5
    _rows = 17
    _rowHeight = 28 #do not change it
    _widthMain = 454
    _heightMain = (_rows*_rowHeight)+4

    _baudrateList = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]
    _baudrate = 0
    _port = ''
    _serialTimeout = 3

    _currentFrame = None

    def __init__(self):
        """
            setup variables
        """
        self._running = False

        self._detectSystem() #sets the OS running

        logging.getLogger().setLevel(logging.NOTSET)
        self.logger = logging.getLogger('FirmwareUploader')
        self._ch = logging.StreamHandler()
        self._ch.setLevel(logging.WARN)    # this should be WARN by default
        self._formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self._ch.setFormatter(self._formatter)
        self.logger.addHandler(self._ch)

    def _initLogging(self):
        """ now we have the config file loaded and the command line args setup
            setup the loggers
            """
        self.logger.info("Setting up Loggers. Console output may stop here")

        # disable logging if no options are enabled
        if (self.args.debug == False and
            self.config.getboolean('Debug', 'console_debug') == False and
            self.config.getboolean('Debug', 'file_debug') == False):
            self.logger.debug("Disabling loggers")
            # disable debug output
            self.logger.setLevel(100)
            return
        # set console level
        if (self.args.debug or self.config.getboolean('Debug', 'console_debug')):
            self.logger.debug("Setting Console debug level")
            if (self.args.log):
                logLevel = self.args.log
            else:
                logLevel = self.config.get('Debug', 'console_level')

            numeric_level = getattr(logging, logLevel.upper(), None)
            if not isinstance(numeric_level, int):
                raise ValueError('Invalid console log level: %s' % loglevel)
            self._ch.setLevel(numeric_level)
        else:
            self._ch.setLevel(100)

        # add file logging if enabled
        # TODO: look at rotating log files
        # http://docs.python.org/2/library/logging.handlers.html#logging.handlers.TimedRotatingFileHandler
        if (self.config.getboolean('Debug', 'file_debug')):
            self.logger.debug("Setting file debugger")
            self._fh = logging.FileHandler(self.config.get('Debug', 'log_file'))
            self._fh.setFormatter(self._formatter)
            logLevel = self.config.get('Debug', 'file_level')
            numeric_level = getattr(logging, logLevel.upper(), None)
            if not isinstance(numeric_level, int):
                raise ValueError('Invalid console log level: %s' % loglevel)
            self._fh.setLevel(numeric_level)
            self.logger.addHandler(self._fh)
            self.logger.info("File Logging started")

    def _detectSystem(self) :
        """ Detects what OS are using
        """
        global WINDOWS, MACOSX, LINUX
        if sys.platform.startswith('win'):
            WINDOWS = True
        elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
            LINUX = True
        elif sys.platform.startswith('darwin'):
            MACOSX = True
        else:
            raise EnvironmentError('Unsupported platform')

    def _listSerialPorts(self):
        """Lists serial ports

        :raises EnvironmentError:
            On unsupported or unknown platforms
        :returns:
            A list of available serial ports
        """
        global WINDOWS, MACOSX, LINUX
        result = []

        if WINDOWS:
            #ports = ['COM' + str(i + 1) for i in range(256)]
            import _winreg
            try:
                path = "HARDWARE\\DEVICEMAP\\SERIALCOMM"
                key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, path)
            except WindowsError:
                raise IterationError
            i = 0
            while True:
                try:
                    port = _winreg.EnumValue(key, i)
                    result.append(str(port[1]))
                    i += 1
                except EnvironmentError:
                    # if reachs here, means the key is empty now
                    return sorted(result)
        elif LINUX:
            # this is to exclude your current terminal "/dev/tty"
            ports = glob.glob('/dev/tty[A-Za-z]*')

        elif MACOSX:
            ports = glob.glob('/dev/tty.*')

        else:
            raise EnvironmentError('Unsupported platform')

        for port in ports:
            if port == '/dev/ttyprintk': ## don't need to check for this port
                continue
            try:
                s = serial.Serial(port)
                s.close()
                result.append(port)
            except (OSError, serial.SerialException):
                pass
        return sorted(result)

    def downloadFile(self, type):
        try:
            if type == 'json' :
                request = urllib2.urlopen(self.config.get('FirmwareUploader', 'url_path') +
                                          self.config.get('FirmwareUploader', 'json_file'))
                self.jsonFile = request.read()

            elif type == 'bin' :
                url = (self.config.get('FirmwareUploader', 'url_path') +
                                  self._bootloaderFolder + '/' + self._deviceClass +
                                  '/' + self._firmwareFilename)

                self.logger.info (url) #debug
                self.updateDownloadStatus('start')

                request = urllib2.urlopen(url)
                self.firmwareFile = request.read().splitlines() #splitlines removes the aditional '\n' on the end of file added by read() mode

            elif type == 'txt' :
                request = urllib2.urlopen(self.config.get('FirmwareUploader', 'url_path') + self._releaseNotes)
                #request = urllib2.urlopen('http://openmicros.org/index.php/articles/84-xrf-basics/224-firmware-release-notes')
                self._releaseNotesFile = request.read()

        except urllib2.HTTPError, e:
            self.logger.error('Unable to get file - HTTPError = ' +
                            str(e.code))
            return e.code

        except urllib2.URLError, e:
            self.logger.error('Unable to get file - URLError = ' +
                            str(e.reason))

            return e.reason

        except httplib.HTTPException, e:
            self.logger.error('Unable to get file - HTTPException')

            return 'HTTPException'

        except Exception, e:
            import traceback
            self.logger.critical('Unable to get file - Exception = ' +
                            traceback.format_exc())
            return traceback.format_exc()

        if type == 'bin' :
            self.updateDownloadStatus('end')

        return request.getcode()

    def updateDownloadStatus (self, state):
        if state == 'start':
            self.labelUploading.set(DOWNLOADING)
            self.qSerialUpload.put_nowait(['Debug',DOWNLOADING+'\n'])
            #self.uploadBar.start(100)
            self.qUploadProgressBar.put_nowait(["start",100])
        else :
            self.labelUploading.set(DWNLDCOMPLETE)
            self.qSerialUpload.put_nowait(['Debug',DWNLDCOMPLETE+'\n'])
            self.qSerialUpload.put_nowait(['Debug',UPLOADING+'\n'])
            self.qUploadProgressBar.put_nowait(["stop"])
            #self.uploadBar.stop()
            self.qUploadProgressBar.put_nowait(["value","maximum"])
            #self.uploadBar['value'] = self.uploadBar['maximum']
            sleep (2)
            #self.labelUploading.config(text=UPLOADING)
            self.labelUploading.set(UPLOADING)
            self.qUploadProgressBar.put_nowait(["value",0])
            #self.uploadBar['value'] = 0

    def on_execute(self):
        """
            entry point for running
        """
        self._checkArgs()
        self._readConfig()
        self._initLogging()
        self._loadDevices()

        self._running = True

        # run the GUI's
        self._runUpWiz()
        self._cleanUp()

    def _runUpWiz(self):
        try:
            self.logger.debug("Running Main GUI")
            self.master = tk.Tk()
            self.master.protocol("WM_DELETE_WINDOW", self.confirmClosing)

            # check if the offset in the config file can be applied to this screen
            # Note: due to limitation of the tk, we can't be able to find the use of
            # multiple monitors on Windows.
            configWidth = self.config.getint('FirmwareUploader','window_width_offset')
            configHeight = self.config.getint('FirmwareUploader','window_height_offset')
            monitorWidth = self.master.winfo_screenwidth()
            monitorHeight = self.master.winfo_screenheight()
            #if the offset stored is not applicable, center the screen
            if (configWidth > monitorWidth) or (configHeight > monitorHeight):
                width_offset = (monitorWidth - self._widthMain)/2
                height_offset = (monitorHeight - self._heightMain)/2
            else:
                #uses config
                width_offset = configWidth
                height_offset = configHeight

            self.master.geometry(
                     "{}x{}+{}+{}".format(self._widthMain,
                                          self._heightMain,
                                          width_offset,
                                          height_offset
                                          )
                                 )

            self.master.title("WirelessThings Firmware Uploader Wizard v{}".format(self._version))
            self.master.resizable(0,0)

            self._displayIntro()

            if WINDOWS :
                icon = 'wt.ico'
                self.master.wm_iconbitmap(icon)
            elif LINUX :
            ### TODO test on MACOSX #####
                icon = 'wt.gif'
                img = tk.PhotoImage(file=icon)
                self.master.tk.call('wm', 'iconphoto', self.master._w, img)

            self.master.mainloop()
        except KeyboardInterrupt:
            self.logger.info("Keyboard Interrupt - Exiting")
            self._endUpWiz()

        self.logger.debug("Exiting")

    def confirmClosing(self):
        if tkMessageBox.askyesno("Uploader Wizard", "Do you really want to quit?", parent=self.master):
            self._endUpWiz()
            self._cleanUp()
        else:
            return

    def _displayIntro(self):
        self.logger.debug("Display Intro Page")
        self.iframe = tk.Frame(self.master, name='introFrame', relief=tk.RAISED,
                                borderwidth=2, width=self._widthMain,
                                height=self._heightMain)
        self.iframe.pack()
        self._currentFrame = 'introFrame'
        self._buildGrid(self.iframe)

        tk.Label(self.iframe, name='introText', text=INTRO
                ).grid(row=2, column=0, columnspan=self._columns, rowspan=3)

        tk.Label(self.iframe, name='commText', text=COMM
                ).grid(row=6, column=1, columnspan=2, rowspan=1)

        self.commPortCombobox = ttk.Combobox(self.iframe, state='readonly')
        self.commPortCombobox.config(postcommand=self.reListSerialPorts)
        self.commPortCombobox.grid(row=7, column=1, columnspan=2, rowspan=1)

        self.searchDeviceSerialButton = tk.Button(self.iframe, text='Search', command=lambda :self.searchDeviceSerial())
        self.searchDeviceSerialButton.grid(row=7, column=3, columnspan=1)

        tk.Label(self.iframe, text="Baudrate"
                ).grid(row=9, column=1, columnspan=2, rowspan=1)

        self.baudrateCombobox = ttk.Combobox(self.iframe, state='readonly')
        self.baudrateCombobox['values'] = self._baudrateList
        self.baudrateCombobox.set(9600) #9600 default
        self.baudrateCombobox.grid(row=10, column=1, columnspan=2, rowspan=1)

        tk.Button(self.iframe, text='Next', command=lambda :self._setCOMPort()
                ).grid(row=self._rows-4, column=1, columnspan=3,
                sticky=tk.E+tk.W)


    def reListSerialPorts(self) :
        try :
            self.commPortCombobox['values'] = self._listSerialPorts()
        except :
            self.logger.debug("reListSerialPorts: Error listing serial ports")

    def searchDeviceSerial(self):
        if tkMessageBox.askyesno("Uploader Wizard", "This can take quite some time to search all the available COM ports\nAre you sure?", parent=self.master):
            self.reListSerialPorts()
            self._initLocatingDeviceSerialThread()

            self.startSearchingScreen()
        else:
            return

    def _initLocatingDeviceSerialThread(self):
        self.logger.debug("Starting initLocatingSerialDevice Thread")

        self.tLocatingDeviceSerialStop = threading.Event()

        self.tLocatingDeviceSerial = threading.Thread(target=self.locatingDeviceSerialThread)
        self.tLocatingDeviceSerial.daemon = True

        try:
            self.tLocatingDeviceSerial.start()
        except:
            self.logger.exception("Failed to start Locating Device Serial Thread")

    def _checkDeviceFound(self):
        if not self.tLocatingDeviceSerial.is_alive():
            if len(self.deviceAndCommPort) > 1:
                self.loadingBar.destroy()
                self.sframe.children['label'].config(text="More than one device was found.\n\nPlease select what device you want")

                lb = tk.Listbox(self.sframe, selectmode=tk.SINGLE, bd=0, height=5)
                lb.pack(fill=tk.X, padx=5)
                lb.pack()
                for r in range(0,len(self.deviceAndCommPort)):
                    lb.insert(r+1,self.deviceAndCommPort[r])

                lb.bind('<<ListboxSelect>>', self.commPortSelect)

                tk.Button(self.sframe, name="confirm", text="Confirm", state=tk.DISABLED,
                          command=lambda :self.destroySearchWindow()
                          ).pack(side=tk.BOTTOM, pady=10)

                self.searchWindow.update()
                position = self.master.geometry().split("+")
                w, h = position[0].split("x")
                self.searchWindow.geometry("+{}+{}".format(
                                                            int(position[1])+((int(w)/2)-self.searchWindow.winfo_width()/2),
                                                            int(position[2])+((int(h)/2)-self.searchWindow.winfo_height()/2)
                                                            )
                                           )
            else:
                if self.deviceFound:
                    port = self.deviceAndCommPort[0].split("[",1)[1]
                    self._port = port.split("]",1)[0]
                    self.commPortCombobox.set(self._port)
                    self.baudrateCombobox.set(self._baudrate)
                    self.searchWindow.destroy()
                else:
                    self.searchWindow.destroy()
                    tkMessageBox.showerror("Uploader Wizard", "No Device found", parent=self.master)
        else:
            self.master.after(1000, self._checkDeviceFound)

    def commPortSelect(self, evt):
        w = evt.widget
        self.device = w.get(w.curselection())
        if self.device:
            self.sframe.children['confirm'].config(state=tk.ACTIVE)

    def destroySearchWindow(self):
        #sets the comm selected and destroy the screen
        self.device = self.device.split("[",1)[1]
        self._port = self.device.split("]",1)[0]
        self.commPortCombobox.set(self._port)
        self.baudrateCombobox.set(self._baudrate)
        self.searchWindow.destroy()

    def locatingDeviceSerialThread(self):
        self.logger.debug("Starting search for the COM ports")

        self._baudrate = 9600
        self.deviceFound = False
        self.deviceAndCommPort = []
        for port in self.commPortCombobox['values']:
            if self.tLocatingDeviceSerialStop.is_set():
                return
            self._port = port
            try :
                self.ser = serial.Serial(self._port, self._baudrate,timeout=self._serialTimeout)
                self.at = AT.AT(serialHandle=self.ser, logger=self.logger)
            except serial.SerialException as e:
                self.ser.close()
                self.logger.critical ("Failed to open port {}: {}".format(port,e.strerror))
                return
            try :
                if self.at.enterATMode() : #if comm succeed
                    #ask the device for FW Version and add to a list of devices
                    self.deviceFound = True
                    fwVersion = self.at.sendATWaitForResponse("ATVR")
                    self.at.sendATWaitForOK("ATDN")
                    self.ser.close()
                    if fwVersion:
                        if '0.' in fwVersion:
                            fwVersion = fwVersion.split('0.',1)[1]
                    # remove the B and U for display?
                    else:
                        fwVersion = "Unknown"
                    #TODO: Improve this way to create the data displayed in the listbox.
                    self.deviceAndCommPort.append("Firmware: {}      [{}]".format(fwVersion, port))
                    #self.deviceAndCommPort.append("port, fwVersion])
                    #break
            except:
                self.logger.critical ("Failed to open port {}: {}".format(port,e.strerror))
                self.ser.close()

        self.ser.close()
        return


    def startSearchingScreen(self):
        self.logger.debug("Starting Searching Screen")

        self.searchWindow = tk.Toplevel()
        self.searchWindow.protocol("WM_DELETE_WINDOW", self.tLocatingDeviceSerialStop.set)

        self.sframe = tk.Frame(self.searchWindow, name='searchFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain/2,
                               height=self._heightMain/2)
        self.sframe.pack(fill=tk.BOTH)

        tk.Label(self.sframe, name="label", text="Searching for WirelessThings Devices\n\nThis could take some time").pack(fill=tk.BOTH, padx=80, pady=35)
        self.logger.debug ("Starting Loading Bar")
        self.loadingBar = ttk.Progressbar(self.sframe, orient='horizontal', mode='indeterminate')
        self.loadingBar.pack(fill=tk.X, padx=80, pady=35)
        self.loadingBar.start()

        self.searchWindow.update_idletasks()
        self.searchWindow.grab_set_global()
        position = self.master.geometry().split("+")
        w, h = position[0].split("x")
        self.searchWindow.geometry("+{}+{}".format(
                                                    int(position[1])+((int(w)/2)-self.searchWindow.winfo_width()/2),
                                                    int(position[2])+((int(h)/2)-self.searchWindow.winfo_height()/2)
                                                    )
                                    )

        self.master.after(2000, self._checkDeviceFound)

        if WINDOWS :
            icon = 'wt.ico'
            self.searchWindow.wm_iconbitmap(icon)
        elif LINUX :
        ### TODO test on MACOSX #####
            icon = 'wt.gif'
            img = tk.PhotoImage(file=icon)
            self.searchWindow.tk.call('wm', 'iconphoto', self.searchWindow._w, img)
        self.searchWindow.update_idletasks()
        return



    def _setCOMPort (self) :
        self._port = self.commPortCombobox.get()
        self._baudrate = int(self.baudrateCombobox.get())

        self._initSerialGetVersionThread()

        self.startCommunicatingScreen()

        self._checkSerialError = True
        self.master.after(1000, self._checkSerialGetVersionError)


    def startCommunicatingScreen(self) :
        self.master.children[self._currentFrame].pack_forget()

        self.cframe = tk.Frame(self.master, name='communicatingFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain,
                               height=self._heightMain)
        self.cframe.pack()
        self._currentFrame = 'communicatingFrame'

        self._buildGrid(self.cframe)

        tk.Label(self.cframe, text="Connecting with device..."
                ).grid(row=7, column=0, columnspan=self._columns, rowspan=1)

        self.commProgressBar = ttk.Progressbar(self.cframe, orient='horizontal', mode='indeterminate', length=self._widthMain/2.5)
        self.commProgressBar.grid(row=9, column=0, columnspan=self._columns)
        self.commProgressBar.start()
        return

    def createDevicesList(self):
        try :
            ds = self._devices
        except :
            pass
        else:
            self.ordDevices = OrderedDict(sorted(ds.items(), key=lambda t: t[0]))
            index = 0
            self._deviceList = []

            if self._inBootloaderMode : #if is in bootloader mode, list all devices
                for id, devices in self.ordDevices.items() :
                    if devices['Device Class'] in ['USB','Serial'] :
                        for dev in devices['Devices'] :
                            self._deviceList.insert(index, dev['Name'])
                            self._deviceClass = self.originalDeviceClass = devices['Device Class']
                            self.frequency = dev['Frequency']
                            self.fileExtension = dev['Filename Extension']
                            self._newFwName = id
                            try :
                                if dev['Support LLAP'] :
                                    self._supportLLAP = True
                            except :
                                self._supportLLAP = False

                            index += 1
            else : #list only the devices correspondent to the Fw version
                for id, devices in self.ordDevices.items() :
                    if id == self._deviceFwName :
                        self._newFwName = id
                        for dev in devices['Devices'] :
                            self._deviceList.insert(index, dev['Name'])
                            self._deviceName = dev['Name']
                            self._deviceClass = self.originalDeviceClass = devices['Device Class']
                            self.frequency = dev['Frequency']
                            self.fileExtension = dev['Filename Extension']
                            if (self._deviceClass in ['LLAP','LLAP2']) :
                                self._supportLLAP = True
                                self._serialFirmware = dev['Serial Firmware']
                            else :
                                try :
                                    if dev['Support LLAP'] :
                                        self._supportLLAP = True
                                except :
                                    self._supportLLAP = False
                            index += 1

            if len(self._deviceList) > 1 :
                self._deviceList.sort()
                self.singleDevice = False
                self.startListDeviceScreen()
            else :
                self.singleDevice = True
                self._checkAcceptsLLAP()


    def startListDeviceScreen(self) :
        self.master.children[self._currentFrame].pack_forget()

        self.lframe = tk.Frame(self.master, name='lFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain,
                               height=self._heightMain)
        self.lframe.pack()
        self._currentFrame = 'lFrame'
        self._listboxSelection = ''
        self._buildGrid(self.lframe)

        self._supportLLAP = False

        if self._inBootloaderMode :
        #if not identify the version, list all devices
            tk.Label(self.lframe, text=UNABLEFINDDEVICE
                    ).grid(row=2, column=0, columnspan=self._columns, rowspan=4)
        else :
            tk.Label(self.lframe, text="Your Device Firmware Version is"
                    ).grid(row=1, column=0, columnspan=self._columns, rowspan=4)

            tk.Label(self.lframe, text=('v'+self._fwVersion+' '+self._deviceFwName)
                        ).grid(row=3, column=0, columnspan=self._columns, rowspan=4)

        tk.Label(self.lframe, text=CHOOSEDEVICEBELOW1
                    ).grid(row=5, column=0, columnspan=self._columns, rowspan=4)

        lbframe = tk.Frame(self.lframe, bd=1, relief=tk.SUNKEN)

        self._listboxDevices = tk.Listbox(lbframe, selectmode=tk.SINGLE, bd=0, height=9)

        for r in range(0,len(self._deviceList))        :
            self._listboxDevices.insert(r,self._deviceList[r])

        self._listboxDevices.bind('<<ListboxSelect>>', self._onDeviceSelect)

        sV = tk.Scrollbar(lbframe)
        sV.pack(side=tk.RIGHT, fill=tk.Y)
        sV.config(command=self._listboxDevices.yview)
        self._listboxDevices.config(yscrollcommand=sV.set)

        sH = tk.Scrollbar(lbframe, orient=tk.HORIZONTAL)
        sH.pack(side=tk.BOTTOM, fill=tk.X)
        sH.config(command=self._listboxDevices.xview)
        self._listboxDevices.config(xscrollcommand=sH.set)

        self._listboxDevices.pack(fill=tk.X)

        lbframe.grid(row=8, column=1, columnspan=self._columns-2, rowspan=6, sticky=tk.W+tk.E+tk.N+tk.S)

        tk.Button(self.lframe, text='Back',
              command=lambda :self._startOver(),
              ).grid(row=self._rows-2, column=1, sticky=tk.W)

        self.listNextButton = tk.Button(self.lframe, text='Next', state=tk.DISABLED,
             command=lambda :self._checkAcceptsLLAP())
        self.listNextButton.grid(row=self._rows-2, column=2, columnspan=2, sticky=tk.E+tk.W)


    def _checkAcceptsLLAP(self) :
        if self._supportLLAP:    #if supports LLAP, go to supportLLAP screen
            self._xrfVersion = self._listboxSelection.split('v',1)[1] # splits on v char to get the hw version Number

        self._startMainScreen()


    def _startMainScreen(self) :
        self.master.children[self._currentFrame].pack_forget()

        self.mframe = tk.Frame(self.master, name='mFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain,
                               height=self._heightMain)
        self.mframe.pack()
        self._currentFrame = 'mFrame'

        self._buildGrid(self.mframe)

        if self._deviceClass == 'USB' :
            devClass = self._usbCommon
        elif self._deviceClass == 'LLAP' :
            devClass = self._llapCommon
        elif self._deviceClass == 'LLAP2':
            devClass = self._llap2Common
        elif self._deviceClass == 'Serial':
            devClass = self._serialCommon

        versions = devClass['Versions']
        #starts create the firmware filename
        self._fileBase = devClass['FileBase']
        ver_sort = sorted(versions, key=lambda t: t, reverse=True)

        self._lastFwVersion = self.showVersion = ver_sort[0] #takes the latest firmware version number
        if '0.' in self.showVersion :
            self.showVersion = self.showVersion.split('.',1)[1]

        if self._inBootloaderMode :
            self._deviceFwName = ''

        deviceList = []
        i = 0

        if self._fwVersion == "Unknown":
            tk.Label(self.mframe, text=self._deviceName+"     "+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=0, column=0, columnspan=self._columns, rowspan=2)
        else:
            tk.Label(self.mframe, text=self._deviceName+"     v"+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=0, column=0, columnspan=self._columns, rowspan=2)

        latestFwLabel = tk.Label(self.mframe, text="Latest "+self._deviceClass+" Version Available: "+self.showVersion)
        latestFwLabel.grid(row=2, column=0, columnspan=self._columns, rowspan=1)

        releaseNotesButton = tk.Button(self.mframe, text='Release Notes',
                                            command=lambda :self._startReleaseNoteScreen())
        releaseNotesButton.grid(column=1, columnspan=self._columns-2, rowspan=1, sticky=tk.N+tk.S+tk.W+tk.E)

        olderVersionButton = tk.Button(self.mframe, text='Change to Older Version',
                                            command=lambda :self._startOlderVersionScreen())
        olderVersionButton.grid(column=1, columnspan=self._columns-2, rowspan=1, sticky=tk.N+tk.S+tk.W+tk.E)

        #extrem test
        #self._fwVersion = "78"

        if self._fwVersion == self.showVersion :
            txt = "Your device is up to date"
            tk.Label(self.mframe, text=txt).grid(row=4, column=0, columnspan=self._columns, rowspan=1)

        elif self._fwVersion < self.showVersion or self._inBootloaderMode:
            txt = "Version "+self.showVersion+" available"
            tk.Label(self.mframe, text=txt).grid(row=4, column=0, columnspan=self._columns, rowspan=1)

            upgradeButton = tk.Button(self.mframe, text='Upgrade to Latest Firmware',
                                            #command=lambda :self._startUploading())
                                            command=lambda :self.askConfirmation("Upgrade"))
            upgradeButton.grid(column=1, columnspan=self._columns-2, rowspan=1, sticky=tk.N+tk.S+tk.W+tk.E)
            deviceList.insert(i, upgradeButton)
            i += 1

        deviceList.insert(i,olderVersionButton)
        i += 1

        if self._deviceClass in ['LLAP','LLAP2'] : #shows serial button and change llap type button
            changeToSerialButton = tk.Button(self.mframe, text='Change to Serial',
                                                    command=lambda :self.askConfirmation("Serial"))
            changeToSerialButton.grid(column=1, columnspan=self._columns-2, rowspan=1, sticky=tk.N+tk.S+tk.W+tk.E)
            deviceList.insert(i, changeToSerialButton)
            i += 1

            changeToLLAPButton = tk.Button(self.mframe, text='Change LLAP Type',
                                                command=lambda :self._startLLAPScreen())
            changeToLLAPButton.grid(column=1, columnspan=self._columns-2, rowspan=1, sticky=tk.N+tk.S+tk.W+tk.E)
            deviceList.insert(i, changeToLLAPButton)
            i += 1
        elif self._supportLLAP: #if device is not LLAP but has support for that, show the change LLAP button
            changeToLLAPButton = tk.Button(self.mframe, text='Change to LLAP Type',
                                                command=lambda :self._startLLAPScreen())
            changeToLLAPButton.grid(column=1, columnspan=self._columns-2, rowspan=1, sticky=tk.N+tk.S+tk.W+tk.E)
            deviceList.insert(i, changeToLLAPButton)
            i += 1

        deviceList.insert(i,releaseNotesButton)
        i+=1

        if self.singleDevice :
            backButton = tk.Button(self.mframe, text='Back',
                    command=lambda :self._startOver())
            backButton.grid(column=1, columnspan=self._columns-2,
                    sticky=tk.E+tk.W)
        else :
            backButton = tk.Button(self.mframe, text='Back',
                    command=lambda :self.startListDeviceScreen())
            backButton.grid(column=1, columnspan=self._columns-2,
                    sticky=tk.E+tk.W)

        deviceList.insert(i, backButton)
        self._assignRows(deviceList,5,self._rows)


    def _assignRows (self, deviceList, initialRow, finalRow):
            lenList = len(deviceList)
            availableRows = finalRow - initialRow
            step = (availableRows/lenList)
            mod = (availableRows%lenList)
            i = 0
            if lenList < 4 :
                initialRow += 1
            r = initialRow + mod
            while i < lenList :
                deviceList[i].grid(row=r)
                i+=1
                r+=step

    def askConfirmation(self, sender):
        if sender == "Upgrade":
            text = "This will upgrade your device to latest firmware.\nAre you sure?"
        else:
            text = "This will change your device to {} firmware.\nAre you sure?".format(sender)

        if tkMessageBox.askyesno("Uploader Wizard",text, parent=self.master):
            if sender == "Serial":
                self._setSerialFirmware()
            else:
                self._startUploading()
        else:
            return

    def _setSerialFirmware(self) :
        self._deviceClass = 'Serial'
        self._fileBase = self._serialCommon['FileBase']
        ver_sort = sorted(self._serialCommon['Versions'], key=lambda t: t, reverse=True)
        self._lastFwVersion = self.showVersion = ver_sort[0] #takes the latest firmware version number
        if '0.' in self.showVersion :
            self.showVersion = self.showVersion.split('.',1)[1]

        if self._serialFirmware == 'XRF' :
            self.fileExtension = ''
        elif self._serialFirmware == 'UARTSRF' :
            self.fileExtension = 'UARTSRF'
        self._newFwName = self._serialFirmware #sets the new firmware name for the device

        self._startUploading()


    def _startLLAPScreen(self) :
        self.master.children[self._currentFrame].pack_forget()

        self.llapframe = tk.Frame(self.master, name='llapFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain,
                               height=self._heightMain)
        self.llapframe.pack()
        self._currentFrame = 'llapFrame'

        self._buildGrid(self.llapframe)

        if self._fwVersion == "Unknown":
            tk.Label(self.llapframe, text=self._deviceName+"     "+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=1, column=0, columnspan=self._columns, rowspan=2)
        else:
            tk.Label(self.llapframe, text=self._deviceName+"     v"+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=1, column=0, columnspan=self._columns, rowspan=2)

        tk.Label(self.llapframe, text="LLAP Mode"
                    ).grid(row=3, column=0, columnspan=self._columns, rowspan=2)

        tk.Label(self.llapframe, text=CHOOSEDEVICEBELOW
                    ).grid(row=5, column=0, columnspan=self._columns, rowspan=1)


        lbframe = tk.Frame(self.llapframe, bd=1, relief=tk.SUNKEN)

        self._listboxLLAP = tk.Listbox(lbframe, selectmode=tk.SINGLE, bd=0, height=9)

        self._llapFirmware = ''
        index = 0

        for id, devices in self.ordDevices.items() :
            if id == self._deviceFwName :
                continue
            if devices['Device Class'] == 'LLAP' :
                for dev in devices['Devices'] :
                    if (self._xrfVersion in dev['Name']) :
                        self._listboxLLAP.insert(index, devices['Description'])
                        index += 1

            self._listboxLLAP.bind('<<ListboxSelect>>', self._onLLAPSelect)

        sH = tk.Scrollbar(lbframe, orient=tk.HORIZONTAL)
        sH.config(command=self._listboxLLAP.xview)
        self._listboxLLAP.config(xscrollcommand=sH.set)
        sH.pack(side=tk.BOTTOM, fill=tk.X)

        sV = tk.Scrollbar(lbframe)
        sV.config(command=self._listboxLLAP.yview)
        self._listboxLLAP.config(yscrollcommand=sV.set)
        sV.pack(side=tk.RIGHT, fill=tk.Y)

        self._listboxLLAP.pack(fill=tk.X)
        lbframe.grid(row=8, column=1, columnspan=self._columns-2, rowspan=6, sticky=tk.W+tk.E+tk.N+tk.S)

        self._deviceClass = 'LLAP'
        self._fileBase = self._llapCommon['FileBase']
        ver_sort = sorted(self._llapCommon['Versions'], key=lambda t: t, reverse=True)
        self._lastFwVersion = self.showVersion = ver_sort[0] #takes the latest firmware version number
        if '0.' in self.showVersion :
            self.showVersion = self.showVersion.split('.',1)[1]

        tk.Button(self.llapframe, text='Back',
              command=lambda :self._setDevClassBack()
              ).grid(row=self._rows-2, column=1, sticky=tk.W)

        self.listLLAPNextButton = tk.Button(self.llapframe, text='Next', state=tk.DISABLED,
                          command=lambda :self.askConfirmation(self._llapFirmware))
        self.listLLAPNextButton.grid(row=self._rows-2, column=2, columnspan=2,
                    sticky=tk.E+tk.W)


    def _setDevClassBack(self) :
        self._deviceClass = self.originalDeviceClass
        self._startMainScreen()


    def _startReleaseNoteScreen(self):
        position = self.master.geometry().split("+")

        self.releaseNotesWindow = tk.Toplevel()
        self.releaseNotesWindow.geometry("+{}+{}".format(
                                                    int(position[1])+self._widthMain/6,
                                                    int(position[2])+self._heightMain/6
                                                    )
                                    )

        self.releaseNotesWindow.title("Release Notes")

        self.rnframe = tk.Frame(self.releaseNotesWindow, name='moreInfoFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain/2,
                               height=self._heightMain/4)
        self.rnframe.pack()

        text = tk.Text(self.rnframe, width=60,
                                    height=20)

        ##### TODO Release Notes file to show here
        #self._releaseNotes = "README.md" #name of the file on url_path
        #self.downloadFile('txt')
        #text.insert(tk.END, self._releaseNotesFile)

        text.insert(tk.END, RELEASENOTES)
        text.config(state=tk.DISABLED)

        s = tk.Scrollbar(self.rnframe)

        s.config(command=text.yview)
        text.config(yscrollcommand=s.set)

        tk.Button(self.rnframe, text="Dismiss",
                  command=lambda :self.releaseNotesWindow.destroy()
                  ).pack(side=tk.BOTTOM)

        s.pack(side="right", fill="y", expand=False)
        text.pack(side="left", fill="both", expand=True)

        if WINDOWS :
            icon = 'wt.ico'
            self.releaseNotesWindow.wm_iconbitmap(icon)
        elif LINUX :
        ### TODO test on MACOSX #####
            icon = 'wt.gif'
            img = tk.PhotoImage(file=icon)
            self.releaseNotesWindow.tk.call('wm', 'iconphoto', self.releaseNotesWindow._w, img)


    def _startOlderVersionScreen(self):
        self.master.children[self._currentFrame].pack_forget()

        self.ovframe = tk.Frame(self.master, name='ovFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain,
                               height=self._heightMain)
        self.ovframe.pack()
        self._currentFrame = 'ovFrame'

        self._buildGrid(self.ovframe)

        if self._fwVersion == "Unknown":
            tk.Label(self.ovframe, text=self._deviceName+"     "+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=0, column=0, columnspan=self._columns, rowspan=2)
        else:
            tk.Label(self.ovframe, text=self._deviceName+"     v"+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=0, column=0, columnspan=self._columns, rowspan=2)

        tk.Label(self.ovframe, text=self._deviceClass+" Firmware Versions"
                    ).grid(row=2, column=0, columnspan=self._columns, rowspan=2)

        lbframe = tk.Frame(self.ovframe, bd=1, relief=tk.SUNKEN)

        self._listboxOlderVer = tk.Listbox(lbframe, selectmode=tk.SINGLE, bd=0, height=9)

        try :
            if self._deviceClass == 'USB' :
                devClass = self._usbCommon
            elif self._deviceClass == 'Serial':
                devClass = self._serialCommon
            elif self._deviceClass == 'LLAP' :
                devClass = self._llapCommon
            elif self._deviceClass == 'LLAP2':
                devClass = self._llap2Common
        except :
            pass
        else:
            ods = OrderedDict(sorted(devClass.items(), key=lambda t: t[0]))
            index = 0

            ods['Versions'] = sorted(ods['Versions'], key=lambda t: t, reverse=True)
            for version in ods['Versions'] :
                if '0.' in version :
                    version = version.split('.',1)[1]

                if (version != self._fwVersion) :
                    self._listboxOlderVer.insert(index, version)
                    index += 1

            self._listboxOlderVer.bind('<<ListboxSelect>>', self._onOlderVersionSelect)

        sV = tk.Scrollbar(lbframe)
        sV.pack(side=tk.RIGHT, fill=tk.Y)
        sV.config(command=self._listboxOlderVer.yview)
        self._listboxOlderVer.config(yscrollcommand=sV.set)

        sH = tk.Scrollbar(lbframe, orient=tk.HORIZONTAL)
        sH.pack(side=tk.BOTTOM, fill=tk.X)
        sH.config(command=self._listboxOlderVer.xview)
        self._listboxOlderVer.config(xscrollcommand=sH.set)

        self._listboxOlderVer.pack(fill=tk.X)

        if self._listboxOlderVer.size() > 1 :
            tk.Label(self.ovframe, text="Please select the version listed below"
                        ).grid(row=4, column=0, columnspan=self._columns, rowspan=2)
            lbframe.grid(row=8, column=1, columnspan=self._columns-2,
                            rowspan=6, sticky=tk.W+tk.E+tk.N+tk.S)
        else :
            tk.Label(self.ovframe, text="No older versions found"
                    ).grid(row=6, column=1, columnspan=self._columns-2,
                            rowspan=6, sticky=tk.W+tk.E+tk.N+tk.S)

        tk.Button(self.ovframe, text='Back',
              command=lambda :self._startMainScreen(),
              ).grid(row=self._rows-2, column=1, sticky=tk.W)

        self.olderVersionNextButton = tk.Button(self.ovframe, text='Next', state=tk.DISABLED,
             command=lambda :self._startUploading())
        self.olderVersionNextButton.grid(row=self._rows-2, column=2, columnspan=2,
                    sticky=tk.E+tk.W)

    def _startUploading (self) :
        self._initSerialUploadThread()
        self._startUploadingScreen()

    def _startUploadingScreen(self):
        self.master.children[self._currentFrame].pack_forget()

        self.upframe = tk.Frame(self.master, name='upFrame', relief=tk.RAISED,
                               borderwidth=2, width=self._widthMain,
                               height=self._heightMain)
        self.upframe.pack()
        self._currentFrame = 'upFrame'

        self._buildGrid(self.upframe)

        self.labelDebug = tk.StringVar()
        self.labelUploading = tk.StringVar()


        if self._fwVersion == "Unknown":
            tk.Label(self.upframe, text=self._deviceName+"     "+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=0, column=0, columnspan=self._columns, rowspan=1)
        else:
            tk.Label(self.upframe, text=self._deviceName+"     v"+self._fwVersion+' '+self._deviceFwName
                    ).grid(row=0, column=0, columnspan=self._columns, rowspan=1)

        tk.Label(self.upframe, text="Replacing with v"+self.showVersion+" "+self._newFwName
                ).grid(row=1, column=0, columnspan=self._columns, rowspan=1)

        self.labelUploading.set(PREPARING)
        tk.Label(self.upframe, textvariable=self.labelUploading).grid(row=3, column=0, columnspan=self._columns, rowspan=2)

        self.uploadBar = ttk.Progressbar(self.upframe, orient='horizontal', mode='determinate', length=self._widthMain-16)
        self.uploadBar.grid(row=5, column=0, columnspan=self._columns)
        self.percent = STEP

        debugButton = tk.Button(self.upframe, text='Debug', state=tk.DISABLED,
             command=lambda: self._enableDebugWindow())
        debugButton.grid(row=6, column=4, columnspan=1, rowspan=1,
                    sticky=tk.E+tk.W)

        self.debugTextVisible = False
        self.debugText = ScrolledText(self.upframe, width=self._widthMain/9, height=self._heightMain/50)

        self.fDebugTextCreated.set()
        debugButton.config(state=tk.ACTIVE)

        self.labelDebug.set(UPPROGRESS+'\n'+CLICKDEBUG)
        tk.Label(self.upframe, name='clickDebugLabel', textvariable=self.labelDebug
                    ).grid(row=9, column=0, columnspan=self._columns, rowspan=2)

        self.finishButton = tk.Button(self.upframe, text='Finish', state=tk.DISABLED,
             command=lambda: self._endUpWiz())
        self.finishButton.grid(row=self._rows-2, column=1, columnspan=self._columns-2, sticky=tk.E+tk.W)


    def _enableDebugWindow(self) :
        if self.debugTextVisible :
            self.debugText.grid_forget()
            self.upframe.children['clickDebugLabel'].grid(row=8, column=0,
                                            columnspan=self._columns, rowspan=4)
            self.debugTextVisible = False
        else :
            #self.labelDebug.grid_forget()
            self.upframe.children['clickDebugLabel'].grid_forget()
            self.debugText.grid(row=7, column=0, columnspan=self._columns, rowspan=8)
            self.debugTextVisible = True


    def _updateDebugText(self, message) :
        self.debugText.config(state=tk.NORMAL)
        self.debugText.insert(tk.END,message)
        self.debugText.see(tk.END)
        self.debugText.config(state=tk.DISABLED)


#    def _updateProgressBar(self):
#        if self._checkProgress:
#            if (self.fw._line_number > ((self.firmware_lines*self.percent)/100)) :
#                self.qSerialUpload.put_nowait(['Debug',"{}% Completed\n".format(self.percent)])
#                self.percent+=STEP
#
#            if (self.fw._line_number == self.firmware_lines) :
#                self.percent = STEP
#                self.uploadBar['value'] = self.uploadBar['maximum']
#                self._checkProgress = False
#
#            elif (self.fw._line_number != self.uploadBar['value']) :
#                self.uploadBar.step(self.fw._line_number-self.uploadBar['value'])
#            self.master.after(100, self._updateProgressBar)

    def _updateProgressBar(self):
        if self._checkProgress:
            while not self.qUploadProgressBar.empty():
                msg = self.qUploadProgressBar.get()
                if msg[0] == "start":
                    self.uploadBar.start(int(msg[1]))
                elif msg[0] == "stop":
                    self.uploadBar.stop()
                elif msg[0] == "value":
                    if msg[1] == "maximum":
                        msg[1] = self.uploadBar["maximum"]
                    self.uploadBar[msg[0]] = msg[1]
                else:
                    self.uploadBar[msg[0]] = msg[1]

            if (self.fw._line_number > ((self.firmware_lines*self.percent)/100)) :
                self.qSerialUpload.put_nowait(['Debug',"{}% Completed\n".format(self.percent)])
                self.percent+=STEP

            if (self.fw._line_number == self.firmware_lines) :
                self.percent = STEP
                self.uploadBar['value'] = self.uploadBar['maximum']
                self._checkProgress = False

            elif (self.fw._line_number != self.uploadBar['value']) :
                self.uploadBar.step(self.fw._line_number-self.uploadBar['value'])
            self.master.after(100, self._updateProgressBar)


    def _checkSerialUploadMessage(self) :
        if self._checkUploadQueue :
            self.master.after(500,self._checkSerialUploadMessage)
            while not self.qSerialUpload.empty() :
                msg = self.qSerialUpload.get()
                if (msg[0] == 'Debug') :
                    self._updateDebugText(msg[1])
                    self.qSerialUpload.task_done()
                elif (msg[0] == 'Error') :
                    self._updateDebugText(msg[1])
                    tkMessageBox.showerror('Error',message=msg[1], parent=self.master)
                    self._checkUploadQueue = False
                    self.qSerialUpload.task_done()
                    self.labelUploading.set(ERRUPLOADING)
                    self.labelDebug.set(ERRUPLOADING+'\n'+CLICKDEBUG)
                    self.finishButton.config(state=tk.ACTIVE)
            if not self.tSerialUpload.isAlive() :
                self._checkDebugText = False

    def _initSerialUploadThread(self) :
        self.logger.info("Serial Upload Thread Init")

        if self._deviceClass == 'LLAP' or self._deviceClass == 'LLAP2' :
            self._firmwareFilename = "{}{}-V{}-{}.bin".format(self._fileBase, self.fileExtension, self._lastFwVersion, self.frequency)
        elif self._deviceClass == 'Serial' :
            if self.fileExtension == '' : # if no fileExt, remove the last - from the filename
                self._firmwareFilename = "{}-V{}-{}.bin".format(self._fileBase, self._lastFwVersion, self.frequency)
            else :
                self._firmwareFilename = "{}-V{}-{}-{}.bin".format(self._fileBase, self._lastFwVersion, self.frequency, self.fileExtension)
        elif self._deviceClass == 'USB':
            if self.fileExtension == '': # if no fileExt, remove the last '-' from the filename
                self._firmwareFilename = "{}-V{}.bin".format(self._fileBase, self._lastFwVersion)
            else :
                self._firmwareFilename = "{}-V{}-{}.bin".format(self._fileBase, self._lastFwVersion, self.fileExtension)

        self.qSerialUpload = Queue.Queue()
        self.qUploadProgressBar = Queue.Queue()

        self.fDebugTextCreated = threading.Event()

        self.tSerialUpload = threading.Thread(target=self._SerialUploadThread)
        self.tSerialUpload.daemon = True

        try :
            self.tSerialUpload.start()
        except:
            self.logger.exception("Failed to start Serial Upload Thread")


    def _SerialUploadThread(self):
        self.logger.info("tSerialUpload: Serial Upload thread started")
        self.fDebugTextCreated.wait() #waits until debugText is created

        self._checkUploadQueue = True
        self.master.after(1000,self._checkSerialUploadMessage)

        # setup the Serial and AT and FW classes
        self.at = AT.AT(serialHandle=self.ser, logger=self.logger)
        self.fw = FW.FW(serialHandle=self.ser, atHandle=self.at, logger=self.logger)

        if self._inBootloaderMode :
            self.qSerialUpload.put(['Debug','Device is in Bootloader Mode\n'])

        self.qSerialUpload.put(['Debug','Starting Upload Process\n'])
        sleep(1)
        self._uploadFwAndVerify()

    def _uploadFwAndVerify(self) :
        self.qSerialUpload.put_nowait(['Debug','Entering Write Mode\n'])

        writeMode = False
        try :
            writeMode = self.fw.enterWriteMode()
            self.logger.debug("writeMode = {}".format(writeMode))
            if not writeMode:
                self.qSerialUpload.put(['Error',"Error on enter in Write Mode\n"])
                return
        except serial.SerialException as e:
            self.qSerialUpload.put(['Error',"Communication Error"])
            return

        request = self.downloadFile('bin')

        if str(request) != '200' :
            self.qSerialUpload.put(['Error',"Error Downloading Firmware File.\nError "+str(request)])
            #self.uploadBar.stop()
            self.qUploadProgressBar.put_nowait(["stop"])
            return

        self.firmware_lines = len(self.firmwareFile)

        self.logger.debug ("Writing FW on {}... Please wait...".format(self._port))
        self._checkProgress = True
        self.qUploadProgressBar.put_nowait(["value",0])
        self.qUploadProgressBar.put_nowait(["maximum",self.firmware_lines])
        #self.uploadBar['value'] = 0
        #self.uploadBar['maximum'] = self.firmware_lines
        self.master.after(100, self._updateProgressBar)
        lines = 0
        try :
            lines = self.fw.sendFirmware(self.firmwareFile)
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return

        if  lines != self.firmware_lines :
            self.qSerialUpload.put(['Error',"Error while uploading file. Line {}\n".format(lines)])
            return
        try :
            if not self.fw.waitResponse("R") :
                self.qSerialUpload.put(['Error',"Invalid response received\n"])
                return
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return
        try :
            if not self.fw.waitResponse("y") :
                self.qSerialUpload.put(['Error',"Invalid response received\n"])
                return
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return

        #if verify :
        try :
            if not self.fw.enterVerifyMode() :
                self.qSerialUpload.put(['Error',"Invalid response received\n"])
                return
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return
        try :
            self.labelUploading.set(VERIFYING)
            self.qSerialUpload.put_nowait(['Debug',"100% Completed\n\n"])
            self.qSerialUpload.put_nowait(['Debug',"Start the Verify process (3/3)\n"])
            sleep(2)
            self._checkProgress = True
            self.master.after(1000, self._updateProgressBar)
            self.qUploadProgressBar.put_nowait(["value",0])
            #self.uploadBar['value'] = 0
            self.qSerialUpload.put_nowait(['Debug',"Enter Verifying Mode\n"])
        except :
            self.qSerialUpload.put(['Error',"Error setting Verify Mode"])
            return

        lines = 0
        try :
            lines = self.fw.sendFirmware(self.firmwareFile)
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return

        if  lines != self.firmware_lines :
            self.qSerialUpload.put(['Error',"Invalid response received\n"])
            return
        try :
            if not self.fw.sendCommit() :
                self.qSerialUpload.put(['Error',"Error sending commit\n"])
                return
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return

        self.qSerialUpload.put_nowait(['Debug',"100% Completed\n\n"])
        self.qSerialUpload.put_nowait(['Debug',"All OK, Device successfully reprogrammed!\n"])
        self.qSerialUpload.put_nowait(['Debug',"Waiting for device to settle...\n\n"])

        try :
            if self._baudrate != 9600: #if is different than 9600, change the baudrate of the port to given baudrate again
                self.ser = self.fw.restartSerial(self._port, self._baudrate, timeout=self._serialTimeout)#due to a driver error on OSX, we need to restart 2 times
                self.ser = self.fw.restartSerial(self._port, self._baudrate, timeout=self._serialTimeout)
                self.at = AT.AT(serialHandle=self.ser, logger=self.logger)
                self.fw = FW.FW(serialHandle=self.ser, atHandle=self.at, logger=self.logger)
        except :
            self.qSerialUpload.put(['Error',"Error opening Comm port"])
            return

        self.ser.flushInput()
        sleep(3) #waits for the device restart
        try :
            if not self.at.enterATMode() :
                self.qSerialUpload.put(['Debug',"Error obtaining new Version\n"])
                try:
                    self.ser.close()
                    self.finishButton.config(state=tk.NORMAL, text="Finish") #enable the Next button if successfully update
                    self.labelUploading.set(UPFINISHED+"\n\nError obtain the new firmware version")
                except serial.SerialException as e:
                    self.logger.exception("Error closing Comm port")
                return
        except :
            self.qSerialUpload.put(['Error',"Communication Error"])
            return
        try :
            fwVersion = self.fw.checkFWVersion()
            if not fwVersion :
                self.qSerialUpload.put_nowait(['Debug',"Invalid response received\nCan't check for the new version"])
                self.ser.close()
                self.finishButton.config(state=tk.NORMAL, text="Finish") #enable the Next button if successfully update
                return
            else :
                newFwNumber = fwVersion.split(' ',1) # split into version and fw name
                newDevFw = newFwNumber[1].rsplit('\r',1)[0] # removes the \r at end of fw name
                newFwNumber = newFwNumber[0] # "converts" to string
                newFwNumber = newFwNumber.split('B',1)[0] # removes anything after the version number
                if '0.' in newFwNumber : #removes the 0. of the version number
                    newFwNumber = newFwNumber.split('.',1)[1]

                self.qSerialUpload.put_nowait(['Debug',"Update Finished\n\nNew Firmware Version: "+newFwNumber+' '+newDevFw])
        except :
            self.qSerialUpload.put_nowait(['Debug',"Invalid response received\nCan't check for the new version"])

        self.logger.info("tSerialUpload: Thread stopping")

        try:
            self.ser.close()
            self.finishButton.config(state=tk.NORMAL, text="Finish") #enable the Next button if successfully update
            self.labelUploading.set(UPFINISHED+"\n\nNew Firmware Version: "+newFwNumber+' '+newDevFw)
            self.labelDebug.set(UPFINISHED+'\n'+CLICKDEBUG)
        except serial.SerialException as e:
            self.logger.exception("Error closing Comm port")



    def _checkSerialGetVersionError(self):
        if self._checkSerialError :
            self.master.after(1000, self._checkSerialGetVersionError)
            if not self.tSerialGetVersion.isAlive():
                self.commProgressBar.stop()
                self._checkSerialError = False
                if not self.qSerialGetVersion.empty() :
                    msg = self.qSerialGetVersion.get()
                    tkMessageBox.showerror(message=msg, parent=self.master)
                    self.logger.error(msg)
                    self.qSerialGetVersion.task_done()
                    self._checkSerialGetVersionQueue = False
                    self.die()

                if self._checkSerialInitErrors() and self.tSerialGetVersionStop.is_set() :
                    self.createDevicesList()



    def _checkSerialInitErrors(self):
        if self._oldDevice :
            tkMessageBox.showerror(ERRDEV,OLDDEVICE, parent=self.master)
            self._startOver()
            return False

        if self._oldBootloader :
            tkMessageBox.showerror(ERRDEV,OLDBOOTLOADER, parent=self.master)
            self._startOver()
            return False

        if self._usbMode:
            tkMessageBox.showerror(ERRDEV,USBMODE, parent=self.master)
            self._startOver()
            return False

        if self._bootloader4:
            tkMessageBox.showerror(ERRDEV,BOOTLOADERNOTSUPPORTED, parent=self.master)
            self._startOver()
            return False

        if self._commFail :
            if tkMessageBox.askretrycancel(COMMTIMEOUT,
                        NODEVREPLY, parent=self.master) :
                self.ser.close()
                self._setCOMPort()

            else:
                self._startOver()
            return False

        if self._inBootloaderMode :
            tkMessageBox.showwarning(BOOTLOADERMODE,
                        BOOTLOADER, parent=self.master)

        return True


    def _initSerialGetVersionThread(self) :
        self.logger.info("Serial Version Thread Init")

        self.qSerialGetVersion = Queue.Queue()

        self.tSerialGetVersionStop = threading.Event()

        self.tSerialGetVersion = threading.Thread(target=self._SerialGetVersionThread)
        self.tSerialGetVersion.daemon = True

        try :
            self.tSerialGetVersion.start()
        except:
            self.logger.exception("Failed to start Serial Get Version Thread")


    def _SerialGetVersionThread(self):
        self.logger.info("tSerialGetVersion: Serial Get Version thread started")
        self._fwVersion = ''
        self._oldDevice = False
        self._usbMode = False
        self._commFail = False
        self._inBootloaderMode = False
        self._oldBootloader = False
        self._bootloader4 = False

        # setup the Serial and AT and FW classes
        try :
            self.ser = serial.Serial(self._port, self._baudrate,timeout=self._serialTimeout)
        except serial.SerialException as e:
            self.qSerialGetVersion.put("Failed to open port {}: {}".format(self._port,e.strerror))
            return

        try :
            self.at = AT.AT(serialHandle=self.ser, logger=self.logger)
            self.fw = FW.FW(serialHandle=self.ser, atHandle=self.at, logger=self.logger)
        except :
            self.qSerialGetVersion.put("Communication Error")
            return


        if self.args.bootloader :
            self._inBootloaderMode = True
            self._setBootloaderFolder(False)
            self._fwVersion = 'Unknown'
            self.tSerialGetVersionStop.set()
            return

        try :
            if not self.at.enterATMode() : #if comm fails
                if self._baudrate != 9600 : #changes the port baudrate to check if device is in bootloader mode
                    try :
                        self.ser = self.fw.restartSerial(self._port, baudrate=9600,timeout=self._serialTimeout) #due to a driver error on OSX, we need to restart 2 times
                        self.ser = self.fw.restartSerial(self._port, baudrate=9600,timeout=self._serialTimeout)
                    except serial.SerialException as e:
                        self.qSerialGetVersion.put("Failed to open port {}: {}".format(self._port,e.strerror))
                        return
                self.logger.debug("Failed to enter on AT mode.")
                self.logger.debug("Checking if device is in bootloader mode")
                try :
                    bootloaderVersion = int(self.fw.checkBootloaderVersion())
                    if not bootloaderVersion:
                        self.logger.info("tSerialGetVersion: Thread stopping")
                        self._commFail = True
                        return
                except serial.SerialException as e:
                    self.qSerialGetVersion.put("Failed to close port {}: {}".format(self._port,e.strerror))
                    return

                self._inBootloaderMode = True
                self._setBootloaderFolder(bootloaderVersion)
                self._fwVersion = 'Unknown'
                self.tSerialGetVersionStop.set()
                return
        except :
            self.qSerialGetVersion.put("Communication Error")
            return

        try :
            self._fwVersion = self.fw.checkFWVersion()
        except :
            self.qSerialGetVersion.put("Error obtaining the FW Version")
            return

        if self._fwVersion :
            try :
                self._fwVersion = self._fwVersion.split(' ',1)  # divides the version in two list elements, Firmware Version and Device Name
                self._deviceFwName = self._fwVersion[1].rsplit('\r',1)[0] # Eliminates the '\n' of the end of the name
                self._fwVersion = self._fwVersion[0] #store the version with the, possibly, letters (B and U)
                if '0.' in self._fwVersion : #removes the 0. of the version number
                    self._fwVersion = self._fwVersion.split('.',1)[1]

                if self._deviceFwName == '':
                    self._oldDevice = True
                    self.fw.exitATMode()
                    return
                if "B" not in self._fwVersion :
                    self._oldDevice = True
                    self.fw.exitATMode()
                    return
                elif "U" in self._fwVersion :
                    self._usbMode = True
                    self.fw.exitATMode()
                    return

                self._fwVersion = self._fwVersion.split('B',1)[0] #leaves only the version number on string
            except :
                self.qSerialGetVersion.put("Error Setting Version")
                return

            try :
                self.fw.enterProgramMode()
            except :
                self.qSerialGetVersion.put("Communication Error")
                return

            if self._baudrate != 9600 :
                try :
                    self.ser = self.fw.restartSerial(self._port, 9600,timeout=self._serialTimeout)
                    self.at = AT.AT(serialHandle=self.ser, logger=self.logger)
                    self.fw = FW.FW(serialHandle=self.ser, atHandle=self.at, logger=self.logger)
                except serial.SerialException as e:
                    self.qSerialGetVersion.put("Failed to open port {}: {}".format(self._port,e.strerror))
                    return

            sleep(0.05) #time for device reboot
            self._setBootloaderFolder()
        else : #in case of response from AT but no fwVersion response, sends comm error
            self.logger.info("tSerialGetVersion: Thread stopping")
            self._commFail = True
            self.fw.exitATMode() #make sure device quit AT Mode, if fails
            return

        self.logger.info("tSerialGetVersion: Thread stopping")
        self.tSerialGetVersionStop.set()


    def _setBootloaderFolder(self, version=False) :
        bootloaderVersion = version
        if not version:
            try :
                bootloaderVersion = int(self.fw.checkBootloaderVersion())
                if not bootloaderVersion:
                    self.logger.info("tSerialGetVersion: Thread stopping")
                    self._commFail = True
                    return
            except serial.SerialException as e:
                self.qSerialGetVersion.put("Failed to close port {}: {}".format(self._port,e.strerror))
                return
            sleep(2)

        self.logger.debug ("Bootloader Version: {}".format(bootloaderVersion))

        if (bootloaderVersion < 3) :
            self._oldDevice = True
            return

        if (bootloaderVersion == 4) :
            self._bootloader4 = True
            return

        if bootloaderVersion == 3 : #should check for the subversion is equals d, otherwise bootloader must be updated
            try :
                bootloaderSubVersion = self.fw.checkBootloaderSubVersion()
                if not bootloaderSubVersion:
                    self.logger.info("tSerialGetVersion: Thread stopping")
                    self._commFail = True
                    return
            except serial.SerialException as e:
                self.qSerialGetVersion.put("Failed to close port {}: {}".format(self._port,e.strerror))
                return

            self.logger.debug ("Sub Version: {}".format(bootloaderSubVersion))
            if bootloaderSubVersion not in ["d","D"] :
                self._oldBootloader = True
                return

        self._bootloaderFolder = 'BootloaderV{}'.format(bootloaderVersion) #only reaches here if is bootloader v3d
        return


    def _onDeviceSelect(self, evt):
        w = evt.widget
        self._listboxSelection = w.get(w.curselection())
        if self._listboxSelection :
            self.listNextButton.config(state=tk.ACTIVE) #enables the next button after selection

        if self._inBootloaderMode: #if comm fail, list all devices available and store it's properties here
            for id, devices in self.ordDevices.items() :
                if devices['Device Class'] in ['USB','Serial'] :
                    for dev in devices['Devices'] :
                        if (dev['Name'] == self._listboxSelection) :
                            self._deviceName = dev['Name']
                            self._deviceClass = self.originalDeviceClass = devices['Device Class']
                            self.frequency = dev['Frequency']
                            self.fileExtension = dev['Filename Extension']
                            self._newFwName = id
                            try :
                                if dev['Support LLAP'] :
                                    self._supportLLAP = True
                            except :
                                self._supportLLAP = False

        else :
            for id, devices in self.ordDevices.items() :
                if id == self._deviceFwName :
                    for dev in devices['Devices'] :
                            if (dev['Name'] == self._listboxSelection) :
                                self._deviceName = dev['Name']
                                self._deviceClass = self.originalDeviceClass = devices['Device Class']
                                self.frequency = dev['Frequency']
                                self.fileExtension = dev['Filename Extension']
                                self._newFwName = id
                                if (self._deviceClass in ['LLAP','LLAP2']) :
                                    self._supportLLAP = True
                                    self._serialFirmware = dev['Serial Firmware']
                                else :
                                    try :
                                        if dev['Support LLAP'] :
                                            self._supportLLAP = True
                                    except :
                                        self._supportLLAP = False
        return


    def _onLLAPSelect(self, evt) :
        w = evt.widget
        self._llapFirmware = w.get(w.curselection())
        if self._listboxSelection :
            self.listLLAPNextButton.config(state=tk.ACTIVE) #enables the next button after selection
        for id, devices in self.ordDevices.items() :
            if devices['Device Class'] == 'LLAP' :
                if devices['Description'] == self._llapFirmware : #if not the selected firmware, goes to next item on the ordDevices
                    for dev in devices['Devices'] :                #found the elements, now list the devices to find the specific one that was plugged in
                        if (self._xrfVersion in dev['Name']) :  # when found, copy the parameters to set the proper firmware file
                            self._deviceClass = devices['Device Class']
                            self.frequency = dev['Frequency']
                            self.fileExtension = dev['Filename Extension']
                            self._newFwName = id
                            return


    def _onOlderVersionSelect(self, evt) :
        w = evt.widget
        self._lastFwVersion = self.showVersion = w.get(w.curselection())
        if '0.' not in self.showVersion :
            self._lastFwVersion = '0.'+self._lastFwVersion

        if self._lastFwVersion :
            self.olderVersionNextButton.config(state=tk.ACTIVE) #enables the next button after selection


    def _startOver(self):
        self.logger.debug("Starting over")
        self.master.children[self._currentFrame].pack_forget()
        self.iframe.pack()
        self._currentFrame = 'introFrame'
        self.fw.sendCommit() #send commit to try remove device from bootloader mode
        self.ser.close()
        self.bootloaderVersion = False
        self.bootloaderSubVersion = False
        self._deviceClass = ''
        self._deviceName = ''
        self._deviceFwName = ''
        self.commPortCombobox.set(self._port)
        self.baudrateCombobox.set(str(self._baudrate))


    def _buildGrid(self, frame, quit=False, halfSize=False):
        self.logger.debug("Building Grid for {}".format(frame.winfo_name()))
        canvas = tk.Canvas(frame, bd=0, width=self._widthMain-4,
                               height=self._rowHeight, highlightthickness=0)
        canvas.grid(row=0, column=0, columnspan=self._columns)

        if halfSize:
            rows=self._rows/2
        else:
            rows=self._rows

        for r in range(rows):
            for c in range(self._columns):
                tk.Canvas(frame, bd=0,  #bg=("black" if r%2 and c%2 else "gray"),
                          highlightthickness=0,
                          width=(self._widthMain-4)/self._columns,
                          height=self._rowHeight
                          ).grid(row=r, column=c)

        if (quit):
            tk.Button(frame, text='Quit', command=self._endUpWiz
                      ).grid(row=rows-2, column=0, sticky=tk.E)


    def _endUpWiz(self):
        self.logger.debug("End Application")
        if hasattr(self, "master"):
            position = self.master.geometry().split("+")
            self.config.set('FirmwareUploader', 'window_width_offset', position[1])
            self.config.set('FirmwareUploader', 'window_height_offset', position[2])
            self.master.destroy()
        self._running = False


    def _cleanUp(self):
        self.logger.debug("Clean up and exit")
        if hasattr(self,'fw'):
            self.fw.sendCommit() #try to remove the device from bootloader mode
        if hasattr(self,'ser'):
            self.ser.close()
        self._writeConfig()


    def _checkArgs(self):
        self.logger.debug("Parse Args")
        parser = argparse.ArgumentParser(description='Update Wizard')
        parser.add_argument('-d', '--debug',
                            help='Enable debug output to console, overrides FirmwareUploader.cfg setting',
                            action='store_true')
        parser.add_argument('-l', '--log',
                            help='Override the debug logging level, DEBUG, INFO, WARNING, ERROR, CRITICAL'
                            )
        parser.add_argument('-b', '--bootloader',
                            help='Informs that device is already in bootloader Mode',
                            action='store_true')

        self.args = parser.parse_args()

    def _readConfig(self):
        self.logger.debug("Reading Config")

        self.config = ConfigParser.SafeConfigParser()

        # load defaults
        try:
            self.config.readfp(open(self._configFileDefault))
        except:
            self.logger.debug("Could Not Load Default Settings File")

        # read the user config file
        if not self.config.read(self._configFile):
            self.logger.debug("Could Not Load User Config, One Will be Created on Exit")

        if not self.config.sections():
            self.logger.debug("No Config Loaded, Quitting")
            sys.exit()


    def _writeConfig(self):
        self.logger.debug("Writing Config")
        with open(self._configFile, 'wb') as _configFile:
            self.config.write(_configFile)

    def _loadDevices(self):
        self.logger.debug("Loading device List")
        self.logger.debug("Downloading JSON File")
        request = self.downloadFile('json')

        if str(request) != '200' :
            tkMessageBox.showerror("Error","Error downloading JSON File\nError "+str(request), parent=self.master)
            sys.exit(1)

        try:
            self._usbCommon = json.loads(self.jsonFile)['USB']
            self._llapCommon = json.loads(self.jsonFile)['LLAP']
            self._llap2Common = json.loads(self.jsonFile)['LLAP2']
            self._serialCommon = json.loads(self.jsonFile)['Serial']
            self._devices = json.loads(self.jsonFile)['Devices']

        except :
            self.logger.debug("Could Not Load JSON File")
            sys.exit(1)



    def die(self):
        """For some reason we can not longer go forward
            Try cleaning up what we can and exit
        """
        self.logger.critical("DIE")
        if hasattr(self, 'ser') :
            self.logger.debug("Trying to close serial port")
            self.ser.close()
        self._endUpWiz()
        self._cleanUp()
        sys.exit(1)

if __name__ == "__main__":
    app = FirmwareUploader()
    app.on_execute()
