# Alarm clock with LED Display
# James S. Lucas
# Bookworm/2025: Uses lgpio (not RPi.GPIO) for GPIO compatibility with Raspberry Pi OS Bookworm.
# Requires: sudo apt install python3-lgpio; pip3 install adafruit-circuitpython-ht16k33
#
# Issues and todo: alarm pre-selects, auto alarm repeat, issues with dimLevel 0 line 402 auto time setting conflict with manual off
#   , display override move to display functions? LED blinking when after 8PM
# 20171118
# 20250526
import os
import sys
import time
import datetime
from datetime import datetime as dt
from adafruit_ht16k33.segments import Seg7x4
from adafruit_ht16k33.segments import Seg14x4
import logging
try:
    import lgpio
except ImportError:
    print("ERROR: lgpio not installed. Please run: sudo apt install python3-lgpio")
    sys.exit(1)
try:
    import board
    import busio
except ImportError:
    print("ERROR: board/busio not installed. Please run: pip3 install adafruit-blinka")
    sys.exit(1)
from rotary_class_jsl import RotaryEncoder

# Set up logger for error logging
logger = logging.getLogger("aclock")
logger.setLevel(logging.ERROR)
handler = logging.FileHandler("aclock_error.log")
formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Define rotary encoder and separate pushbutton GPIO input pins (GPIO setup in separate rotary_class)
PIN_A = 19    # Pin 19
PIN_B = 26    # Pin 26
BUTTON = 12   # Pin 12
mode_switch = 13
aux_switch = 21

# Open GPIO chip handle
try:
    h = lgpio.gpiochip_open(0)
except Exception as e:
    logger.error(f"Failed to open GPIO chip: {e}")
    print(f"ERROR: Failed to open GPIO chip: {e}")
    sys.exit(1)

# Define EDS GPIO input and output pins and setup GPIO
TRIG = 5
ECHO = 6
lgpio.set_mode(h, TRIG, lgpio.OUTPUT)
lgpio.set_mode(h, ECHO, lgpio.INPUT)

# Set up rotary encoder pins as GPIO inputs with pull-ups
for pin in [PIN_A, PIN_B, BUTTON, mode_switch, aux_switch]:
    lgpio.set_mode(h, pin, lgpio.INPUT)
    lgpio.set_pull_up_down(h, pin, lgpio.PUD_UP)

# Pulse EDS and wait for sensor to settle
lgpio.gpio_write(h, TRIG, 0)
print("Waiting For Sensor To Settle")
time.sleep(2)

# Define increment for alarm minute ajustment
minute_incr = 1

# Create display instances (default I2C address (0x70))
try:
    i2c = busio.I2C(board.SCL, board.SDA)
    alphadisplay = Seg14x4(i2c)
    numdisplay = Seg7x4(i2c, address=0x72)
except Exception as e:
    logger.error(f"I2C/Display initialization error: {e}")
    print(f"ERROR: I2C/Display initialization error: {e}")
    lgpio.gpiochip_close(h)
    sys.exit(1)

# Initialize the display. Must be called once before using the display.
alphadisplay.fill(0)
numdisplay.fill(0)
numdisplay.brightness = 0.375  # 6/16, since range is 0.0-1.0

# Audio feature flag
use_audio = False  # Set to True to enable audio features

# Create Audio Mixer instance if audio is enabled
if use_audio:
    import alsaaudio
    mixer = alsaaudio.Mixer('PCM')

mode_state = 1 # Display mode (1 = display time, 2 = alarm setting)
aux_state = 1
display_mode = "MANUAL_DIM"
display_override = "ON"
alarm_hour = 4 # Hour portion of the alarm
alarm_minute = 0 # Minute portion of the alarm
alarm_time = dt.strptime("04:00", "%H:%M")
alarmSet = 1 # Alarm setting mode (1 hour, 2 minute, 3 on or off)
auxSet = 1
alarm_stat = "OFF" # Alarm active or intactive (ON or OFF)
alarm_ringing = 0
sleep_state = "OFF"
period = "AM"
dimLevel = 6 # Display brightness range 0 to 15. Scaled 0 to 16 with 0 = off
auto_dimLevel = 0
manual_dimLevel = 6
alarmTrack = 1
volLevel = 65
alarm_tracks = {1: '01.mp3', 2: '02.mp3', 3: '03.mp3', 4: '04.mp3', 5: '05.mp3', 6: '06.mp3'}
distance = 0
autoDim = "ON"
loop_count = 0
debug = "NO"

