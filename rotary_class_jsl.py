#!/usr/bin/env python
# Raspberry Pi Rotary Encoder Class
# $Id: rotary_class.py,v 1.7 2017/01/07 11:38:47 bob Exp $
#
# Copyright 2011 Ben Buxton. Licenced under the GNU GPL Version 3.
# Contact: bb@cactii.net
# Adapted by : Bob Rathbone and Lubos Ruckl (Czech republic)
# Site   : http://www.bobrathbone.com
#
# This class uses standard rotary encoder with push switch
# License: GNU V3, See https://www.gnu.org/copyleft/gpl.html
#
# Disclaimer: Software is provided as is and absolutly no warranties are implied or given.
#             The authors shall not be liable for any loss or damage however caused.
#
#
# A typical mechanical rotary encoder emits a two bit gray code
# on 3 output pins. Every step in the output (often accompanied
# by a physical 'click') generates a specific sequence of output
# codes on the pins.
#
# There are 3 pins used for the rotary encoding - one common and
# two 'bit' pins.
#
# The following is the typical sequence of code on the output when
# moving from one step to the next:
#
#   Position   Bit1   Bit2
#   ----------------------
#     Step1     0      0
#      1/4      1      0
#      1/2      1      1
#      3/4      0      1
#     Step2     0      0
#
# From this table, we can see that when moving from one 'click' to
# the next, there are 4 changes in the output code.
#
# - From an initial 0 - 0, Bit1 goes high, Bit0 stays low.
# - Then both bits are high, halfway through the step.
# - Then Bit1 goes low, but Bit2 stays high.
# - Finally at the end of the step, both bits return to 0.
#
# Detecting the direction is easy - the table simply goes in the other
# direction (read up instead of down).
#
# To decode this, we use a simple state machine. Every time the output
# code changes, it follows state, until finally a full steps worth of
# code is received (in the correct order). At the final 0-0, it returns
# a value indicating a step in one direction or the other.
#
# It's also possible to use 'half-step' mode. This just emits an event
# at both the 0-0 and 1-1 positions. This might be useful for some
# encoders where you want to detect all positions.
#
# If an invalid state happens (for example we go from '0-1' straight
# to '1-0'), the state machine resets to the start until 0-0 and the
# next valid codes occur.
#
# The biggest advantage of using a state machine over other algorithms
# is that this has inherent debounce built in. Other algorithms emit spurious
# output with switch bounce, but this one will simply flip between
# sub-states until the bounce settles, then continue along the state
# machine.
# A side effect of debounce is that fast rotations can cause steps to
# be skipped. By not requiring debounce, fast rotations can be accurately
# measured.
# Another advantage is the ability to properly handle bad state, such
# as due to EMI, etc.
# It is also a lot simpler than others - a static state table and less
# than 10 lines of logic.
#
# Modified by JSL 20170910 adding two stand-alone switches

import sys
import lgpio
print("[DEBUG] lgpio attributes:", dir(lgpio))
sys.exit(1)

R_CCW_BEGIN   = 0x1
R_CW_BEGIN    = 0x2
R_START_M     = 0x3
R_CW_BEGIN_M  = 0x4
R_CCW_BEGIN_M = 0x5

# Values returned by 'process_'
# No complete step yet.
DIR_NONE = 0x0
# Clockwise step.
DIR_CW = 0x10
# Anti-clockwise step.
DIR_CCW = 0x20

R_START = 0x0

HALF_TAB = (
  # R_START (00)
  (R_START_M,           R_CW_BEGIN,     R_CCW_BEGIN,  R_START),
  # R_CCW_BEGIN
  (R_START_M | DIR_CCW, R_START,        R_CCW_BEGIN,  R_START),
  # R_CW_BEGIN
  (R_START_M | DIR_CW,  R_CW_BEGIN,     R_START,      R_START),
  # R_START_M (11)
  (R_START_M,           R_CCW_BEGIN_M,  R_CW_BEGIN_M, R_START),
  # R_CW_BEGIN_M
  (R_START_M,           R_START_M,      R_CW_BEGIN_M, R_START | DIR_CW),
  # R_CCW_BEGIN_M
  (R_START_M,           R_CCW_BEGIN_M,  R_START_M,    R_START | DIR_CCW),
)

R_CW_FINAL  = 0x1
R_CW_BEGIN  = 0x2
R_CW_NEXT   = 0x3
R_CCW_BEGIN = 0x4
R_CCW_FINAL = 0x5
R_CCW_NEXT  = 0x6

