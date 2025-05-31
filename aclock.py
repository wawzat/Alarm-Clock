# Alarm clock with LED Display
# James S. Lucas
# Issues and todo: alarm pre-selects, auto alarm repeat, issues with dimLevel 0 line 402 auto time setting conflict with manual off
#   , display override move to display functions? LED blinking when after 8PM
# 20171118
# 20250530
# All camelCase variable and method names have been converted to snake_case throughout the file, except for library-required names.
import os
import time
import datetime
from datetime import datetime as dt
from adafruit_ht16k33.segments import Seg7x4
from adafruit_ht16k33.segments import Seg14x4
from gpiozero import Button, DigitalInputDevice, DigitalOutputDevice
from rotary_class_jsl import RotaryEncoder
import logging
import board
import busio
import json

class AlarmClock:
    SETTINGS_FILE = "settings.json"
    PERSISTED_SETTINGS = [
        "alarm_hour", "alarm_minute", "period", "alarm_stat", "alarm_track", "vol_level",
        "manual_dim_level", "auto_dim_level", "auto_dim", "display_mode", "display_override"
    ]

    def __init__(self):
        # Set up logger for error logging
        self.logger = logging.getLogger("aclock")
        self.logger.setLevel(logging.ERROR)
        if not self.logger.handlers:
            handler = logging.FileHandler("aclock_error.log")
            formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

        # Define rotary encoder and separate pushbutton GPIO input pins
        self.rotary_a = DigitalInputDevice(19, pull_up=True)
        self.rotary_b = DigitalInputDevice(26, pull_up=True)
        self.rotary_button = Button(12, pull_up=True, bounce_time=0.08)
        self.alarm_settings_button = Button(13, pull_up=True, bounce_time=0.08)
        self.display_settings_button = Button(21, pull_up=True, bounce_time=0.08)

        # Define EDS GPIO input and output pins and setup gpiozero devices
        self.trig_pin = 5
        self.echo_pin = 22
        self.trig = DigitalOutputDevice(self.trig_pin)
        self.echo = DigitalInputDevice(self.echo_pin)

        # Pulse EDS and wait for sensor to settle
        self.trig.off()
        print("Waiting For Sensor To Settle")
        time.sleep(2)

        # Define increment for alarm minute adjustment
        self.minute_incr = 1

        # Create display instances (default I2C address (0x70))
        self.i2c = busio.I2C(board.SCL, board.SDA)
        self.alpha_display = Seg14x4(self.i2c)
        self.num_display = Seg7x4(self.i2c, address=0x72)

        # Initialize the display. Must be called once before using the display.
        self.alpha_display.fill(0)
        self.num_display.fill(0)
        self.num_display.brightness = 6 / 15.0

        # Audio feature flag
        self.use_audio = False  # Set to True to enable audio features
        if self.use_audio:
            import alsaaudio
            self.mixer = alsaaudio.Mixer('PCM')

        # State variables
        self.alarm_settings_state = 1
        self.display_settings_state = 1
        self.display_mode = "MANUAL_DIM"
        self.display_override = "ON"
        self.alarm_hour = 4
        self.alarm_minute = 0
        self.alarm_time = dt.strptime("04:00", "%H:%M")
        self.alarm_set = 1
        self.display_set = 1
        self.alarm_stat = "OFF"
        self.alarm_ringing = 0
        self.sleep_state = "OFF"
        self.period = "AM"
        self.dim_level = 6
        self.auto_dim_level = 0
        self.manual_dim_level = 6
        self.alarm_track = 1
        self.vol_level = 65
        self.alarm_tracks = {1: '01.mp3', 2: '02.mp3', 3: '03.mp3', 4: '04.mp3', 5: '05.mp3', 6: '06.mp3'}
        self.distance = 0
        self.auto_dim = "ON"
        self.loop_count = 0
        self.debug = "NO"

        # Display cache
        self.last_num_message = None
        self.last_num_brightness = None
        self.last_alpha_message = None
        self.last_alpha_brightness = None
        self.last_alpha_type = None

        # Load settings at startup
        self.load_settings()

        # Define the rotary and stand-alone switches
        self.rswitch = RotaryEncoder(
            self.rotary_a, self.rotary_b, self.rotary_button,
            self.alarm_settings_button, self.display_settings_button,
            self.rotary_encoder_event, self.alarm_settings_callback, self.display_settings_callback, 2
        )

    def get_time(self):
        return dt.now()

    def check_alarm(self, now):
        loop_count = 0
        vol_increase = 0
        time_decrease = 0
        print(f"time: {now.time()} {self.period}  alarm time: {self.alarm_time.time()}")
        if now.strftime("%p") == self.period and now.time() >= self.alarm_time.time() and self.alarm_stat == "ON":
            self.alarm_ringing = 1
            self.sleep_state = "OFF"
            snooze_triggered = False
            snooze_cooldown = 10  # seconds to wait before alarm can re-trigger after snooze
            snooze_time = None
            # --- Flicker reduction: cache last num display value and colon ---
            last_num_message = None
            last_colon = None
            while self.alarm_ringing == 1 and self.alarm_stat == "ON":
                loop_count += 1
                delay_loop = 0
                self.alpha_display.fill(0)
                self.alpha_display.print("RING")
                self.alpha_display.show()
                now = self.get_time()
                num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
                colon_state = now.second % 2
                # Only update numeric display if value or colon changed
                if (num_message != last_num_message) or (colon_state != last_colon):
                    self.num_display.fill(0)
                    self.num_display.print(num_message)
                    self.num_display.colon = colon_state
                    try:
                        self.num_display.show()
                    except Exception as e:
                        self.logger.error("num_display.show() error: %s", str(e))
                    last_num_message = num_message
                    last_colon = colon_state
                if self.use_audio:
                    if loop_count % 10 == 0 and (self.vol_level + vol_increase) <= 90:
                        vol_increase += 5
                    if loop_count % 10 == 0 and time_decrease <= 2.25:
                        time_decrease += .25
                    self.mixer.setvolume(self.vol_level+vol_increase)
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")
                print(f"alarm ring, now: {now.time()} alarm: {self.alarm_time.time()} Count: {loop_count} Vol: {self.vol_level+vol_increase} Ring Time: {3-time_decrease} alarm_ringing: {self.alarm_ringing} sleep_state: {self.sleep_state}")
                # Check EDS for snooze every 0.1s for up to 2 seconds (or less as time_decrease increases)
                snooze_window = max(0.5, 2-time_decrease)  # never less than 0.5s
                start_time = time.time()
                while time.time() - start_time < snooze_window:
                    self.distance = self.eds()
                    print(f"EDS distance: {self.distance}")
                    if 0 < self.distance < 4:
                        print("Snooze triggered by hand wave!")
                        self.alarm_ringing = 0
                        self.alarm_time = self.alarm_time + datetime.timedelta(minutes=5)  # 5 min snooze
                        self.sleep_state = "ON"
                        snooze_triggered = True
                        snooze_time = time.time()
                        break
                    time.sleep(0.1)
                if snooze_triggered:
                    # Wait for cooldown before allowing alarm to re-trigger
                    print(f"Snooze cooldown for {snooze_cooldown} seconds.")
                    while time.time() - snooze_time < snooze_cooldown:
                        time.sleep(0.2)
                    break
        elif now >= self.alarm_time and self.alarm_stat == "OFF":
            print("alarm mode off")
        return

    def eds(self):
        self.trig.off()
        time.sleep(0.000002)
        self.trig.on()
        time.sleep(0.000015)
        self.trig.off()
        timeout = time.time() + 0.05
        while not self.echo.value:
            if time.time() > timeout:
                return -1
        pulse_start = time.time()
        timeout = time.time() + 0.05
        while self.echo.value:
            if time.time() > timeout:
                return -1
        pulse_end = time.time()
        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 6752
        distance = round(distance, 2)
        return distance

    def clear_alpha_display(self):
        self.alpha_display.fill(0)
        try:
            self.alpha_display.show()
        except Exception as e:
            self.logger.error("alpha_display.show() error: %s", str(e))

    def alarm_settings_callback(self, channel):
        debug_lines = []
        debug_lines.append(f"alarm_settings_callback called with channel={channel} alarm_state={self.alarm_settings_state}, display_state={self.display_settings_state}, alarm_set={self.alarm_set}")
        # Only act on BUTTONUP (button release)
        if channel != RotaryEncoder.BUTTONUP:
            debug_lines.append("alarm_settings_callback: Ignored, not BUTTONUP")
            print("\n".join(debug_lines), end="\n")
            return
        if self.alarm_ringing == 1:
            debug_lines.append("alarm_settings_callback: Stopping alarm ring")
            self.alarm_ringing = 0
            self.alarm_stat = "OFF"
            self.sleep_state = "OFF"
        elif self.alarm_settings_state == 1:
            debug_lines.append("alarm_settings_callback: Entering alarm settings mode")
            self.alarm_settings_state = 2
            self.alarm_set = 1
        elif self.alarm_settings_state == 2:
            debug_lines.append("alarm_settings_callback: Exiting alarm settings mode")
            self.alarm_settings_state = 1
            self.alpha_display.fill(0)
            try:
                self.alpha_display.show()
            except Exception as e:
                self.logger.error("alpha_display.show() error: %s", str(e))
            time.sleep(.5)
        # Reset display cache to force refresh
        self.last_num_message = None
        self.last_num_brightness = None
        self.last_alpha_message = None
        self.last_alpha_brightness = None
        self.last_alpha_type = None
        debug_lines.append(f"alarm_settings_callback exit: alarm_state={self.alarm_settings_state}, display_state={self.display_settings_state}, alarm_set={self.alarm_set}")
        print("\n".join(debug_lines), end="\n")
        return

    def display_settings_callback(self, channel):
        debug_lines = []
        debug_lines.append(f"display_settings_callback called with channel={channel} display_state={self.display_settings_state}, alarm_set={self.alarm_set}, aux_set={self.display_set}")
        # Only act on BUTTONUP (button release)
        if channel != RotaryEncoder.BUTTONUP:
            return
        if self.display_settings_state == 1:
            debug_lines.append("display_settings_callback: Entering display mode")
            self.alarm_settings_state = 1
            if self.alarm_ringing == 1:
                self.alarm_ringing = 0
                self.alarm_stat = "OFF"
                self.sleep_state = "OFF"
            # Always reset display_settings_state and display_set when entering display settings
            self.display_settings_state = 2
            self.display_set = 1
            self.clear_alpha_display()  # Clear display when entering display mode
            self.save_settings()
            # Reset display cache to force refresh
            self.last_num_message = None
            self.last_num_brightness = None
            self.last_alpha_message = None
            self.last_alpha_brightness = None
            self.last_alpha_type = None
            debug_lines.append(f"display_settings_callback exit: display_state={self.display_settings_state}, alarm_set={self.alarm_set}, aux_set={self.display_set}")
            print("\n".join(debug_lines), end="\n")
            return
        elif self.display_settings_state == 2:
            debug_lines.append("display_settings_callback: Exiting display mode")
            self.display_settings_state = 1
            self.clear_alpha_display()  # Clear display when exiting display mode
            # Reset display cache to force refresh
            self.last_num_message = None
            self.last_num_brightness = None
            self.last_alpha_message = None
            self.last_alpha_brightness = None
            self.last_alpha_type = None
            debug_lines.append(f"display_settings_callback exit: display_state={self.display_settings_state}, alarm_set={self.alarm_set}, aux_set={self.display_set}")
            print("\n".join(debug_lines), end="\n")
            return

    def rotary_encoder_event(self, event):
        if self.alarm_settings_state == 2:
            def inc_alarm_hour():
                self.alarm_hour = (self.alarm_hour % 12) + 1
                print(f"clockwise {self.alarm_hour}")
                return True
            def inc_alarm_minute():
                self.alarm_minute = (self.alarm_minute + self.minute_incr) % 60
                print(f"clockwise {self.alarm_minute}")
                return True
            def toggle_period():
                self.period = "PM" if self.period == "AM" else "AM"
                print(f"clockwise {self.period}")
                return True
            def toggle_alarm_stat():
                self.alarm_stat = "OFF" if self.alarm_stat == "ON" else "ON"
                print(f"clockwise {self.alarm_stat}")
            def inc_alarm_track():
                self.alarm_track = (self.alarm_track % 6) + 1
                if self.use_audio:
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")
            def inc_vol_level():
                self.vol_level = (self.vol_level + 1) % 96
                if self.use_audio:
                    self.mixer.setvolume(self.vol_level)
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")
            def dec_alarm_hour():
                self.alarm_hour = 12 if self.alarm_hour == 1 else self.alarm_hour - 1
                print(f"counter clockwise {self.alarm_hour}")
                return True
            def dec_alarm_minute():
                self.alarm_minute = (self.alarm_minute - self.minute_incr) % 60
                print(f"counter clockwise {self.alarm_minute}")
                return True
            def dec_period():
                self.period = "PM" if self.period == "AM" else "AM"
                print(f"counter clockwise {self.period}")
                return True
            def dec_alarm_stat():
                self.alarm_stat = "OFF" if self.alarm_stat == "ON" else "ON"
                print(f"counter clockwise {self.alarm_stat}")
            def dec_alarm_track():
                self.alarm_track = 6 if self.alarm_track == 1 else self.alarm_track - 1
                if self.use_audio:
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")
            def dec_vol_level():
                self.vol_level = 95 if self.vol_level == 0 else self.vol_level - 1
                if self.use_audio:
                    self.mixer.setvolume(self.vol_level)
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")

            clockwise_actions = {
                1: inc_alarm_hour,
                2: inc_alarm_minute,
                3: toggle_period,
                4: toggle_alarm_stat,
                5: inc_alarm_track,
                6: inc_vol_level
            }
            anticlockwise_actions = {
                1: dec_alarm_hour,
                2: dec_alarm_minute,
                3: dec_period,
                4: dec_alarm_stat,
                5: dec_alarm_track,
                6: dec_vol_level
            }
            if event == RotaryEncoder.BUTTONDOWN:
                self.alarm_set = (self.alarm_set % 6) + 1
            elif event == RotaryEncoder.CLOCKWISE:
                update_time = False
                if self.alarm_set in clockwise_actions:
                    result = clockwise_actions[self.alarm_set]()
                    if result:
                        update_time = True
                if update_time:
                    self.alarm_time = dt.strptime(f"{self.alarm_hour}:{self.alarm_minute} {self.period}", "%I:%M %p")
            elif event == RotaryEncoder.ANTICLOCKWISE:
                update_time = False
                if self.alarm_set in anticlockwise_actions:
                    result = anticlockwise_actions[self.alarm_set]()
                    if result:
                        update_time = True
                if update_time:
                    self.alarm_time = dt.strptime(f"{self.alarm_hour}:{self.alarm_minute} {self.period}", "%I:%M %p")
        elif self.display_settings_state == 2:
            # Refactored: Use dictionaries to map display_set to actions
            def inc_manual_dim_level():
                self.display_mode = "MANUAL_DIM"
                self.manual_dim_level = (self.manual_dim_level + 1) % 16
            def toggle_display_override():
                self.display_override = "OFF" if self.display_override == "ON" else "ON"
            def dec_manual_dim_level():
                self.display_mode = "MANUAL_DIM"
                self.manual_dim_level = (self.manual_dim_level - 1) % 16

            clockwise_display_actions = {
                1: inc_manual_dim_level,
                2: toggle_display_override
            }
            anticlockwise_display_actions = {
                1: dec_manual_dim_level,
                2: toggle_display_override
            }
            if event == RotaryEncoder.BUTTONDOWN:
                self.display_set = (self.display_set % 2) + 1
            elif event == RotaryEncoder.CLOCKWISE:
                action = clockwise_display_actions.get(self.display_set)
                if action:
                    action()
            elif event == RotaryEncoder.ANTICLOCKWISE:
                action = anticlockwise_display_actions.get(self.display_set)
                if action:
                    action()
            if self.alarm_ringing == 0 and (self.display_mode == "MANUAL_OFF" or self.display_mode == "AUTO_OFF"):
                self.display_mode = "ON"
                self.display_override = "ON"
                self.display_settings_state = 1
            elif self.alarm_ringing == 1 and self.sleep_state == "OFF":
                self.alarm_ringing = 0
                self.alarm_time = self.alarm_time + datetime.timedelta(minutes=1)
                self.sleep_state = "ON"
            elif self.alarm_ringing == 0 and self.sleep_state == "ON":
                self.alarm_stat = "OFF"
                self.sleep_state = "OFF"
        self.save_settings()
        return

    def brightness(self, auto_dim, alarm_stat, display_mode, now):
        if auto_dim == "ON":
            if dt.strptime("07:30", "%H:%M").time() <= now.time() <= dt.strptime("22:00", "%H:%M").time():
                display_mode = "MANUAL_DIM"
            elif dt.strptime("22:00", "%H:%M").time() < now.time() <= dt.strptime("23:59", "%H:%M").time():
                display_mode = "AUTO_DIM"
            if alarm_stat == "OFF":
                if dt.strptime("00:00", "%H:%M").time() < now.time() <= dt.strptime("07:00", "%H:%M").time():
                    if self.display_override == "OFF":
                        display_mode = "AUTO_OFF"
            elif alarm_stat == "ON":
                if dt.strptime("00:01", "%H:%M").time() <= now.time() < dt.strptime(self.alarm_time.time().strftime("%H:%M"), "%H:%M").time():
                    if self.display_override == "OFF":
                        display_mode = "AUTO_OFF"
                if dt.strptime(self.alarm_time.time().strftime("%H:%M"), "%H:%M").time() <= now.time() < dt.strptime("07:30", "%H:%M").time():
                    display_mode = "MANUAL_DIM"
        return display_mode

    def debug_brightness(self, auto_dim, alarm_stat, display_mode, now):
        if auto_dim == "ON":
            if dt.strptime("07:30", "%H:%M").time() <= now.time() <= dt.strptime("12:00", "%H:%M").time():
                display_mode = "MANUAL_DIM"
            elif dt.strptime("12:00", "%H:%M").time() < now.time() <= dt.strptime("12:59", "%H:%M").time():
                display_mode = "AUTO_DIM"
            if alarm_stat == "OFF":
                if dt.strptime("13:00", "%H:%M").time() < now.time() <= dt.strptime("15:00", "%H:%M").time():
                    if self.display_override == "OFF":
                        display_mode = "AUTO_OFF"
            elif alarm_stat == "ON":
                if dt.strptime("00:01", "%H:%M").time() <= now.time() < dt.strptime(self.alarm_time.time().strftime("%H:%M"), "%H:%M").time():
                    if self.display_override == "OFF":
                        display_mode = "AUTO_OFF"
                if dt.strptime(self.alarm_time.time().strftime("%H:%M"), "%H:%M").time() <= now.time() < dt.strptime("07:30", "%H:%M").time():
                    display_mode = "MANUAL_DIM"
        return display_mode

    def display_alpha_message(self, message_type, alpha_message, display_mode):
        if (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF"):
            self.alpha_display.fill(0)
            try:
                self.alpha_display.show()
            except Exception as e:
                self.logger.error("alpha_display.show() error: %s", str(e))
            # Reset cache so next message will display
            self.last_alpha_message = None
            self.last_alpha_brightness = None
            self.last_alpha_type = None
        elif display_mode == "AUTO_DIM" or display_mode == "MANUAL_DIM":
            if display_mode == "AUTO_DIM":
                dim_level = self.auto_dim_level
            elif display_mode == "MANUAL_DIM":
                dim_level = self.manual_dim_level
            # Only update if value or brightness or type changed
            current_brightness = dim_level / 15.0
            if (alpha_message != self.last_alpha_message) or (current_brightness != self.last_alpha_brightness) or (message_type != self.last_alpha_type):
                self.alpha_display.fill(0)
                if message_type == "FLOAT":
                    self.alpha_display.print(str(alpha_message))
                elif message_type == "STR":
                    self.alpha_display.print(alpha_message)
                print(f"dim_level: {dim_level} display_mode: {display_mode}")
                self.alpha_display.brightness = current_brightness
                try:
                    self.alpha_display.show()
                except Exception as e:
                    self.logger.error("alpha_display.show() error: %s", str(e))
                self.last_alpha_message = alpha_message
                self.last_alpha_brightness = current_brightness
                self.last_alpha_type = message_type
            time.sleep(.02)
        return

    def display_num_message(self, num_message, display_mode, now):
        if (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF"):
            self.num_display.fill(0)
            try:
                self.num_display.show()
            except Exception as e:
                self.logger.error("num_display.show() error: %s", str(e))
        elif display_mode == "AUTO_DIM" or display_mode == "MANUAL_DIM":
            if display_mode == "AUTO_DIM":
                dim_level = self.auto_dim_level
            elif display_mode == "MANUAL_DIM":
                dim_level = self.manual_dim_level
            self.num_display.fill(0)
            self.num_display.print(str(num_message))
            self.num_display.colon = now.second % 2
            self.num_display.brightness = dim_level / 15.0
            try:
                self.num_display.show()
            except Exception as e:
                self.logger.error("num_display.show() error: %s", str(e))
        time.sleep(.02)
        return

    def save_settings(self):
        settings = {k: getattr(self, k) for k in self.PERSISTED_SETTINGS}
        # Save alarm_time as string
        settings["alarm_time"] = self.alarm_time.strftime("%H:%M")
        try:
            with open(self.SETTINGS_FILE, "w") as f:
                json.dump(settings, f)
        except Exception as e:
            self.logger.error("Failed to save settings: %s", str(e))

    def load_settings(self):
        try:
            with open(self.SETTINGS_FILE, "r") as f:
                settings = json.load(f)
            self.alarm_hour = settings.get("alarm_hour", self.alarm_hour)
            self.alarm_minute = settings.get("alarm_minute", self.alarm_minute)
            self.period = settings.get("period", self.period)
            self.alarm_stat = settings.get("alarm_stat", self.alarm_stat)
            self.alarm_track = settings.get("alarm_track", self.alarm_track)
            self.vol_level = settings.get("vol_level", self.vol_level)
            self.manual_dim_level = settings.get("manual_dim_level", self.manual_dim_level)
            self.auto_dim_level = settings.get("auto_dim_level", self.auto_dim_level)
            self.auto_dim = settings.get("auto_dim", self.auto_dim)
            self.display_mode = settings.get("display_mode", self.display_mode)
            self.display_override = settings.get("display_override", self.display_override)
            alarm_time_str = settings.get("alarm_time", None)
            if alarm_time_str:
                # Parse alarm_time as HH:MM (24-hour format)
                self.alarm_time = dt.strptime(alarm_time_str, "%H:%M")
                # Update alarm_hour, alarm_minute, and period to match alarm_time
                hour_24 = self.alarm_time.hour
                self.alarm_minute = self.alarm_time.minute
                if hour_24 == 0:
                    self.alarm_hour = 12
                    self.period = "AM"
                elif 1 <= hour_24 < 12:
                    self.alarm_hour = hour_24
                    self.period = "AM"
                elif hour_24 == 12:
                    self.alarm_hour = 12
                    self.period = "PM"
                else:
                    self.alarm_hour = hour_24 - 12
                    self.period = "PM"
        except FileNotFoundError:
            pass
        except Exception as e:
            self.logger.error("Failed to load settings: %s", str(e))

    def handle_eds_wake(self, now):
        # Wake the display on EDS
        if self.display_override == "OFF":
            if self.display_mode == "AUTO_OFF" and 0 < self.distance < 4:
                self.loop_count = 0
                self.display_mode = "AUTO_DIM"
                self.display_override = "ON"
                while self.loop_count <= 100:
                    now = self.get_time()
                    num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
                    self.display_num_message(num_message, self.display_mode, now)
                    time.sleep(.03)
                    self.loop_count += 1
                self.display_mode = "AUTO_OFF"
                self.display_override = "OFF"
            elif self.display_mode == "MANUAL_OFF" and 0 < self.distance < 4:
                self.loop_count = 0
                self.display_mode = "AUTO_DIM"
                self.display_override = "ON"
                while self.loop_count <= 100:
                    now = self.get_time()
                    num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
                    self.display_num_message(num_message, self.display_mode, now)
                    time.sleep(.03)
                    self.loop_count += 1
                self.display_mode = "MANUAL_OFF"
                self.display_override = "OFF"

    def update_main_display(self, now):
        num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
        # Determine current brightness
        if self.display_mode == "AUTO_DIM":
            current_brightness = self.auto_dim_level / 15.0
        elif self.display_mode == "MANUAL_DIM":
            current_brightness = self.manual_dim_level / 15.0
        else:
            current_brightness = self.num_display.brightness
        # Only update if value or brightness changed
        if (num_message != self.last_num_message) or (current_brightness != self.last_num_brightness):
            self.num_display.fill(0)
            self.num_display.print(str(num_message))
            self.num_display.brightness = current_brightness
            self.last_num_message = num_message
            self.last_num_brightness = current_brightness
        # Always update colon and show, for blink effect
        self.num_display.colon = now.second % 2
        try:
            self.num_display.show()
        except Exception as e:
            self.logger.error("num_display.show() error: %s", str(e))
        self.update_alpha_display(now)

    def update_alpha_display(self, now):
        if self.alarm_settings_state == 2:
            if self.alarm_set == 1:
                alpha_message = self.alarm_hour*100 + self.alarm_minute
                self.display_alpha_message("FLOAT", alpha_message, self.display_mode)
            elif self.alarm_set == 2:
                alpha_message = self.alarm_hour*100 + self.alarm_minute
                self.display_alpha_message("FLOAT", alpha_message, self.display_mode)
            elif self.alarm_set == 3:
                alpha_message = self.period
                self.display_alpha_message("STR", alpha_message, self.display_mode)
            elif self.alarm_set == 4:
                alpha_message = self.alarm_stat
                self.display_alpha_message("STR", alpha_message, self.display_mode)
            elif self.alarm_set == 5:
                alpha_message = self.alarm_track
                self.display_alpha_message("FLOAT", alpha_message, self.display_mode)
                if self.use_audio:
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")
            elif self.alarm_set == 6:
                alpha_message = self.vol_level
                self.display_alpha_message("FLOAT", alpha_message, self.display_mode)
                if self.use_audio:
                    self.mixer.setvolume(self.vol_level)
                    os.system(f"mpg123 -q {self.alarm_tracks[self.alarm_track]} &")
        elif self.display_settings_state == 2:
            if self.display_set == 1:
                alpha_message = self.manual_dim_level
                self.display_alpha_message("FLOAT", alpha_message, self.display_mode)
            elif self.display_set == 2:
                alpha_message = self.display_override
                self.display_alpha_message("STR", alpha_message, self.display_mode)
        elif (self.alarm_settings_state == 1 and self.display_settings_state == 1):
            self.alpha_display.fill(0)
            try:
                self.alpha_display.show()
            except Exception as e:
                self.logger.error("alpha_display.show() error: %s", str(e))

    def handle_display_off(self):
        self.alpha_display.fill(0)
        try:
            self.alpha_display.show()
        except Exception as e:
            self.logger.error("alpha_display.show() error: %s", str(e))
        self.num_display.fill(0)
        try:
            self.num_display.show()
        except Exception as e:
            self.logger.error("num_display.show() error: %s", str(e))

    def main_loop_iteration(self):
        now = self.get_time()
        if self.debug == "YES":
            self.display_mode = self.debug_brightness(self.auto_dim, self.alarm_stat, self.display_mode, now)
        else:
            self.display_mode = self.brightness(self.auto_dim, self.alarm_stat, self.display_mode, now)
        if (self.display_mode == "MANUAL_OFF" or self.display_mode == "AUTO_OFF") and self.display_override == "OFF":
            self.distance = self.eds()
            print(f"{self.distance} {self.display_mode}")
        self.handle_eds_wake(now)
        if self.display_mode != "MANUAL_OFF":
            self.update_main_display(now)
        elif (self.display_mode == "MANUAL_OFF" or self.display_mode == "AUTO_OFF"):
            self.handle_display_off()
        if self.alarm_stat == "ON":
            self.check_alarm(now)

    def run(self):
        try:
            while True:
                self.main_loop_iteration()
                time.sleep(0.05)
        except KeyboardInterrupt:
            self.alpha_display.fill(0)
            try:
                self.alpha_display.show()
            except Exception as e:
                self.logger.error("alpha_display.show() error: %s", str(e))
            self.num_display.fill(0)
            try:
                self.num_display.show()
            except Exception as e:
                self.logger.error("num_display.show() error: %s", str(e))
        finally:
            try:
                self.alpha_display.fill(0)
                self.alpha_display.show()
            except Exception as e:
                self.logger.error("alpha_display.show() error: %s", str(e))
            try:
                self.num_display.fill(0)
                self.num_display.show()
            except Exception as e:
                self.logger.error("num_display.show() error: %s", str(e))

if __name__ == "__main__":
    clock = AlarmClock()
    clock.run()