def get_time():
   now = dt.now()
   return now

def check_alarm(now):
   global alarm_stat
   global mode_state
   global alarm_time
   global alarmSet
   global alarm_ringing
   global sleep_state
   global distance
   loopCount = 0
   volIncrease = 0
   timeDecrease = 0
   print(f"time: {now.time()} {period}  alarm time: {alarm_time.time()}")
   if now.strftime("%p") == period and now.time() >= alarm_time.time() and alarm_stat == "ON":
      alarm_ringing = 1
      sleep_state = "OFF"
      while alarm_ringing == 1 and alarm_stat == "ON":
         loopCount += 1
         delay_loop = 0
         alphadisplay.fill(0)
         alphadisplay.print("RING")
         alphadisplay.show()
         now = get_time()
         numdisplay.fill(0)
         numdisplay.print(int(now.strftime("%I"))*100+int(now.strftime("%M")))
         numdisplay.colon = now.second % 2
         try:
            numdisplay.show()
         except Exception as e:
            logger.error("numdisplay.show() error: %s", str(e))
         if use_audio:
            if loopCount % 10 == 0 and (volLevel + volIncrease) <= 90:
               volIncrease += 5
            if loopCount % 10 ==0 and timeDecrease <= 2.25:
               timeDecrease += .25
            mixer.setvolume(volLevel+volIncrease)
            os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
         print(f"alarm ring, now: {now.time()} alarm: {alarm_time.time()} Count: {loopCount} Vol: {volLevel+volIncrease} Ring Time: {3-timeDecrease} alarm_ringing: {alarm_ringing} sleep_state: {sleep_state}")
         time.sleep(1)
         while delay_loop <= (2-timeDecrease):
            distance = eds()
            time.sleep(.1)
            delay_loop += .1
            # print str(distance) + " Delay: " + str(delay_loop) + " Time: " + str(2-timeDecrease)
            if 0 < distance < 4:
               print("Should be sleep state now")
               delay_loop = 3
               alarm_ringing = 0
               alarm_time = alarm_time+datetime.timedelta(minutes=1)
               sleep_state = "ON"
   elif now >= alarm_time and alarm_stat == "OFF":
      print("alarm mode off")
   return

def eds():
   lgpio.gpio_write(h, TRIG, 0)
   time.sleep(0.000002)
   lgpio.gpio_write(h, TRIG, 1)
   time.sleep(0.000015)
   lgpio.gpio_write(h, TRIG, 0)
   while lgpio.gpio_read(h, ECHO)==0:
      pulse_start = time.time()
   while lgpio.gpio_read(h, ECHO)==1:
      pulse_end = time.time()
   pulse_duration = pulse_end - pulse_start
   distance = pulse_duration * 6752
   distance = round(distance, 2)
   return distance

# Callback function used by GPIO interrupt, runs in separate thread
# Used for mode pushbutton
def mode_callback(channel):
   global mode_state
   global aux_state
   global alarm_stat
   global alarm_ringing
   global sleep_state
   global alarmSet
   aux_state = 1
   if alarm_ringing == 1:
      alarm_ringing = 0
      alarm_stat = "OFF"
      sleep_state = "OFF"
   elif mode_state == 1:
      mode_state = 2
      alarmSet = 1
   elif mode_state == 2:
      mode_state = 1
      alphadisplay.fill(0)
      try:
         alphadisplay.show()
      except Exception as e:
         logger.error("alphadisplay.show() error: %s", str(e))
      time.sleep(.5)
   return

