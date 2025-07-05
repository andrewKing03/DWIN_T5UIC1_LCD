from asyncio.tasks import sleep
import threading
import errno
import select
import socket
import json
import requests
from requests.exceptions import ConnectionError
import atexit
import time
import asyncio
from json.decoder import JSONDecodeError

class xyze_t:
	x = 0.0
	y = 0.0
	z = 0.0
	e = 0.0
	home_x = False
	home_y = False
	home_z = False

	def homing(self):
		self.home_x = False
		self.home_y = False
		self.home_z = False


class AxisEnum:
	X_AXIS = 0
	A_AXIS = 0
	Y_AXIS = 1
	B_AXIS = 1
	Z_AXIS = 2
	C_AXIS = 2
	E_AXIS = 3
	X_HEAD = 4
	Y_HEAD = 5
	Z_HEAD = 6
	E0_AXIS = 3
	E1_AXIS = 4
	E2_AXIS = 5
	E3_AXIS = 6
	E4_AXIS = 7
	E5_AXIS = 8
	E6_AXIS = 9
	E7_AXIS = 10
	ALL_AXES = 0xFE
	NO_AXIS = 0xFF


class HMI_value_t:
	E_Temp = 0
	Bed_Temp = 0
	Fan_speed = 0
	print_speed = 100
	Max_Feedspeed = 0.0
	Max_Acceleration = 0.0
	Max_Jerk = 0.0
	Max_Step = 0.0
	Move_X_scale = 0.0
	Move_Y_scale = 0.0
	Move_Z_scale = 0.0
	Move_E_scale = 0.0
	offset_value = 0.0
	show_mode = 0  # -1: Temperature control    0: Printing temperature


class HMI_Flag_t:
	language = 0
	pause_flag = False
	pause_action = False
	print_finish = False
	done_confirm_flag = False
	select_flag = False
	home_flag = False
	heat_flag = False  # 0: heating done  1: during heating
	ETempTooLow_flag = False
	leveling_offset_flag = False
	feedspeed_axis = AxisEnum()
	acc_axis = AxisEnum()
	jerk_axis = AxisEnum()
	step_axis = AxisEnum()


class buzz_t:
	def tone(self, t, n):
		pass


class material_preset_t:
	def __init__(self, name, hotend_temp, bed_temp, fan_speed=100):
		self.name = name
		self.hotend_temp = hotend_temp
		self.bed_temp = bed_temp
		self.fan_speed = fan_speed


class KlippySocket:
	def __init__(self, uds_filename, callback=None):
		self.webhook_socket_create(uds_filename)
		self.lock = threading.Lock()
		self.poll = select.poll()
		self.stop_threads = False
		self.poll.register(self.webhook_socket, select.POLLIN | select.POLLHUP)
		self.socket_data = ""
		self.t = threading.Thread(target=self.polling)
		self.callback = callback
		self.lines = []
		self.t.start()
		atexit.register(self.klippyExit)

	def klippyExit(self):
		print("Shuting down Klippy Socket")
		self.stop_threads = True
		self.t.join()

	def webhook_socket_create(self, uds_filename):
		self.webhook_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self.webhook_socket.setblocking(0)
		print("Waiting for connect to %s\n" % (uds_filename,))
		while 1:
			try:
				self.webhook_socket.connect(uds_filename)
			except socket.error as e:
				if e.errno == errno.ECONNREFUSED:
					time.sleep(0.1)
					continue
				print(
					"Unable to connect socket %s [%d,%s]\n" % (
						uds_filename, e.errno,
						errno.errorcode[e.errno]
					))
				exit(-1)
			break
		print("Connection.\n")

	def process_socket(self):
		data = self.webhook_socket.recv(4096).decode()
		if not data:
			print("Socket closed\n")
			exit(0)
		parts = data.split('\x03')
		parts[0] = self.socket_data + parts[0]
		self.socket_data = parts.pop()
		for line in parts:
			if self.callback:
				self.callback(line)

	def queue_line(self, line):
		with self.lock:
			self.lines.append(line)

	def send_line(self):
		if len(self.lines) == 0:
			return
		line = self.lines.pop(0).strip()
		if not line or line.startswith('#'):
			return
		try:
			m = json.loads(line)
		except JSONDecodeError:
			print("ERROR: Unable to parse line\n")
			return
		cm = json.dumps(m, separators=(',', ':'))
		wdm = '{}\x03'.format(cm)
		self.webhook_socket.send(wdm.encode())

	def polling(self):
		while True:
			if self.stop_threads:
				break
			res = self.poll.poll(1000.)
			for fd, event in res:
				self.process_socket()
			with self.lock:
				self.send_line()


