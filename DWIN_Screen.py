import time
import math
import serial
import struct
import threading


def _MAX(lhs, rhs):
	"""Helper function for max comparison"""
	return lhs if lhs > rhs else rhs


def _MIN(lhs, rhs):
	"""Helper function for min comparison"""
	return lhs if lhs < rhs else rhs


class T5UIC1_LCD:
	address = 0x2A
	DWIN_BufTail = [0xCC, 0x33, 0xC3, 0x3C]
	DWIN_SendBuf = []
	databuf = [None] * 26
	recnum = 0

	RECEIVED_NO_DATA = 0x00
	RECEIVED_SHAKE_HAND_ACK = 0x01

	FHONE = b'\xAA'

	DWIN_WIDTH = 272
	DWIN_HEIGHT = 480

	# 3-.0：The font size, 0x00-0x09, corresponds to the font size below:
	# 0x00=6*12   0x01=8*16   0x02=10*20  0x03=12*24  0x04=14*28
	# 0x05=16*32  0x06=20*40  0x07=24*48  0x08=28*56  0x09=32*64

	font6x12 = 0x00
	font8x16 = 0x01
	font10x20 = 0x02
	font12x24 = 0x03
	font14x28 = 0x04
	font16x32 = 0x05
	font20x40 = 0x06
	font24x48 = 0x07
	font28x56 = 0x08
	font32x64 = 0x09

	# Color
	Color_White = 0xFFFF
	Color_Yellow = 0xFF0F
	Color_Bg_Window = 0x31E8  # Popup background color
	Color_Bg_Blue = 0x1125  # Dark blue background color
	Color_Bg_Black = 0x0841  # Black background color
	Color_Bg_Red = 0xF00F  # Red background color
	Popup_Text_Color = 0xD6BA  # Popup font background color
	Line_Color = 0x3A6A  # Split line color
	Rectangle_Color = 0xEE2F  # Blue square cursor color
	Percent_Color = 0xFE29  # Percentage color
	BarFill_Color = 0x10E4  # Fill color of progress bar
	Select_Color = 0x33BB  # Selected color

	DWIN_FONT_MENU = font8x16
	DWIN_FONT_STAT = font10x20
	DWIN_FONT_HEAD = font10x20

	# Dwen serial screen initialization
	# Passing parameters: serial port number
	# DWIN screen uses serial port 1 to send
	def __init__(self, USARTx):
		"""Initialize DWIN screen with comprehensive error handling"""
		self._initialized = False
		self.lock = threading.Lock()  # Thread safety for serial operations
		
		try:
			# Validate input
			if not USARTx:
				raise ValueError("USARTx parameter cannot be empty")
			
			print(f"\nInitializing DWIN display on {USARTx}")
			
			# Initialize serial connection with error handling
			try:
				self.MYSERIAL1 = serial.Serial(
					USARTx, 
					115200, 
					timeout=2,  # Increased timeout for reliability
					write_timeout=2,  # Add write timeout
					exclusive=True  # Prevent multiple access
				)
				print(f"Serial connection established: {USARTx}")
			except serial.SerialException as e:
				raise RuntimeError(f"Failed to open serial port {USARTx}: {e}")
			except Exception as e:
				raise RuntimeError(f"Serial port initialization error: {e}")
			
			# Initialize communication
			print("Starting DWIN handshake...")
			handshake_attempts = 0
			max_handshake_attempts = 5
			
			while handshake_attempts < max_handshake_attempts:
				handshake_attempts += 1
				try:
					if self.Handshake():
						print("DWIN handshake successful")
						break
				except Exception as e:
					print(f"Handshake attempt {handshake_attempts} failed: {e}")
					if handshake_attempts < max_handshake_attempts:
						time.sleep(0.5)  # Wait before retry
						continue
					else:
						raise RuntimeError(f"Failed to establish handshake after {max_handshake_attempts} attempts")
			else:
				raise RuntimeError("DWIN handshake failed - display may not be connected or responding")
			
			# Initialize display
			try:
				self.JPG_ShowAndCache(0)
				self.Frame_SetDir(1)
				self.UpdateLCD()
				print("DWIN display initialized successfully")
				self._initialized = True
			except Exception as e:
				raise RuntimeError(f"Failed to initialize display: {e}")
				
		except Exception as e:
			print(f"Error initializing DWIN screen: {e}")
			self.cleanup()
			raise

	def Byte(self, bval):
		"""Add byte to buffer with validation"""
		try:
			if not isinstance(bval, (int, float)):
				raise ValueError(f"Byte value must be numeric, got {type(bval)}")
			val = int(bval)
			if val < 0 or val > 255:
				raise ValueError(f"Byte value must be 0-255, got {val}")
			self.DWIN_SendBuf += val.to_bytes(1, byteorder='big')
		except Exception as e:
			print(f"Error adding byte to buffer: {e}")
			raise

	def Word(self, wval):
		"""Add word to buffer with validation"""
		try:
			if not isinstance(wval, (int, float)):
				raise ValueError(f"Word value must be numeric, got {type(wval)}")
			val = int(wval)
			if val < 0 or val > 65535:
				raise ValueError(f"Word value must be 0-65535, got {val}")
			self.DWIN_SendBuf += val.to_bytes(2, byteorder='big')
		except Exception as e:
			print(f"Error adding word to buffer: {e}")
			raise

	def Long(self, lval):
		"""Add long to buffer with validation"""
		try:
			if not isinstance(lval, (int, float)):
				raise ValueError(f"Long value must be numeric, got {type(lval)}")
			val = int(lval)
			if val < 0 or val > 4294967295:
				raise ValueError(f"Long value must be 0-4294967295, got {val}")
			self.DWIN_SendBuf += val.to_bytes(4, byteorder='big')
		except Exception as e:
			print(f"Error adding long to buffer: {e}")
			raise

	def D64(self, value):
		"""Add 64-bit value to buffer with validation"""
		try:
			if not isinstance(value, (int, float)):
				raise ValueError(f"D64 value must be numeric, got {type(value)}")
			val = int(value)
			if val < 0 or val > 18446744073709551615:
				raise ValueError(f"D64 value out of range: {val}")
			self.DWIN_SendBuf += val.to_bytes(8, byteorder='big')
		except Exception as e:
			print(f"Error adding D64 to buffer: {e}")
			raise

	def String(self, string):
		"""Add string to buffer with validation"""
		try:
			if not isinstance(string, str):
				string = str(string)
			if len(string) > 255:  # Reasonable limit for display strings
				print(f"Warning: String truncated from {len(string)} to 255 characters")
				string = string[:255]
			self.DWIN_SendBuf += string.encode('utf-8')
		except Exception as e:
			print(f"Error adding string to buffer: {e}")
			raise

	# Send the data in the buffer and the packet end
	def Send(self):
		"""Send buffer contents with comprehensive error handling"""
		if not self._initialized:
			print("Warning: Attempting to send data before initialization complete")
			return False
			
		try:
			with self.lock:  # Thread safety
				if not self.DWIN_SendBuf:
					print("Warning: Empty send buffer")
					return False
				
				# Check serial connection
				if not self.MYSERIAL1 or not self.MYSERIAL1.is_open:
					raise RuntimeError("Serial port is not open")
				
				# Send data
				bytes_written = 0
				try:
					bytes_written += self.MYSERIAL1.write(self.DWIN_SendBuf)
					bytes_written += self.MYSERIAL1.write(self.DWIN_BufTail)
					self.MYSERIAL1.flush()  # Ensure data is sent
				except serial.SerialTimeoutException:
					print("Warning: Serial write timeout")
					return False
				except Exception as e:
					print(f"Error writing to serial port: {e}")
					return False
				
				# Reset buffer
				self.DWIN_SendBuf = self.FHONE
				time.sleep(0.001)  # Brief delay for hardware processing
				
				return True
				
		except Exception as e:
			print(f"Error in Send(): {e}")
			self.DWIN_SendBuf = self.FHONE  # Reset buffer even on error
			return False

	def Read(self, lend=1):
		bit = self.bus.read_i2c_block_data(self.address, 0, lend)
		if lend == 1:
			return bytes(bit)
		return bit

	# /*-------------------------------------- System variable function --------------------------------------*/

	# Handshake (1: Success, 0: Fail)
	def Handshake(self):
		"""Perform handshake with comprehensive error handling and timeout"""
		try:
			# Reset communication state
			self.recnum = 0
			self.databuf = [None] * 26
			
			# Clear any pending data
			if self.MYSERIAL1.in_waiting:
				self.MYSERIAL1.reset_input_buffer()
			
			# Send handshake command
			self.Byte(0x00)
			if not self.Send():
				return False
			
			# Wait for response with timeout
			timeout_start = time.time()
			timeout_duration = 2.0  # 2 second timeout
			
			while self.recnum < 26 and (time.time() - timeout_start) < timeout_duration:
				if self.MYSERIAL1.in_waiting:
					try:
						byte_data = self.MYSERIAL1.read(1)
						if not byte_data:
							continue
							
						self.databuf[self.recnum] = struct.unpack('B', byte_data)[0]
						
						# Validate start byte
						if self.databuf[0] != 0xAA:
							if self.recnum > 0:
								self.recnum = 0
								self.databuf = [None] * 26
							continue
						
						self.recnum += 1
						
						# Check if we have enough data for validation
						if self.recnum >= 4:
							break
							
					except struct.error as e:
						print(f"Error unpacking handshake data: {e}")
						continue
					except Exception as e:
						print(f"Error reading handshake response: {e}")
						return False
				else:
					time.sleep(0.010)  # Small delay before checking again
			
			# Validate handshake response
			success = (self.recnum >= 3 and 
					  self.databuf[0] == 0xAA and 
					  self.databuf[1] == 0)
			
			if success and self.recnum >= 4:
				try:
					char2 = chr(self.databuf[2]) if self.databuf[2] < 128 else '?'
					char3 = chr(self.databuf[3]) if self.databuf[3] < 128 else '?'
					success = success and char2 == 'O' and char3 == 'K'
				except (ValueError, IndexError):
					success = False
			
			if success:
				print("Handshake completed successfully")
			else:
				print(f"Handshake failed - received {self.recnum} bytes: {self.databuf[:self.recnum]}")
			
			return success
			
		except Exception as e:
			print(f"Exception during handshake: {e}")
			return False

	# Set the backlight luminance
	#  luminance: (0x00-0xFF)
	def Backlight_SetLuminance(self, luminance):
		"""Set backlight with input validation and error handling"""
		try:
			if not isinstance(luminance, (int, float)):
				raise ValueError(f"Luminance must be numeric, got {type(luminance)}")
			
			# Clamp luminance to valid range
			luminance = int(luminance)
			if luminance < 0:
				luminance = 0
			elif luminance > 255:
				luminance = 255
			
			# Apply minimum brightness (0x1F = 31)
			safe_luminance = _MAX(luminance, 0x1F)
			
			self.Byte(0x30)
			self.Byte(safe_luminance)
			return self.Send()
			
		except Exception as e:
			print(f"Error setting backlight luminance: {e}")
			return False

	# Set screen display direction
	#  dir: 0=0°, 1=90°, 2=180°, 3=270°
	def Frame_SetDir(self, dir):
		"""Set frame direction with input validation"""
		try:
			if not isinstance(dir, (int, float)):
				raise ValueError(f"Direction must be numeric, got {type(dir)}")
			
			dir = int(dir)
			if dir < 0 or dir > 3:
				raise ValueError(f"Direction must be 0-3, got {dir}")
			
			self.Byte(0x34)
			self.Byte(0x5A)
			self.Byte(0xA5)
			self.Byte(dir)
			return self.Send()
			
		except Exception as e:
			print(f"Error setting frame direction: {e}")
			return False

	# Update display
	def UpdateLCD(self):
		"""Update LCD display with error handling"""
		try:
			self.Byte(0x3D)
			return self.Send()
		except Exception as e:
			print(f"Error updating LCD: {e}")
			return False

	# /*---------------------------------------- Drawing functions ----------------------------------------*/

	# Clear screen
	#  color: Clear screen color
	def Frame_Clear(self, color):
		"""Clear screen with input validation"""
		try:
			if not isinstance(color, (int, float)):
				raise ValueError(f"Color must be numeric, got {type(color)}")
			
			color = int(color)
			if color < 0 or color > 65535:
				raise ValueError(f"Color must be 0-65535, got {color}")
			
			self.Byte(0x01)
			self.Word(color)
			return self.Send()
			
		except Exception as e:
			print(f"Error clearing frame: {e}")
			return False

	# Draw a point
	#  width: point width   0x01-0x0F
	#  height: point height 0x01-0x0F
	#  x,y: upper left point
	def Draw_Point(self, width, height, x, y):
		self.Byte(0x02)
		self.Byte(width)
		self.Byte(height)
		self.Word(x)
		self.Word(y)
		self.Send()

	# ___________________________________Draw points ____________________________________________\\
	# Command: frame header + command + color of drawing point + pixel size of drawing point (Nx, Ny) + position of drawing point [(X1,Y1)+(X2,Y2)+.........]+ End of frame
	# Set point; processing time=0.4*Nx*Ny*number of set points uS.
	# Color: Set point color.
	# Nx: Actual pixel size in X direction, 0x01-0x0F.
	# Ny: Actual pixel size in Y direction, 0x01-0x0F.
	# (Xn, Yn): Set point coordinate sequence.
	# Example: AA 02 F8 00 04 04 00 08 00 08 CC 33 C3 3C
	# /**************Drawing point protocol command can draw multiple points at a time (this function only draws pixels in one position) ********** *****/
	def DrawPoint(self, Color, Nx, Ny, X1, Y1):			  # Draw some
		self.Byte(0x02)
		self.Word(Color)
		self.Byte(int(Nx))
		self.Byte(int(Ny))
		self.Word(int(X1))
		self.Word(int(Y1))
		self.Send()

	#  Draw a line
	#   color: Line segment color
	#   xStart/yStart: Start point
	#   xEnd/yEnd: End point
	def Draw_Line(self, color, xStart, yStart, xEnd, yEnd):
		self.Byte(0x03)
		self.Word(color)
		self.Word(xStart)
		self.Word(yStart)
		self.Word(xEnd)
		self.Word(yEnd)
		self.Send()

	#  Draw a rectangle
	#   mode: 0=frame, 1=fill, 2=XOR fill
	#   color: Rectangle color
	#   xStart/yStart: upper left point
	#   xEnd/yEnd: lower right point
	def Draw_Rectangle(self, mode, color, xStart, yStart, xEnd, yEnd):
		"""Draw rectangle with input validation"""
		def build_command():
			# Validate mode
			if not (0 <= int(mode) <= 2):
				raise ValueError(f"Mode must be 0-2, got {mode}")
			
			# Validate and clamp coordinates
			x1 = _MAX(0, _MIN(int(xStart), self.DWIN_WIDTH - 1))
			y1 = _MAX(0, _MIN(int(yStart), self.DWIN_HEIGHT - 1))
			x2 = _MAX(0, _MIN(int(xEnd), self.DWIN_WIDTH - 1))
			y2 = _MAX(0, _MIN(int(yEnd), self.DWIN_HEIGHT - 1))
			
			# Ensure proper ordering
			if x1 > x2:
				x1, x2 = x2, x1
			if y1 > y2:
				y1, y2 = y2, y1
			
			self.Byte(0x05)
			self.Byte(int(mode))
			self.Word(int(color))
			self.Word(x1)
			self.Word(y1)
			self.Word(x2)
			self.Word(y2)
		
		return self._safe_send_command(build_command)

	#  Move a screen area
	#   mode: 0, circle shift; 1, translation
	#   dir: 0=left, 1=right, 2=up, 3=down
	#   dis: Distance
	#   color: Fill color
	#   xStart/yStart: upper left point
	#   xEnd/yEnd: bottom right point
	def Frame_AreaMove(self, mode, dir, dis, color, xStart, yStart, xEnd, yEnd):
		self.Byte(0x09)
		self.Byte((mode << 7) | dir)
		self.Word(dis)
		self.Word(color)
		self.Word(xStart)
		self.Word(yStart)
		self.Word(xEnd)
		self.Word(yEnd)
		self.Send()

	# ____________________________Draw a circle________________________________\\
	# Color: circle color
	# x0: the abscissa of the center of the circle
	# y0: ordinate of the center of the circle
	# r: circle radius
	def Draw_Circle(self, Color, x0, y0, r):  # Draw a circle
		b = 0
		a = 0
		while(a <= b):
			b = math.sqrt(r * r - a * a)
			while(a == 0):
				b = b - 1
				break
			self.DrawPoint(Color, 1, 1, x0 + a, y0 + b)		               # Draw some sector 1
			self.DrawPoint(Color, 1, 1, x0 + b, y0 + a)		               # Draw some sector 2
			self.DrawPoint(Color, 1, 1, x0 + b, y0 - a)		               # Draw some sector 3
			self.DrawPoint(Color, 1, 1, x0 + a, y0 - b)		               # Draw some sector 4

			self.DrawPoint(Color, 1, 1, x0 - a, y0 - b)		              # Draw some sector 5
			self.DrawPoint(Color, 1, 1, x0 - b, y0 - a)		              # Draw some sector 6
			self.DrawPoint(Color, 1, 1, x0 - b, y0 + a)		              # Draw some sector 7
			self.DrawPoint(Color, 1, 1, x0 - a, y0 + b)		              # Draw some sector 8
			a += 1

	# ____________________________Circular Filling________________________________\\
	# FColor: circle fill color
	# x0: the abscissa of the center of the circle
	# y0: ordinate of the center of the circle
	# r: circle radius
	def CircleFill(self, FColor, x0, y0, r):  # Round filling
		b = 0
		for i in range(r, 0, -1):
			a = 0
			while(a <= b):
				b = math.sqrt(i * i - a * a)
				while(a == 0):
					b = b - 1
					break
				self.DrawPoint(FColor, 2, 2, x0 + a, y0 + b)  # Draw some sector 1
				self.DrawPoint(FColor, 2, 2, x0 + b, y0 + a)  # raw some sector 2
				self.DrawPoint(FColor, 2, 2, x0 + b, y0 - a)  # Draw some sector 3
				self.DrawPoint(FColor, 2, 2, x0 + a, y0 - b)  # Draw some sector 4

				self.DrawPoint(FColor, 2, 2, x0 - a, y0 - b)  # Draw some sector 5
				self.DrawPoint(FColor, 2, 2, x0 - b, y0 - a)  # Draw some sector 6
				self.DrawPoint(FColor, 2, 2, x0 - b, y0 + a)  # Draw some sector 7
				self.DrawPoint(FColor, 2, 2, x0 - a, y0 + b)  # Draw some sector 8
				a = a + 2

	# /*---------------------------------------- Text related functions ----------------------------------------*/

	#  Draw a string
	#   widthAdjust: True=self-adjust character width; False=no adjustment
	#   bShow: True=display background color; False=don't display background color
	#   size: Font size
	#   color: Character color
	#   bColor: Background color
	#   x/y: Upper-left coordinate of the string
	#   *string: The string
	def Draw_String(self, widthAdjust, bShow, size, color, bColor, x, y, string):
		"""Draw string with comprehensive input validation"""
		def build_command():
			# Validate inputs
			if not isinstance(string, str):
				raise ValueError("String must be a string type")
			if len(string) > 100:  # Reasonable limit
				raise ValueError(f"String too long: {len(string)} characters")
			
			# Validate coordinates
			if not (0 <= x < self.DWIN_WIDTH and 0 <= y < self.DWIN_HEIGHT):
				raise ValueError(f"Coordinates out of bounds: ({x}, {y})")
			
			# Validate font size
			if not (0 <= size <= 9):
				raise ValueError(f"Font size must be 0-9, got {size}")
			
			self.Byte(0x11)
			# Bit 7: widthAdjust, Bit 6: bShow, Bit 5-4: Unused (0), Bit 3-0: size
			self.Byte((bool(widthAdjust) * 0x80) | (bool(bShow) * 0x40) | int(size))
			self.Word(int(color))
			self.Word(int(bColor))
			self.Word(int(x))
			self.Word(int(y))
			self.String(string)
		
		return self._safe_send_command(build_command)

	#  Draw a positive integer
	#   bShow: True=display background color; False=don't display background color
	#   zeroFill: True=zero fill; False=no zero fill
	#   zeroMode: 1=leading 0 displayed as 0; 0=leading 0 displayed as a space
	#   size: Font size
	#   color: Character color
	#   bColor: Background color
	#   iNum: Number of digits
	#   x/y: Upper-left coordinate
	#   value: Integer value
	def Draw_IntValue(self, bShow, zeroFill, zeroMode, size, color, bColor, iNum, x, y, value):
		"""Draw integer value with comprehensive validation"""
		def build_command():
			# Validate coordinates
			if not (0 <= int(x) < self.DWIN_WIDTH and 0 <= int(y) < self.DWIN_HEIGHT):
				raise ValueError(f"Coordinates out of bounds: ({x}, {y})")
			
			# Validate font size
			if not (0 <= int(size) <= 9):
				raise ValueError(f"Font size must be 0-9, got {size}")
			
			# Validate digit count
			if not (1 <= int(iNum) <= 10):
				raise ValueError(f"Digit count must be 1-10, got {iNum}")
			
			# Validate value range (64-bit)
			if not (-9223372036854775808 <= int(value) <= 9223372036854775807):
				raise ValueError(f"Value out of range: {value}")
			
			self.Byte(0x14)
			# Bit 7: bshow, Bit 6: 1 = signed; 0 = unsigned, Bit 5: zeroFill, Bit 4: zeroMode, Bit 3-0: size
			self.Byte((bool(bShow) * 0x80) | (bool(zeroFill) * 0x20) | (bool(zeroMode) * 0x10) | int(size))
			self.Word(int(color))
			self.Word(int(bColor))
			self.Byte(int(iNum))
			self.Byte(0)  # fNum
			self.Word(int(x))
			self.Word(int(y))
			self.D64(int(value))
		
		return self._safe_send_command(build_command)

	#  Draw a floating point number
	#   bShow: True=display background color; False=don't display background color
	#   zeroFill: True=zero fill; False=no zero fill
	#   zeroMode: 1=leading 0 displayed as 0; 0=leading 0 displayed as a space
	#   size: Font size
	#   color: Character color
	#   bColor: Background color
	#   iNum: Number of whole digits
	#   fNum: Number of decimal digits
	#   x/y: Upper-left point
	#   value: Float value
	def Draw_FloatValue(self, bShow, zeroFill, zeroMode, size, color, bColor, iNum, fNum, x, y, value):
		"""Draw float value with comprehensive validation"""
		def build_command():
			# Validate coordinates
			if not (0 <= int(x) < self.DWIN_WIDTH and 0 <= int(y) < self.DWIN_HEIGHT):
				raise ValueError(f"Coordinates out of bounds: ({x}, {y})")
			
			# Validate font size
			if not (0 <= int(size) <= 9):
				raise ValueError(f"Font size must be 0-9, got {size}")
			
			# Validate digit counts
			if not (1 <= int(iNum) <= 10):
				raise ValueError(f"Integer digits must be 1-10, got {iNum}")
			if not (0 <= int(fNum) <= 10):
				raise ValueError(f"Fraction digits must be 0-10, got {fNum}")
			
			# Convert float to appropriate integer representation
			try:
				int_value = int(float(value))
			except (ValueError, OverflowError):
				raise ValueError(f"Invalid float value: {value}")
			
			self.Byte(0x14)
			self.Byte((bool(bShow) * 0x80) | (bool(zeroFill) * 0x20) | (bool(zeroMode) * 0x10) | int(size))
			self.Word(int(color))
			self.Word(int(bColor))
			self.Byte(int(iNum))
			self.Byte(int(fNum))
			self.Word(int(x))
			self.Word(int(y))
			self.Long(int_value)
		
		return self._safe_send_command(build_command)

	def Draw_Signed_Float(self, size, bColor, iNum, fNum, x, y, value):
		"""Draw signed float with improved error handling"""
		try:
			float_value = float(value)
			
			if float_value < 0:
				# Draw negative sign
				if not self.Draw_String(False, True, size, self.Color_White, bColor, x - 6, y, "-"):
					return False
				if not self.Draw_FloatValue(True, True, 0, size, self.Color_White, bColor, iNum, fNum, x, y, -float_value):
					return False
			else:
				# Draw space for positive numbers
				if not self.Draw_String(False, True, size, self.Color_White, bColor, x - 6, y, " "):
					return False
				if not self.Draw_FloatValue(True, True, 0, size, self.Color_White, bColor, iNum, fNum, x, y, float_value):
					return False
			
			return True
			
		except (ValueError, TypeError) as e:
			print(f"Error drawing signed float: {e}")
			return False

	# /*---------------------------------------- Picture related functions ----------------------------------------*/

	#  Draw JPG and cached in #0 virtual display area
	# id: Picture ID
	def JPG_ShowAndCache(self, id):
		"""Show and cache JPG with input validation"""
		def build_command():
			if not isinstance(id, (int, float)):
				raise ValueError(f"Picture ID must be numeric, got {type(id)}")
			
			pic_id = int(id)
			if pic_id < 0 or pic_id > 255:
				raise ValueError(f"Picture ID must be 0-255, got {pic_id}")
			
			self.Word(0x2200)
			self.Byte(pic_id)
		
		return self._safe_send_command(build_command)

	#  Draw an Icon
	#   libID: Icon library ID
	#   picID: Icon ID
	#   x/y: Upper-left point
	def ICON_Show(self, libID, picID, x, y):
		"""Show icon with input validation and bounds checking"""
		def build_command():
			# Validate coordinates and clamp to screen bounds
			safe_x = _MAX(0, _MIN(int(x), self.DWIN_WIDTH - 1))
			safe_y = _MAX(0, _MIN(int(y), self.DWIN_HEIGHT - 1))
			
			# Validate IDs
			if not (0 <= int(libID) <= 127):  # 7-bit limit due to 0x80 OR
				raise ValueError(f"Library ID must be 0-127, got {libID}")
			if not (0 <= int(picID) <= 255):
				raise ValueError(f"Picture ID must be 0-255, got {picID}")
			
			self.Byte(0x23)
			self.Word(safe_x)
			self.Word(safe_y)
			self.Byte(0x80 | int(libID))
			self.Byte(int(picID))
		
		return self._safe_send_command(build_command)

	# Unzip the JPG picture to a virtual display area
	#  n: Cache index
	#  id: Picture ID
	def JPG_CacheToN(self, n, id):
		self.Byte(0x25)
		self.Byte(n)
		self.Byte(id)
		self.Send()

	def JPG_CacheTo1(self, id):
		self.JPG_CacheToN(1, id)

	#  Copy area from virtual display area to current screen
	#   cacheID: virtual area number
	#   xStart/yStart: Upper-left of virtual area
	#   xEnd/yEnd: Lower-right of virtual area
	#   x/y: Screen paste point
	def Frame_AreaCopy(self, cacheID, xStart, yStart, xEnd, yEnd, x, y):
		self.Byte(0x27)
		self.Byte(0x80 | cacheID)
		self.Word(xStart)
		self.Word(yStart)
		self.Word(xEnd)
		self.Word(yEnd)
		self.Word(x)
		self.Word(y)
		self.Send()

	def Frame_TitleCopy(self, id, x1, y1, x2, y2):
		self.Frame_AreaCopy(id, x1, y1, x2, y2, 14, 8)

	#  Animate a series of icons
	#   animID: Animation ID; 0x00-0x0F
	#   animate: True on; False off;
	#   libID: Icon library ID
	#   picIDs: Icon starting ID
	#   picIDe: Icon ending ID
	#   x/y: Upper-left point
	#   interval: Display time interval, unit 10mS
	def ICON_Animation(self, animID, animate, libID, picIDs, picIDe, x, y, interval):
		if x > self.DWIN_WIDTH - 1:
			x = self.DWIN_WIDTH - 1
		if y > self.DWIN_HEIGHT - 1:
			y = self.DWIN_HEIGHT - 1
		self.Byte(0x28)
		self.Word(x)
		self.Word(y)
		# Bit 7: animation on or off
		# Bit 6: start from begin or end
		# Bit 5-4: unused (0)
		# Bit 3-0: animID
		self.Byte((animate * 0x80) | 0x40 | animID)
		self.Byte(libID)
		self.Byte(picIDs)
		self.Byte(picIDe)
		self.Byte(interval)
		self.Send()

	#  Animation Control
	#   state: 16 bits, each bit is the state of an animation id
	def ICON_AnimationControl(self, state):
		self.Byte(0x28)
		self.Word(state)
		self.Send()

	# ____________________________Display QR code ________________________________\\
	# QR_Pixel: The pixel size occupied by each point of the QR code: 0x01-0x0F (1-16)
	# (Nx, Ny): The coordinates of the upper left corner displayed by the QR code
	# str: multi-bit data
	# /**************The size of the QR code is (46*QR_Pixel)*(46*QR_Pixle) dot matrix************/
	def QR_Code(self, QR_Pixel, Xs, Ys, data):	    # Display QR code
		self.Byte(0x21)  # Display QR code instruction
		self.Word(Xs)  # Two-dimensional code Xs coordinate high eight
		self.Word(Ys)  # The Ys coordinate of the QR code is eight high

		if(QR_Pixel <= 6):  # Set the upper limit of pixels according to the actual screen size
			self.Byte(QR_Pixel)  # Two-dimensional code pixel size
		else:
			self.Byte(0x06)  # The pixel size of the QR code exceeds the default of 1
		self.String(data)
		self.Send()
	# /*---------------------------------------- Memory functions ----------------------------------------*/
	#  The LCD has an additional 32KB SRAM and 16KB Flash

	#  Data can be written to the sram and save to one of the jpeg page files

	#  Write Data Memory
	#   command 0x31
	#   Type: Write memory selection; 0x5A=SRAM; 0xA5=Flash
	#   Address: Write data memory address; 0x000-0x7FFF for SRAM; 0x000-0x3FFF for Flash
	#   Data: data
	#
	#   Flash writing returns 0xA5 0x4F 0x4B

	#  Read Data Memory
	#   command 0x32
	#   Type: Read memory selection; 0x5A=SRAM; 0xA5=Flash
	#   Address: Read data memory address; 0x000-0x7FFF for SRAM; 0x000-0x3FFF for Flash
	#   Length: leangth of data to read; 0x01-0xF0
	#
	#   Response:
	#     Type, Address, Length, Data

	#  Write Picture Memory
	#   Write the contents of the 32KB SRAM data memory into the designated image memory space
	#   Issued: 0x5A, 0xA5, PIC_ID
	#   Response: 0xA5 0x4F 0x4B
	#
	#   command 0x33
	#   0x5A, 0xA5
	#   PicId: Picture Memory location, 0x00-0x0F
	#
	#   Flash writing returns 0xA5 0x4F 0x4B
	# def sendPicture(self, PicId, SRAM, Address, data):
	# 	self.Byte(0x31)
	# 	if SRAM:
	# 		self.Byte(0x5A)
	# 	else:
	# 		self.Byte(0xA5)
	# 	self.Word(Address)
	# 	self.DWIN_SendBuf += data
	# 	self.Send()

	# --------------------------------------------------------------#
	# --------------------------------------------------------------#

	def _safe_send_command(self, command_builder):
		"""Safely execute a command building function and send it"""
		try:
			if not self._initialized:
				print("Warning: Display not initialized")
				return False
				
			# Execute the command builder
			command_builder()
			return self.Send()
			
		except Exception as e:
			print(f"Error executing display command: {e}")
			# Reset buffer on error
			self.DWIN_SendBuf = self.FHONE
			return False

	def cleanup(self):
		"""Clean up resources"""
		try:
			print("Cleaning up DWIN display...")
			
			# Clear display if possible
			if self._initialized and hasattr(self, 'MYSERIAL1') and self.MYSERIAL1:
				try:
					self.Frame_Clear(self.Color_Bg_Black)
				except:
					pass  # Ignore errors during cleanup
			
			# Close serial connection
			if hasattr(self, 'MYSERIAL1') and self.MYSERIAL1:
				try:
					self.MYSERIAL1.close()
					print("Serial connection closed")
				except Exception as e:
					print(f"Error closing serial connection: {e}")
			
			self._initialized = False
			
		except Exception as e:
			print(f"Error during cleanup: {e}")

	def __del__(self):
		"""Destructor to ensure cleanup"""
		try:
			self.cleanup()
		except:
			pass  # Ignore errors in destructor

	def is_connected(self):
		"""Check if display is connected and responding"""
		try:
			return (self._initialized and 
					hasattr(self, 'MYSERIAL1') and 
					self.MYSERIAL1 and 
					self.MYSERIAL1.is_open)
		except:
			return False