FULL_TAB = (
  # R_START
  (R_START,    R_CW_BEGIN,  R_CCW_BEGIN, R_START),
  # R_CW_FINAL
  (R_CW_NEXT,  R_START,     R_CW_FINAL,  R_START | DIR_CW),
  # R_CW_BEGIN
  (R_CW_NEXT,  R_CW_BEGIN,  R_START,     R_START),
  # R_CW_NEXT
  (R_CW_NEXT,  R_CW_BEGIN,  R_CW_FINAL,  R_START),
  # R_CCW_BEGIN
  (R_CCW_NEXT, R_START,     R_CCW_BEGIN, R_START),
  # R_CCW_FINAL
  (R_CCW_NEXT, R_CCW_FINAL, R_START,     R_START | DIR_CCW),
  # R_CCW_NEXT
  (R_CCW_NEXT, R_CCW_FINAL, R_CCW_BEGIN, R_START),
)

# Enable this to emit codes twice per step.
# HALF_STEP == True: emits a code at 00 and 11
# HALF_STEP == False: emits a code at 00 only
HALF_STEP     = False
STATE_TAB = HALF_TAB if HALF_STEP else FULL_TAB

# State table has, for each state (row), the new state
# to set based on the next encoder output. From left to right in,
# the table, the encoder outputs are 00, 01, 10, 11, and the value
# in that position is the new state to set.

class RotaryEncoder:
    state = R_START
    pinA = None
    pinB = None
    CLOCKWISE=1
    ANTICLOCKWISE=2
    BUTTONDOWN=3
    BUTTONUP=4

    def __init__(self, pinA, pinB, button, mode_switch, aux_switch, callback, mode_callback, aux_callback, revision):
        self.pinA = pinA
        self.pinB = pinB
        self.button = button
        self.mode_switch = mode_switch
        self.aux_switch = aux_switch
        self.callback = callback
        self.mode_callback = mode_callback
        self.aux_callback = aux_callback
        self.h = lgpio.gpiochip_open(0)
        # Set up pins as inputs with pull-ups using correct lgpio API
        lgpio.gpio_set_mode(self.h, self.pinA, lgpio.INPUT)
        lgpio.gpio_set_pull_up_down(self.h, self.pinA, lgpio.PUD_UP)
        lgpio.gpio_set_mode(self.h, self.pinB, lgpio.INPUT)
        lgpio.gpio_set_pull_up_down(self.h, self.pinB, lgpio.PUD_UP)
        lgpio.gpio_set_mode(self.h, self.button, lgpio.INPUT)
        lgpio.gpio_set_pull_up_down(self.h, self.button, lgpio.PUD_UP)
        if self.mode_switch is not None:
            lgpio.gpio_set_mode(self.h, self.mode_switch, lgpio.INPUT)
            lgpio.gpio_set_pull_up_down(self.h, self.mode_switch, lgpio.PUD_UP)
        if self.aux_switch is not None:
            lgpio.gpio_set_mode(self.h, self.aux_switch, lgpio.INPUT)
            lgpio.gpio_set_pull_up_down(self.h, self.aux_switch, lgpio.PUD_UP)
        # Register alert functions for rotary and buttons
        lgpio.set_alert_func(self.h, self.pinA, self._switch_event)
        lgpio.set_alert_func(self.h, self.pinB, self._switch_event)
        lgpio.set_alert_func(self.h, self.button, self._button_event)
        lgpio.set_alert_func(self.h, self.mode_switch, self._mode_callback)
        lgpio.set_alert_func(self.h, self.aux_switch, self._aux_callback)

    def _switch_event(self, h, gpio, level, tick):
        # Only trigger on edge (not level change to 2)
        if level == 2:
            return
        pinstate = (lgpio.gpio_read(self.h, self.pinB) << 1) | lgpio.gpio_read(self.h, self.pinA)
        self.state = STATE_TAB[self.state & 0xf][pinstate]
        result = self.state & 0x30
        if result:
            event = self.CLOCKWISE if result == 32 else self.ANTICLOCKWISE
            self.callback(event)

    def _button_event(self, h, gpio, level, tick):
        if level == 2:
            return
        if lgpio.gpio_read(self.h, self.button):
            event = self.BUTTONUP
        else:
            event = self.BUTTONDOWN
        self.callback(event)

    def _mode_callback(self, h, gpio, level, tick):
        if level == 2:
            return
        if lgpio.gpio_read(self.h, self.mode_switch):
            channel = self.BUTTONUP
        else:
            channel = self.BUTTONDOWN
        self.mode_callback(channel)

    def _aux_callback(self, h, gpio, level, tick):
        if level == 2:
            return
        if lgpio.gpio_read(self.h, self.aux_switch):
            channel = self.BUTTONUP
        else:
            channel = self.BUTTONDOWN
        self.aux_callback(channel)

    def getSwitchState(self, switch):
        return lgpio.gpio_read(self.h, switch)