class MoonrakerSocket:
	def __init__(self, address, port, api_key):
		self.s = requests.Session()
		self.s.headers.update({
			'X-Api-Key': api_key,
			'Content-Type': 'application/json'
		})
		self.base_address = 'http://' + address + ':' + str(port)


class PrinterData:
	event_loop = None
	HAS_HOTEND = True
	HOTENDS = 1
	HAS_HEATED_BED = True
	HAS_FAN = False
	HAS_ZOFFSET_ITEM = True
	HAS_ONESTEP_LEVELING = False
	HAS_PREHEAT = True
	HAS_BED_PROBE = False
	PREVENT_COLD_EXTRUSION = True
	EXTRUDE_MINTEMP = 170
	EXTRUDE_MAXLENGTH = 200

	HEATER_0_MAXTEMP = 275
	HEATER_0_MINTEMP = 5
	HOTEND_OVERSHOOT = 15

	MAX_E_TEMP = (HEATER_0_MAXTEMP - (HOTEND_OVERSHOOT))
	MIN_E_TEMP = HEATER_0_MINTEMP

	BED_OVERSHOOT = 10
	BED_MAXTEMP = 150
	BED_MINTEMP = 5

	BED_MAX_TARGET = (BED_MAXTEMP - (BED_OVERSHOOT))
	MIN_BED_TEMP = BED_MINTEMP

	X_MIN_POS = 0.0
	Y_MIN_POS = 0.0
	Z_MIN_POS = 0.0
	Z_MAX_POS = 200

	Z_PROBE_OFFSET_RANGE_MIN = -20
	Z_PROBE_OFFSET_RANGE_MAX = 20

	buzzer = buzz_t()

	BABY_Z_VAR = 0
	feedrate_percentage = 100
	temphot = 0
	tempbed = 0

	HMI_ValueStruct = HMI_value_t()
	HMI_flag = HMI_Flag_t()

	current_position = xyze_t()

	thermalManager = {
		'temp_bed': {'celsius': 20, 'target': 120},
		'temp_hotend': [{'celsius': 20, 'target': 120}],
		'fan_speed': [100]
	}

	material_preset = [
		material_preset_t('PLA', 200, 60),
		material_preset_t('ABS', 210, 100)
	]
	files = None
	MACHINE_SIZE = "220x220x250"
	SHORT_BUILD_VERSION = "1.00"
	CORP_WEBSITE_E = "https://www.klipper3d.org/"

	def __init__(self, API_Key, URL='127.0.0.1'):
		"""Initialize printer interface with error handling"""
		try:
			print(f'Initializing printer interface for {URL}')
			
			# Validate inputs
			if not API_Key or not isinstance(API_Key, str):
				raise ValueError('API_Key must be a non-empty string')
			
			self.op = MoonrakerSocket(URL, 80, API_Key)
			self.status = None
			print(f'Moonraker base address: {self.op.base_address}')
			
			# Initialize Klippy socket with error handling
			socket_path = '/home/pi/printer_data/comms/klippy.sock'
			try:
				self.ks = KlippySocket(socket_path, callback=self.klippy_callback)
			except Exception as e:
				print(f'Warning: Could not connect to Klippy socket at {socket_path}: {e}')
				self.ks = None
			
			# Set up Klippy subscriptions if socket is available
			if self.ks:
				subscribe = {
					"id": 4001,
					"method": "objects/subscribe",
					"params": {
						"objects": {
							"toolhead": ["position"]
						},
						"response_template": {}
					}
				}
				self.klippy_z_offset = '{"id": 4002, "method": "objects/query", "params": {"objects": {"configfile": ["config"]}}}'
				self.klippy_home = '{"id": 4003, "method": "objects/query", "params": {"objects": {"toolhead": ["homed_axes"]}}}'

				self.ks.queue_line(json.dumps(subscribe))
				self.ks.queue_line(self.klippy_z_offset)
				self.ks.queue_line(self.klippy_home)

			# Set up async event loop
			self.event_loop = asyncio.new_event_loop()
			threading.Thread(target=self.event_loop.run_forever, daemon=True).start()
			
			print('Printer interface initialization complete')
			
		except Exception as e:
			print(f'Error during printer interface initialization: {e}')
			raise

	# ------------- Klipper Function ----------

	def klippy_callback(self, line):
		try:
			klippyData = json.loads(line)
		except (JSONDecodeError, ValueError) as e:
			print(f'Error parsing Klippy data: {e}')
			return
			
		status = None
		if 'result' in klippyData and 'status' in klippyData['result']:
			status = klippyData['result']['status']
		elif 'params' in klippyData and 'status' in klippyData['params']:
			status = klippyData['params']['status']

		if not status:
			return

		# Handle toolhead updates
		if 'toolhead' in status:
			toolhead = status['toolhead']
			if 'position' in toolhead and len(toolhead['position']) >= 4:
				self.current_position.x = toolhead['position'][0]
				self.current_position.y = toolhead['position'][1]
				self.current_position.z = toolhead['position'][2]
				self.current_position.e = toolhead['position'][3]
				
			if 'homed_axes' in toolhead:
				homed_axes = toolhead['homed_axes']
				self.current_position.home_x = 'x' in homed_axes
				self.current_position.home_y = 'y' in homed_axes
				self.current_position.home_z = 'z' in homed_axes

		# Handle config file updates (BLTouch z_offset)
		if 'configfile' in status and 'config' in status['configfile']:
			config = status['configfile']['config']
			if 'bltouch' in config and 'z_offset' in config['bltouch']:
				z_offset = config['bltouch']['z_offset']
				if z_offset is not None:
					try:
						self.BABY_Z_VAR = float(z_offset)
					except (ValueError, TypeError):
						print(f'Invalid z_offset value: {z_offset}')

			# print(status)

	def ishomed(self):
		if self.current_position.home_x and self.current_position.home_y and self.current_position.home_z:
			return True
		else:
			self.ks.queue_line(self.klippy_home)
			return False

	def offset_z(self, new_offset):
