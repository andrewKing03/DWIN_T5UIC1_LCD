# Class to monitor a rotary encoder and update a value.  You can either read the value when you need it, by calling getValue(), or
# you can configure a callback which will be called whenever the value changes.

import RPi.GPIO as GPIO
import time
import threading

class Encoder:

    def __init__(self, leftPin, rightPin, callback=None, debounce_time=0.001):
        """
        Initialize rotary encoder with error handling and validation
        
        Args:
            leftPin: GPIO pin number for left/A channel
            rightPin: GPIO pin number for right/B channel  
            callback: Optional callback function called when value changes
            debounce_time: Minimum time between transitions (seconds)
        """
        try:
            # Validate input parameters
            if not isinstance(leftPin, int) or not isinstance(rightPin, int):
                raise ValueError("Pin numbers must be integers")
            
            if leftPin == rightPin:
                raise ValueError("Left and right pins must be different")
                
            if leftPin < 0 or rightPin < 0:
                raise ValueError("Pin numbers must be non-negative")
                
            if debounce_time < 0:
                raise ValueError("Debounce time must be non-negative")
            
            self.leftPin = leftPin
            self.rightPin = rightPin
            self.value = 0
            self.state = 0b00  # Use integer instead of string for better performance
            self.direction = None
            self.callback = callback
            self.debounce_time = debounce_time
            self.last_transition_time = 0
            self.lock = threading.Lock()  # Thread safety
            self._initialized = False
            
            print(f"Initializing encoder on pins {leftPin} (left/A) and {rightPin} (right/B)")
            
            # Setup GPIO pins with error handling
            try:
                GPIO.setup(self.leftPin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                GPIO.setup(self.rightPin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
                print(f"GPIO pins {leftPin} and {rightPin} configured successfully")
            except Exception as e:
                raise RuntimeError(f"Failed to setup GPIO pins: {e}")
            
            # Add event detection with error handling
            try:
                GPIO.add_event_detect(self.leftPin, GPIO.BOTH, callback=self.transitionOccurred, bouncetime=1)  
                GPIO.add_event_detect(self.rightPin, GPIO.BOTH, callback=self.transitionOccurred, bouncetime=1)
                print("GPIO event detection configured")
            except Exception as e:
                raise RuntimeError(f"Failed to setup GPIO event detection: {e}")
            
            # Read initial state
            try:
                self._update_state()
                self._initialized = True
                print(f"Encoder initialized successfully with initial state: {self.state:02b}")
            except Exception as e:
                self.cleanup()  # Clean up on initialization failure
                raise RuntimeError(f"Failed to read initial GPIO state: {e}")
                
        except Exception as e:
            print(f"Error initializing encoder: {e}")
            raise  

    def transitionOccurred(self, channel):
        """Handle encoder state transitions with debouncing and error handling"""
        if not self._initialized:
            return
            
        try:
            # Debouncing - ignore transitions that occur too quickly
            current_time = time.time()
            if current_time - self.last_transition_time < self.debounce_time:
                return
            self.last_transition_time = current_time
            
            # Thread safety
            with self.lock:
                # Read current GPIO state
                if not self._update_state():
                    return  # Skip if we can't read GPIO state
                
                old_state = getattr(self, '_previous_state', self.state)
                new_state = self.state
                
                # Only process if state actually changed
                if old_state == new_state:
                    return
                
                # Process state transition using lookup table for better performance
                direction_change = self._process_transition(old_state, new_state)
                
                if direction_change != 0:
                    self.value += direction_change
                    self._safe_callback(self.value)
                
                self._previous_state = new_state
                
        except Exception as e:
            print(f"Error in encoder transition handling: {e}")

    def _process_transition(self, old_state, new_state):
        """
        Process encoder state transition and return direction change
        Returns: -1 for counter-clockwise, +1 for clockwise, 0 for no change
        
        State encoding: 00=0, 01=1, 10=2, 11=3
        """
        try:
            # State transition lookup table for quadrature encoding
            # Based on Gray code sequence: 00 -> 01 -> 11 -> 10 -> 00 (clockwise)
            #                          or: 00 -> 10 -> 11 -> 01 -> 00 (counter-clockwise)
            transition_table = {
                # (old_state, new_state): direction_change
                (0b00, 0b01): 1,   # 00 -> 01: clockwise
                (0b01, 0b11): 1,   # 01 -> 11: clockwise  
                (0b11, 0b10): 1,   # 11 -> 10: clockwise
                (0b10, 0b00): 1,   # 10 -> 00: clockwise
                
                (0b00, 0b10): -1,  # 00 -> 10: counter-clockwise
                (0b10, 0b11): -1,  # 10 -> 11: counter-clockwise
                (0b11, 0b01): -1,  # 11 -> 01: counter-clockwise
                (0b01, 0b00): -1,  # 01 -> 00: counter-clockwise
            }
            
            return transition_table.get((old_state, new_state), 0)
            
        except Exception as e:
            print(f"Error processing encoder transition: {e}")
            return 0

    def _safe_callback(self, value):
        """Safely execute callback with error handling"""
        if self.callback is not None:
            try:
                self.callback(value)
            except Exception as e:
                print(f"Error in encoder callback: {e}")
                # Don't disable callback on error, just log it

    def getValue(self):
        return self.value

    def _update_state(self):
        """Safely read and update the current GPIO state"""
        try:
            p1 = GPIO.input(self.leftPin)
            p2 = GPIO.input(self.rightPin)
            self.state = (p1 << 1) | p2  # Convert to 2-bit integer: 00, 01, 10, 11
            return True
        except Exception as e:
            print(f"Error reading GPIO state: {e}")
            return False

    def cleanup(self):
        """Clean up GPIO resources"""
        try:
            with self.lock:
                self._initialized = False
                GPIO.remove_event_detect(self.leftPin)
                GPIO.remove_event_detect(self.rightPin)
                print(f"Encoder cleanup completed for pins {self.leftPin} and {self.rightPin}")
        except Exception as e:
            print(f"Error during encoder cleanup: {e}")

    def __del__(self):
        """Destructor to ensure cleanup on object deletion"""
        try:
            self.cleanup()
        except:
            pass  # Ignore errors in destructor