# Callback function used by GPIO interrupt, runs in separate thread
# Used for aux pushbutton
def aux_callback(channel):
   global mode_state
   global aux_state
   global alarm_stat
   global alarm_ringing
   global sleep_state
   global auxSet
   mode_state = 1
   if alarm_ringing == 1:
      alarm_ringing = 0
      alarm_stat = "OFF"
      sleep_state = "OFF"
   elif aux_state == 1:
      aux_state = 2
      auxSet = 1
   elif aux_state == 2:
      aux_state = 1
      alphadisplay.fill(0)
      try:
         alphadisplay.show()
      except Exception as e:
         logger.error("alphadisplay.show() error: %s", str(e))
      time.sleep(.5)
   return

# This is the event callback routine to handle events for the rotary encoder
def switch_event(event):
   global alarm_hour
   global alarm_minute
   global alarm_time
   global period
   global alarmSet
   global auxSet
   global alarm_stat
   global alarm_ringing
   global sleep_state
   global minute_incr
   global manual_dimLevel
   global alarmTrack
   global volLevel
   global mode_state
   global aux_state
   global display_mode
   global display_override
   if mode_state == 2:
      if event == RotaryEncoder.BUTTONDOWN:
         if alarmSet == 1:
            alarmSet = 2
         elif alarmSet == 2:
            alarmSet = 3
         elif alarmSet == 3:
            alarmSet = 4
         elif alarmSet == 4:
            alarmSet = 1
      elif event == RotaryEncoder.CLOCKWISE:
         if alarmSet == 1:
            if alarm_hour == 12:
               alarm_hour = 1
            else:
               alarm_hour += 1
            print(f"clockwise {alarm_hour}")
         if alarmSet == 2:
            if alarm_minute == 60-minute_incr:
               alarm_minute = 0
            else:
               alarm_minute += minute_incr
            print(f"clockwise {alarm_minute}")
         if alarmSet == 3:
            if period == "AM":
               period = "PM"
            elif period == "PM":
               period = "AM"
            print(f"clockwise {period}")
         # alarm_time = dt.strptime(str(datetime.date.today()+datetime.timedelta(days=1))+" "+str(alarm_hour)+":"+str(alarm_minute)+" "+period, "%Y-%m-%d %I:%M %p")
         alarm_time = dt.strptime(str(alarm_hour)+":"+str(alarm_minute)+" "+period, "%I:%M %p")
         # print alarm_time.strftime("%I:%M %p")
         if alarmSet == 4:
            if alarm_stat == "ON":
               alarm_stat = "OFF"
            elif alarm_stat == "OFF":
               alarm_stat = "ON"
            print(f"clockwise {alarm_stat}")
      elif event == RotaryEncoder.ANTICLOCKWISE:
         if alarmSet == 1:
            if alarm_hour == 1:
               alarm_hour = 12
            else:
               alarm_hour -= 1
            print(f"counter clockwise {alarm_hour}")
         if alarmSet == 2:
            if alarm_minute == 0:
               alarm_minute = 60-minute_incr
            else:
               alarm_minute -= minute_incr
            print(f"counter clockwise {alarm_minute}")
            time.sleep(.2)
         if alarmSet == 3:
            if period == "AM":
               period = "PM"
            elif period == "PM":
               period = "AM"
            print(f"counter clockwise {period}")
         # alarm_time = dt.strptime(str(datetime.date.today())+" "+str(alarm_hour)+":"+str(alarm_minute)+" "+period, "%Y-%m-%d %I:%M %p")
         alarm_time = dt.strptime(str(alarm_hour)+":"+str(alarm_minute)+" "+period, "%I:%M %p")
         # print alarm_time.strftime("%I:%M %p")
         if alarmSet == 4:
            if alarm_stat == "ON":
               alarm_stat = "OFF"
            elif alarm_stat == "OFF":
               alarm_stat = "ON"
            print(f"counter clockwise {alarm_stat}")
   if aux_state == 2:
      if event == RotaryEncoder.BUTTONDOWN:
         if auxSet == 1:
            auxSet = 2
         elif auxSet == 2:
            auxSet = 3
         elif auxSet == 3:
            auxSet = 4
         elif auxSet == 4:
            auxSet = 1
      elif event == RotaryEncoder.CLOCKWISE and auxSet==1:
         display_mode = "MANUAL_DIM"
         if manual_dimLevel == 15:
            manual_dimLevel = 0
         else:
            manual_dimLevel += 1
      elif event == RotaryEncoder.ANTICLOCKWISE and auxSet==1:
         display_mode = "MANUAL_DIM"
         if manual_dimLevel == 0:
            manual_dimLevel = 15
         else:
            manual_dimLevel -= 1
      elif event == RotaryEncoder.CLOCKWISE and auxSet==2:
         if alarmTrack == 6:
            alarmTrack = 1
         else:
            alarmTrack += 1
         if use_audio:
            os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
            time.sleep(.5)
         else:
            time.sleep(.5)
      elif event == RotaryEncoder.ANTICLOCKWISE and auxSet==2:
         if alarmTrack == 1:
            alarmTrack = 6
         else:
            alarmTrack -= 1
         if use_audio:
            os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
            time.sleep(.5)
         else:
            time.sleep(.5)
      elif event == RotaryEncoder.CLOCKWISE and auxSet==3:
         if volLevel == 95:
            volLevel = 0
         else:
            volLevel += 1
         if use_audio:
            mixer.setvolume(volLevel)
            os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
            time.sleep(.5)
         else:
            time.sleep(.5)
      elif event == RotaryEncoder.ANTICLOCKWISE and auxSet==3:
         if volLevel == 0:
            volLevel = 95
         else:
            volLevel -= 1
         if use_audio:
            mixer.setvolume(volLevel)
            os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
            time.sleep(.5)
         else:
            time.sleep(.5)
      elif event == RotaryEncoder.CLOCKWISE and auxSet==4:
         if display_override == "ON":
            display_override = "OFF"
         elif display_override == "OFF":
            display_override = "ON"
      elif event == RotaryEncoder.ANTICLOCKWISE and auxSet==4:
         if display_override == "ON":
            display_override = "OFF"
         elif display_override == "OFF":
            display_override = "ON"
      if alarm_ringing == 0 and (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF"):
         display_mode = "ON"
         display_override = "ON"
         aux_state = 1
      elif alarm_ringing == 1 and sleep_state == "OFF":
         alarm_ringing = 0
         alarm_time = alarm_time+datetime.timedelta(minutes=1)
         sleep_state = "ON"
      elif alarm_ringing == 0 and sleep_state == "ON":
         alarm_stat = "OFF"
         sleep_state = "OFF"
   return

def brightness(autoDim, alarm_stat, display_mode):
   global display_override
   if autoDim == "ON":
      if dt.strptime("07:30", "%H:%M").time() <= now.time() <= dt.strptime("20:00", "%H:%M").time():
         display_mode = "MANUAL_DIM"
      elif dt.strptime("20:00", "%H:%M").time() < now.time() <= dt.strptime("23:59", "%H:%M").time():
         display_mode = "AUTO_DIM"
      if alarm_stat == "OFF":
         if dt.strptime("00:00", "%H:%M").time() < now.time() <= dt.strptime("07:00", "%H:%M").time():
            if display_override == "OFF":
               display_mode = "AUTO_OFF"
      elif alarm_stat == "ON":
         if dt.strptime("00:01", "%H:%M").time() <= now.time() < dt.strptime(alarm_time.time().strftime("%H:%M"), "%H:%M").time():
            if display_override == "OFF":
               display_mode = "AUTO_OFF"
         if dt.strptime(alarm_time.time().strftime("%H:%M"), "%H:%M").time() <= now.time() < dt.strptime("07:30", "%H:%M").time():
            display_mode = "MANUAL_DIM"
   return display_mode

def debug_brightness(autoDim, alarm_stat, display_mode):
   global display_override
   if autoDim == "ON":
      if dt.strptime("07:30", "%H:%M").time() <= now.time() <= dt.strptime("12:00", "%H:%M").time():
         display_mode = "MANUAL_DIM"
      elif dt.strptime("12:00", "%H:%M").time() < now.time() <= dt.strptime("12:59", "%H:%M").time():
         display_mode = "AUTO_DIM"
      if alarm_stat == "OFF":
         if dt.strptime("13:00", "%H:%M").time() < now.time() <= dt.strptime("15:00", "%H:%M").time():
            if display_override == "OFF":
               display_mode = "AUTO_OFF"
      elif alarm_stat == "ON":
         if dt.strptime("00:01", "%H:%M").time() <= now.time() < dt.strptime(alarm_time.time().strftime("%H:%M"), "%H:%M").time():
            if display_override == "OFF":
               display_mode = "AUTO_OFF"
         if dt.strptime(alarm_time.time().strftime("%H:%M"), "%H:%M").time() <= now.time() < dt.strptime("07:30", "%H:%M").time():
            display_mode = "MANUAL_DIM"
   return display_mode

def display_alphamessage(message_type, alpha_message, decimal_state, decimal_place, display_mode, auto_dimLevel, manual_dimLevel):
   if (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF"):
      alphadisplay.fill(0)
      try:
         alphadisplay.show()
      except Exception as e:
         logger.error("alphadisplay.show() error: %s", str(e))
   elif display_mode == "AUTO_DIM" or display_mode == "MANUAL_DIM":
      if display_mode == "AUTO_DIM":
         dimLevel = auto_dimLevel
      elif display_mode == "MANUAL_DIM":
         dimLevel = manual_dimLevel
      alphadisplay.fill(0)
      if message_type == "FLOAT":
         alphadisplay.print(str(alpha_message))
      elif message_type == "STR":
         alphadisplay.print(alpha_message)
      if decimal_state == "ON":
         alphadisplay.set_decimal(decimal_place,True)
      print(f"dimLevel: {dimLevel} display_mode: {display_mode}")
      # Convert dimLevel (0-15) to float (0.0-1.0) for brightness
      brightness_val = max(0.0, min(1.0, float(dimLevel) / 15.0))
      alphadisplay.brightness = brightness_val
      try:
         alphadisplay.show()
      except Exception as e:
            logger.error("alphadisplay.show() error: %s", str(e))
      time.sleep(.02)
   return

def display_nummessage(num_message, alarm_stat, display_mode, auto_dimLevel, manual_dimLevel):
   if (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF"):
      numdisplay.fill(0)
      try:
         numdisplay.show()
      except Exception as e:
         logger.error("numdisplay.show() error: %s", str(e))
   elif display_mode == "AUTO_DIM" or display_mode == "MANUAL_DIM":
      if display_mode == "AUTO_DIM":
         dimLevel = auto_dimLevel
      elif display_mode == "MANUAL_DIM":
         dimLevel = manual_dimLevel
      numdisplay.fill(0)
      numdisplay.print(str(num_message))
      numdisplay.colon = now.second %2
      # Convert dimLevel (0-15) to float (0.0-1.0) for brightness
      brightness_val = max(0.0, min(1.0, float(dimLevel) / 15.0))
      numdisplay.brightness = brightness_val
      try:
         numdisplay.show()
      except Exception as e:
         logger.error("numdisplay.show() error: %s", str(e))
   time.sleep(.02)
   return

# Define the rotary and stand-alone switches
rswitch = RotaryEncoder(PIN_A,PIN_B,BUTTON,mode_switch,aux_switch,switch_event,mode_callback,aux_callback,2)

try:
   while True:
      now = get_time()
      if debug == "YES":
         display_mode = debug_brightness(autoDim, alarm_stat, display_mode)
      else:
         display_mode = brightness(autoDim, alarm_stat, display_mode)
      if (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF") and display_override == "OFF":
         distance = eds()
         print(f"{distance} {display_mode}")
      # Wake the display on EDS
      if display_override == "OFF":
         if display_mode == "AUTO_OFF" and 0 < distance < 4:
            loop_count = 0
            display_mode = "AUTO_DIM"
            display_override = "ON"
            while loop_count <= 100:
               now = get_time()
               num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
               display_nummessage(num_message, alarm_stat, display_mode, auto_dimLevel, manual_dimLevel)
               time.sleep(.03) # note will be 5 sec delay inluding .02 sec in display_nummessage
               loop_count += 1
            display_mode = "AUTO_OFF"
            display_override = "OFF"
         elif display_mode == "MANUAL_OFF" and 0 < distance < 4:
            loop_count = 0
            display_mode = "AUTO_DIM"
            display_override = "ON"
            while loop_count <= 100:
               now = get_time()
               num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
               display_nummessage(num_message, alarm_stat, display_mode, auto_dimLevel, manual_dimLevel)
               time.sleep(.03) # note will be 5 sec delay inluding .02 sec in display_nummessage
               loop_count += 1
            display_mode = "MANUAL_OFF"
            display_override = "OFF"
      if display_mode != "MANUAL_OFF":
         num_message = int(now.strftime("%I"))*100+int(now.strftime("%M"))
         display_nummessage(num_message, alarm_stat, display_mode, auto_dimLevel, manual_dimLevel)
         if mode_state == 2:
            if alarmSet == 1:
               alpha_message = alarm_hour*100 + alarm_minute
               display_alphamessage("FLOAT", alpha_message, "ON", 1, display_mode, auto_dimLevel, manual_dimLevel)
            elif alarmSet == 2:
               alpha_message = alarm_hour*100 + alarm_minute
               display_alphamessage("FLOAT", alpha_message, "ON", 3, display_mode, auto_dimLevel, manual_dimLevel)
            elif alarmSet == 3:
               alpha_message = period
               display_alphamessage("STR", alpha_message, "OFF", 0, display_mode, auto_dimLevel, manual_dimLevel)
            elif alarmSet == 4:
               alpha_message = alarm_stat
               display_alphamessage("STR", alpha_message, "OFF", 0, display_mode, auto_dimLevel, manual_dimLevel)
         elif aux_state == 2:
            if auxSet == 1:
               alpha_message = manual_dimLevel
               display_alphamessage("FLOAT", alpha_message, "OFF", 0, display_mode, auto_dimLevel, manual_dimLevel)
            elif auxSet == 2:
               alpha_message = alarmTrack
               display_alphamessage("FLOAT", alpha_message, "OFF", 0, display_mode, auto_dimLevel, manual_dimLevel)
               if use_audio:
                  os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
                  time.sleep(.5)
               else:
                  time.sleep(.5)
            elif auxSet == 3:
               alpha_message = volLevel
               display_alphamessage("FLOAT", alpha_message, "OFF", 0, display_mode, auto_dimLevel, manual_dimLevel)
               if use_audio:
                  mixer.setvolume(volLevel)
                  os.system('mpg123 -q '+ alarm_tracks[alarmTrack] +' &')
                  time.sleep(.5)
               else:
                  time.sleep(.5)
            elif auxSet == 4:
               alpha_message = display_override
               display_alphamessage("STR", alpha_message, "OFF", 0, display_mode, auto_dimLevel, manual_dimLevel)
         elif (mode_state == 1 and aux_state == 1):
           alphadisplay.fill(0)
           try:
              alphadisplay.show()
           except Exception as e:
              logger.error("alphadisplay.show() error: %s", str(e))
      elif (display_mode == "MANUAL_OFF" or display_mode == "AUTO_OFF"):
         alphadisplay.fill(0)
         try:
            alphadisplay.show()
         except Exception as e:
            logger.error("alphadisplay.show() error: %s", str(e))
         numdisplay.fill(0)
         try:
            numdisplay.show()
         except Exception as e:
            logger.error("numdisplay.show() error: %s", str(e))
      if alarm_stat == "ON":
         check_alarm(now)
except KeyboardInterrupt:
   alphadisplay.fill(0)
   try:
      alphadisplay.show()
   except Exception as e:
      logger.error("alphadisplay.show() error: %s", str(e))
   numdisplay.fill(0)
   try:
      numdisplay.show()
   except Exception as e:
      logger.error("numdisplay.show() error: %s", str(e))
finally:
   lgpio.gpiochip_close(h)