#		print('new z offset:', new_offset)
		self.BABY_Z_VAR = new_offset
		self.sendGCode('ACCEPT')

	def add_mm(self, axs, new_offset):
		gc = 'TESTZ Z={}'.format(new_offset)
		print(axs, gc)
		self.sendGCode(gc)

	def probe_calibrate(self):
		self.sendGCode('G28')
		self.sendGCode('PROBE_CALIBRATE')
		self.sendGCode('G1 Z0')

	# ------------- OctoPrint Function ----------

	def getREST(self, path):
		try:
			r = self.op.s.get(self.op.base_address + path)
			d = r.content.decode('utf-8')
			try:
				result = json.loads(d)
				# Check if this is an error response
				if isinstance(result, dict) and 'error' in result:
					print(f'API Error for {path}: {result["error"]}')
					return None
				return result
			except JSONDecodeError:
				print('Decoding JSON has failed')
			return None
		except Exception as e:
			print(f'Request failed for {path}: {e}')
			return None

	async def _postREST(self, path, json):
		"""Async REST POST with error handling"""
		try:
			response = self.op.s.post(self.op.base_address + path, json=json, timeout=10)
			response.raise_for_status()
			return True
		except requests.exceptions.RequestException as e:
			print(f'POST request failed for {path}: {e}')
			return False
		except Exception as e:
			print(f'Unexpected error in POST request for {path}: {e}')
			return False

	def postREST(self, path, json):
		"""Queue an async REST POST request"""
		try:
			future = asyncio.run_coroutine_threadsafe(self._postREST(path, json), self.event_loop)
			return future
		except Exception as e:
			print(f'Error queuing POST request for {path}: {e}')
			return None

	def init_Webservices(self, max_retries=5, retry_delay=2):
		"""Initialize web services with retry logic for transient failures"""
		for attempt in range(max_retries):
			try:
				print(f'Attempting to connect to web services (attempt {attempt + 1}/{max_retries})')
				
				# Test basic connectivity
				try:
					response = requests.get(self.op.base_address, timeout=10)
					response.raise_for_status()
				except (ConnectionError, requests.exceptions.RequestException) as e:
					print(f'Connection attempt {attempt + 1} failed: {e}')
					if attempt < max_retries - 1:
						print(f'Retrying in {retry_delay} seconds...')
						time.sleep(retry_delay)
						continue
					else:
						print('Web site does not exist after all retries')
						return False
				
				print('Web site exists')
				
				# Test printer API
				printer_check = self.getREST('/api/printer')
				if printer_check is None:
					print(f'Printer API check failed on attempt {attempt + 1}')
					if attempt < max_retries - 1:
						print(f'Retrying in {retry_delay} seconds...')
						time.sleep(retry_delay)
						continue
					else:
						print('Printer API unavailable after all retries')
						return False
				
				# Update variables
				if not self.update_variable():
					print(f'Variable update failed on attempt {attempt + 1}')
					if attempt < max_retries - 1:
						print(f'Retrying in {retry_delay} seconds...')
						time.sleep(retry_delay)
						continue
				
				# Get version info with error handling
				version_data = self.getREST('/machine/update/status?refresh=false')
				if version_data and 'result' in version_data and 'version_info' in version_data['result']:
					try:
						self.SHORT_BUILD_VERSION = version_data['result']['version_info']['klipper']['version']
						print(f'Klipper version: {self.SHORT_BUILD_VERSION}')
					except KeyError:
						print('Warning: Could not get Klipper version')
						self.SHORT_BUILD_VERSION = "Unknown"
				else:
					print('Warning: Could not get machine update status')
					self.SHORT_BUILD_VERSION = "Unknown"

				# Get toolhead data with error handling
				toolhead_data = self.getREST('/printer/objects/query?toolhead')
				if toolhead_data and 'result' in toolhead_data and 'status' in toolhead_data['result']:
					data = toolhead_data['result']['status']
					if 'toolhead' in data and 'axis_maximum' in data['toolhead']:
						toolhead = data['toolhead']
						volume = toolhead['axis_maximum'] #[x,y,z,w]
						self.MACHINE_SIZE = "{}x{}x{}".format(
							int(volume[0]),
							int(volume[1]),
							int(volume[2])
						)
						self.X_MAX_POS = int(volume[0])
						self.Y_MAX_POS = int(volume[1])
						print(f'Machine size: {self.MACHINE_SIZE}')
					else:
						print('Warning: toolhead or axis_maximum not found in response')
				else:
					print('Warning: Could not get toolhead data:', toolhead_data)
				
				print('Web services initialized successfully')
				return True
				
			except Exception as e:
				print(f'Unexpected error during web service initialization (attempt {attempt + 1}): {e}')
				if attempt < max_retries - 1:
					print(f'Retrying in {retry_delay} seconds...')
					time.sleep(retry_delay)
					continue
		
		print('Failed to initialize web services after all retries')
		return False

	def check_webservice_health(self):
		"""Check if web services are responsive and retry if needed"""
		try:
			# Quick health check
			test_data = self.getREST('/api/printer')
			if test_data is None:
				print('Web service health check failed, attempting to reinitialize...')
				return self.init_Webservices(max_retries=3, retry_delay=1)
			return True
		except Exception as e:
			print(f'Web service health check error: {e}')
			return False

	def GetFiles(self, refresh=False):
		if not self.files or refresh:
			files_data = self.getREST('/server/files/list')
			if files_data and 'result' in files_data:
				self.files = files_data["result"]
			else:
				print('Warning: Could not get files list:', files_data)
				self.files = []
		names = []
		for fl in self.files:
			names.append(fl["path"])
		return names

	def update_variable(self, retry_on_failure=False):
		"""Update printer variables from API with optional retry logic"""
		query = '/printer/objects/query?extruder&heater_bed&gcode_move&fan'
		data = self.getREST(query)
		if not data or 'result' not in data or 'status' not in data['result']:
			print('Warning: Missing result or status in response:', data)
			if retry_on_failure:
				print('Attempting to check web service health...')
				if self.check_webservice_health():
					# Retry once after health check
					data = self.getREST(query)
					if not data or 'result' not in data or 'status' not in data['result']:
						print('Still unable to get printer data after retry')
						return False
				else:
					return False
			else:
				return False
		data = data['result']['status']
		gcm = data['gcode_move']
		z_offset = gcm['homing_origin'][2] #z offset
		flow_rate = gcm['extrude_factor'] * 100 #flow rate percent
		self.absolute_moves = gcm['absolute_coordinates'] #absolute or relative
		self.absolute_extrude = gcm['absolute_extrude'] #absolute or relative
		speed = gcm['speed'] #current speed in mm/s
		print_speed = gcm['speed_factor'] * 100 #print speed percent
		bed = data['heater_bed'] #temperature, target
		extruder = data['extruder'] #temperature, target
		fan = data['fan']
		Update = False
		try:
			if self.thermalManager['temp_bed']['celsius'] != int(bed['temperature']):
				self.thermalManager['temp_bed']['celsius'] = int(bed['temperature'])
				Update = True
			if self.thermalManager['temp_bed']['target'] != int(bed['target']):
				self.thermalManager['temp_bed']['target'] = int(bed['target'])
				Update = True
			if self.thermalManager['temp_hotend'][0]['celsius'] != int(extruder['temperature']):
				self.thermalManager['temp_hotend'][0]['celsius'] = int(extruder['temperature'])
				Update = True
			if self.thermalManager['temp_hotend'][0]['target'] != int(extruder['target']):
				self.thermalManager['temp_hotend'][0]['target'] = int(extruder['target'])
				Update = True
			if self.thermalManager['fan_speed'][0] != int(fan['speed'] * 100):
				self.thermalManager['fan_speed'][0] = int(fan['speed'] * 100)
				Update = True
			if self.BABY_Z_VAR != z_offset:
				self.BABY_Z_VAR = z_offset
				self.HMI_ValueStruct.offset_value = z_offset * 100
				Update = True
		except Exception as e:
			print('Exception in update_variable:', e)
			pass #missing key, shouldn't happen, fixes misses on conditionals ¯\_(ツ)_/¯
		self.job_Info = self.getREST('/printer/objects/query?virtual_sdcard&print_stats')
		if self.job_Info and 'result' in self.job_Info and 'status' in self.job_Info['result']:
			self.job_Info = self.job_Info['result']['status']
			self.file_name = self.job_Info['print_stats']['filename']
			self.status = self.job_Info['print_stats']['state']
			self.HMI_flag.print_finish = self.getPercent() == 100.0
		else:
			print('Warning: Missing result/status in job_Info:', self.job_Info)
		return Update

	def printingIsPaused(self):
		"""Check if printing is currently paused"""
		try:
			if not hasattr(self, 'job_Info') or not self.job_Info:
				return False
			
			state = self.job_Info.get('print_stats', {}).get('state', '')
			return state in ["paused", "pausing"]
		except (KeyError, AttributeError) as e:
			print(f'Error checking pause state: {e}')
			return False

	def getPercent(self):
		"""Get print progress percentage"""
		try:
			if not hasattr(self, 'job_Info') or not self.job_Info:
				return 0.0
			
			virtual_sdcard = self.job_Info.get('virtual_sdcard', {})
			if virtual_sdcard.get('is_active', False):
				progress = virtual_sdcard.get('progress', 0)
				return float(progress * 100)
			return 0.0
		except (KeyError, ValueError, TypeError) as e:
			print(f'Error getting print percentage: {e}')
			return 0.0

	def duration(self):
		"""Get print duration in seconds"""
		try:
			if not hasattr(self, 'job_Info') or not self.job_Info:
				return 0
			
			virtual_sdcard = self.job_Info.get('virtual_sdcard', {})
			if virtual_sdcard.get('is_active', False):
				duration = self.job_Info.get('print_stats', {}).get('print_duration', 0)
				return float(duration)
			return 0
		except (KeyError, ValueError, TypeError) as e:
			print(f'Error getting print duration: {e}')
			return 0

	def remain(self):
		"""Calculate estimated remaining print time"""
		try:
			percent = self.getPercent()
			duration = self.duration()
			
			if percent > 0 and duration > 0:
				total_estimated = duration / (percent / 100)
				remaining = total_estimated - duration
				return max(0, remaining)  # Don't return negative time
			return 0
		except (ZeroDivisionError, ValueError) as e:
			print(f'Error calculating remaining time: {e}')
			return 0

	def openAndPrintFile(self, filenum):
		"""Start printing a file by index"""
		if not self.files or filenum >= len(self.files):
			print(f'Error: Invalid file number {filenum} or no files loaded')
			return False
		
		try:
			self.file_name = self.files[filenum]['path']
			print(f'Starting print: {self.file_name}')
			self.postREST('/printer/print/start', json={'filename': self.file_name})
			return True
		except (KeyError, IndexError) as e:
			print(f'Error opening file {filenum}: {e}')
			return False

	def cancel_job(self):
		"""Cancel the current print job"""
		try:
			print('Canceling job...')
			self.postREST('/printer/print/cancel', json=None)
			return True
		except Exception as e:
			print(f'Error canceling job: {e}')
			return False

	def pause_job(self):
		"""Pause the current print job"""
		try:
			print('Pausing job...')
			self.postREST('/printer/print/pause', json=None)
			return True
		except Exception as e:
			print(f'Error pausing job: {e}')
			return False

	def resume_job(self):
		"""Resume the current print job"""
		try:
			print('Resuming job...')
			self.postREST('/printer/print/resume', json=None)
			return True
		except Exception as e:
			print(f'Error resuming job: {e}')
			return False

	def set_feedrate(self, fr):
		"""Set feedrate percentage with validation"""
		try:
			fr = float(fr)
			if fr < 10 or fr > 500:  # Reasonable limits
				print(f'Warning: Feedrate {fr}% outside reasonable range (10-500%)')
				fr = max(10, min(fr, 500))
			
			self.feedrate_percentage = fr
			print(f'Setting feedrate to {fr}%')
			self.sendGCode(f'M220 S{fr}')
			return True
		except (ValueError, TypeError) as e:
			print(f'Error setting feedrate: {e}')
			return False

	def home(self, homeZ=False):
		"""Home axes with optional Z homing"""
		try:
			script = 'G28 X Y'
			if homeZ:
				script += ' Z'
			
			print(f'Homing axes: {script[4:]}')  # Remove 'G28 ' for display
			self.sendGCode(script)
			return True
		except Exception as e:
			print(f'Error during homing: {e}')
			return False

	def moveRelative(self, axis, distance, speed):
		"""Move axis relatively with proper coordinate mode handling"""
		try:
			# Validate inputs
			distance = float(distance)
			speed = float(speed)
			
			if axis.upper() not in ['X', 'Y', 'Z', 'E']:
				print(f'Error: Invalid axis {axis}')
				return False
			
			# Set relative mode, move, then restore original mode
			restore_mode = 'G90' if self.absolute_moves else 'G91'
			gcode = f'G91\nG1 {axis.upper()}{distance} F{speed}\n{restore_mode}'
			
			print(f'Moving {axis.upper()} by {distance}mm at {speed}mm/min')
			self.sendGCode(gcode)
			return True
		except (ValueError, TypeError) as e:
			print(f'Error in relative move: {e}')
			return False

	def moveAbsolute(self, axis, position, speed):
		"""Move axis to absolute position with proper coordinate mode handling"""
		try:
			# Validate inputs
			position = float(position)
			speed = float(speed)
			
			if axis.upper() not in ['X', 'Y', 'Z', 'E']:
				print(f'Error: Invalid axis {axis}')
				return False
			
			# Set absolute mode, move, then restore original mode
			restore_mode = 'G91' if not self.absolute_moves else 'G90'
			gcode = f'G90\nG1 {axis.upper()}{position} F{speed}\n{restore_mode}'
			
			print(f'Moving {axis.upper()} to {position}mm at {speed}mm/min')
			self.sendGCode(gcode)
			return True
		except (ValueError, TypeError) as e:
			print(f'Error in absolute move: {e}')
			return False

	def sendGCode(self, gcode):
		self.postREST('/printer/gcode/script', json={'script': gcode})

	def disable_all_heaters(self):
		self.setExtTemp(0)
		self.setBedTemp(0)

	def zero_fan_speeds(self):
		"""Turn off all fans"""
		try:
			print('Turning off all fans')
			self.sendGCode('M106 S0')  # Turn off part cooling fan
			return True
		except Exception as e:
			print(f'Error turning off fans: {e}')
			return False

	def preheat(self, profile):
		"""Preheat using a material profile"""
		profile_upper = profile.upper()
		
		# Find matching preset
		preset = None
		for p in self.material_preset:
			if p.name.upper() == profile_upper:
				preset = p
				break
		
		if preset:
			print(f'Preheating for {preset.name}: Bed={preset.bed_temp}°C, Hotend={preset.hotend_temp}°C')
			self.preHeat(preset.bed_temp, preset.hotend_temp)
			return True
		else:
			print(f'Unknown material profile: {profile}')
			available = [p.name for p in self.material_preset]
			print(f'Available profiles: {", ".join(available)}')
			return False

	def save_settings(self):
		print('saving settings')
		return True

	def setExtTemp(self, target, toolnum=0):
		"""Set extruder target temperature with validation"""
		try:
			target = float(target)
			if target < 0 or target > self.MAX_E_TEMP:
				print(f'Warning: Extruder temperature {target}°C outside safe range (0-{self.MAX_E_TEMP}°C)')
				target = max(0, min(target, self.MAX_E_TEMP))
			
			print(f'Setting extruder {toolnum} temperature to {target}°C')
			self.sendGCode(f'M104 T{toolnum} S{target}')
			return True
		except (ValueError, TypeError) as e:
			print(f'Error setting extruder temperature: {e}')
			return False

	def setBedTemp(self, target):
		"""Set bed target temperature with validation"""
		try:
			target = float(target)
			if target < 0 or target > self.BED_MAX_TARGET:
				print(f'Warning: Bed temperature {target}°C outside safe range (0-{self.BED_MAX_TARGET}°C)')
				target = max(0, min(target, self.BED_MAX_TARGET))
			
			print(f'Setting bed temperature to {target}°C')
			self.sendGCode(f'M140 S{target}')
			return True
		except (ValueError, TypeError) as e:
			print(f'Error setting bed temperature: {e}')
			return False

	def preHeat(self, bedtemp, exttemp, toolnum=0):
