#!/usr/bin/env python

""" FW Uploader Class


"""

import serial
import sys
import time
import AT
import logging

class FW():

	_line_number = 0
	_device_filename = "COM3"
	_baud_rate = 9600
	_timeout = 1.5 #timeout for receiving bytes functions

	def __init__(self, atHandle=None, serialHandle=None, logger=None, event=None):
		self._serial = serialHandle or serial.Serial()
		self._at = atHandle or AT.AT()
		if logger == None:
			logging.basicConfig(level=logging.DEBUG)
			self.logger = logging.getLogger()
		else:
			self.logger = logger

		self.event = event

	def startSerial(self, port, baudrate, timeout) :
		"""
			Starts the serial port with
			the specified parameters
		"""
		try :
			ser = serial.Serial(port, baudrate, timeout=timeout)
		except serial.SerialException as e:
			self.logger.error ("Failed to open port {}: {}".format(self._device_filename,e.strerror))
			sys.exit(2)

		return ser

	def error(self, message, code) :
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
			waits for an specified time to their response
		"""
		retry = 0
		received = False
		while not received and retry < retries:
			self._serial.flushInput();
			self._serial.write(send)
			received = self._serial.read()
			retry += 1
			if received:
				if received in response:
					return received
		#in case of error, return False
		return False

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

	#def waitResponse(self, response) :
	def waitResponse(self, response) :
		"""
		Waits on the serial for the response
		until timeout or response received
		"""
		data = ""
		data = self._serial.read()
		if data == response :
			return True
		else :
			return False

	def sendFirmware(self, fw) :
	############ send the bin file  ############
		"""
		Sends the firmware file stored before to
		the device line by line, then returns the
		total number of lines are sent (or false if fails)
		"""
		self._line_number = 0
		time.sleep(1.5)
		len_fw = len(fw)
		i = 10
		for file_line in fw :
			data = ""
			data = self._serial.read()
			if data == "":
				self.logger.debug ("FW: returned blank expecting R")
				return self._line_number
			elif data != "R" :
				self.logger.debug ("FW: sendFirmware data = {}".format(ord(data)))
				return self._line_number

			self._line_number += 1
			self._serial.write(file_line) #send the line
			data = ""
			data = self._serial.read()
			# TODO: try to improve this part, be more readable
			if data == "":
				self.logger.debug ("FW: returned blank expecting A")
				return self._line_number
			elif data != "A" :
				if data == "N" : # retry once
					self._serial.write(file_line)
					data = ""
					data = self._serial.read()
					if data == "A" :
						data = ""
						continue
					elif data in ["n","N"] :	#if still not working, restarts the device
						sel.logger.debug ("Restarting device...")
						self._at.endSerial()
						#TODO reset and try again
						sys.exit(-1)
					else :	#if doesn't receive any acceptable answer, exits the program
						return self._line_number
			if (self._line_number >= ((len_fw*i)/100)) :
				self.logger.debug ("FW: {}% Completed".format(i))	# debug
				i += 10

		return self._line_number

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
			sys.exit(2)

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

	def prepareFirmwareFile(self, fw_filename) :
		"""
			Store the content of the FW File (.bin file)
			to be written on the device
		"""

		try :
			f = open(fw_filename, "r")
		except IOError as e:
			self.logger.critical("Could not open firmware file {} for reading: {}\n".format(fw_filename,e.strerror))
			sys.exit(2)
		firmware = [line.rstrip() for line in f] #rstrip() removes the whitespaces \f , \n , \r , \t , \v , \x and blank on the end of the line
		line = ""
		for line in firmware:
			if len(line) != 67 :
				self.logger.critical("Line with invalid length of {} in firmware file\n".format(len(line)))
				sys.exit(2)
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

#		if (baud == len(StdBaudrates)) :
		self.logger.debug("FW: Baudrate not supported")
		return False
#		else :
#			return baudrate

"""