# these work but invoke a wait which hangs the screen until they finish.
#		self.sendGCode('M140 S%s\nM190 S%s' % (bedtemp, bedtemp))
#		self.sendGCode('M104 T%s S%s\nM109 T%s S%s' % (toolnum, exttemp, toolnum, exttemp))
		self.setBedTemp(bedtemp)
		self.setExtTemp(exttemp)

	def setZOffset(self, offset):
		"""Set Z offset with validation"""
		try:
			offset = float(offset)
			if offset < self.Z_PROBE_OFFSET_RANGE_MIN or offset > self.Z_PROBE_OFFSET_RANGE_MAX:
				print(f'Warning: Z offset {offset}mm outside safe range ({self.Z_PROBE_OFFSET_RANGE_MIN} to {self.Z_PROBE_OFFSET_RANGE_MAX}mm)')
				offset = max(self.Z_PROBE_OFFSET_RANGE_MIN, min(offset, self.Z_PROBE_OFFSET_RANGE_MAX))
			
			print(f'Setting Z offset to {offset}mm')
			self.sendGCode(f'SET_GCODE_OFFSET Z={offset} MOVE=1')
			return True
		except (ValueError, TypeError) as e:
			print(f'Error setting Z offset: {e}')
			return False

	def safe_api_call(self, endpoint, description="API call", required=True):
		"""Safely make an API call with logging and error handling"""
		try:
			result = self.getREST(endpoint)
			if result is None:
				print(f'Warning: {description} returned no data from {endpoint}')
				return None if not required else False
			return result
		except Exception as e:
			print(f'Error during {description} from {endpoint}: {e}')
			return None if not required else False

	def wait_for_printer_ready(self, timeout=60, check_interval=2):
		"""Wait for printer services to be ready during startup"""
		start_time = time.time()
		print('Waiting for printer services to be ready...')
		
		while time.time() - start_time < timeout:
			try:
				# Check if basic printer API is responding
				printer_status = self.safe_api_call('/api/printer', 'printer status check', required=False)
				if printer_status is not None:
					print('Printer services are ready!')
					return True
				
				print(f'Printer not ready yet, waiting {check_interval} seconds...')
				time.sleep(check_interval)
				
			except Exception as e:
				print(f'Error while waiting for printer: {e}')
				time.sleep(check_interval)
		
		print(f'Timeout waiting for printer services after {timeout} seconds')
		return False

	def is_printer_ready(self):
		"""Check if printer is ready for operations"""
		try:
			if not hasattr(self, 'status') or not self.status:
				print('Printer status unknown')
				return False
			
			# Check if printer is in a safe state for operations
			safe_states = ['idle', 'ready', 'printing', 'paused']
			if self.status not in safe_states:
				print(f'Printer not ready: current state is {self.status}')
				return False
			
			return True
		except Exception as e:
			print(f'Error checking printer readiness: {e}')
			return False

	def get_printer_status_summary(self):
		"""Get a summary of current printer status"""
		try:
			summary = {
				'status': getattr(self, 'status', 'Unknown'),
				'hotend_temp': self.thermalManager['temp_hotend'][0]['celsius'],
				'hotend_target': self.thermalManager['temp_hotend'][0]['target'],
				'bed_temp': self.thermalManager['temp_bed']['celsius'],
				'bed_target': self.thermalManager['temp_bed']['target'],
				'fan_speed': self.thermalManager['fan_speed'][0],
				'print_progress': self.getPercent(),
				'homed': {
					'x': self.current_position.home_x,
					'y': self.current_position.home_y,
					'z': self.current_position.home_z
				},
				'position': {
					'x': self.current_position.x,
					'y': self.current_position.y,
					'z': self.current_position.z,
					'e': self.current_position.e
				}
			}
			return summary
		except Exception as e:
			print(f'Error getting printer status summary: {e}')
			return None
