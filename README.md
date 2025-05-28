# Alarm-Clock  
Personal project. Not fully baked. UI is not great. Code is not very well written and is unclear.  
Raspberry Pi based alarm clock with 7-segment display.  
  
Schematic  
![Alarm-Clock](./images/schematic.png)

## Features  
1. Dimmable
2. Choose alarm sound
3. Alarm starts quietly and gradually gets louder
4. Wave to snooze
 

## Operation  
The alarm clock is controlled using a rotary encoder (with push button) and two additional pushbuttons: one for Alarm Settings and one for Display Settings. The LED displays show the current time, alarm settings, and other status information.

### Normal Time Display
- **Default Mode:** The numeric display shows the current time in HHMM format. The colon blinks every second.
- **Brightness:** The display brightness is automatically or manually controlled based on the configured mode.

### Setting the Alarm
1. **Enter Alarm Setting Mode:**
   - Press the **Alarm Settings** button.
   - The alphanumeric display will show the alarm time or setting currently being adjusted.
2. **Adjust Alarm Hour:**
   - Rotate the encoder clockwise to increase the hour, counterclockwise to decrease.
   - Press the encoder button to move to minute adjustment.
3. **Adjust Alarm Minute:**
   - Rotate the encoder to set the minutes.
   - Press the encoder button to move to AM/PM selection.
4. **Set AM/PM:**
   - Rotate the encoder to toggle between AM and PM.
   - Press the encoder button to move to alarm ON/OFF selection.
5. **Turn Alarm ON/OFF:**
   - Rotate the encoder to toggle the alarm status.
   - Press the encoder button to finish and return to normal display.

### Display Settings
- **Enter Display Settings:** Press the **Display Settings** button.
- **Adjust Brightness:** In Display Settings mode, rotate the encoder to change manual brightness.
- **Select Alarm Track:** Press the encoder to cycle to alarm track selection, then rotate to choose a track.
- **Adjust Volume:** Press again to cycle to volume adjustment, then rotate to set volume.
- **Display Override:** Press again to toggle display override ON/OFF.

### Alarm Operation
- **Alarm Ringing:** When the alarm time is reached and the alarm is ON, the display will show "RING" and the alarm will sound (if audio is enabled).
- **Snooze:** Wave your hand in front of the EDS sensor to snooze the alarm for 1 minute.
- **Turn Off Alarm:** Press the alarm or rotary encoder button to turn off the alarm.

### Display Modes
- **Manual/Auto Dim:** The display automatically dims or turns off at night, or you can manually adjust brightness in Display Settings mode.
- **Wake Display:** If the display is off, wave your hand in front of the EDS sensor to temporarily wake it.

### Persistent Storage
- **Automatic Saving:** Alarm and display settings (such as alarm time, alarm status, brightness, alarm track, volume, and display override) are automatically saved to persistent storage. Your settings will be restored after a power cycle or reboot.

### Notes
- All settings and states are displayed on the alphanumeric display for clarity.
- For more details on wiring, setup, or troubleshooting, see the rest of this README or the code comments.

## Parts List
1. 1 x Raspberry Pi Model 2 w/ SD Card
2. 1 x USB power supply for Raspberry Pi
3. 1 x Adafruit 1.2" 4-Digit 7-Segment Display w/I2C Backpack - Yellow. Product ID: 1269
4. 1 x Adafruit Quad Alphanumeric Display - Red 0.54" Digits w/ I2C Backpack - STEMMA QT / Qwiic. Product ID: 1911
4. 1 x Adafruit Rotary Encoder. Product ID: 377
5. 1 x HC-SR04 Ultrasonic Distance Sensor
6. 1 x Sparkfun Logic Level Converter - Bi-Directional. PN BOB-12009
7. 2 x Sparkfun Mini Pushbutton Switch. PN COM-00097
8. 1 x Adafruit T-Cobbler Plus. Product ID: 2028
9. 4 x 2P 0.1" Pitch PCB Mount Screw Terminal Block
10. 1 x 3P 0.1" Pitch PCB Mount Screw Terminal Block
11. 1 x BusBoard Prototype Systems Breadboard. PN BB830
12. Various jumper wires
13. iHome iM60LT Rechargeable Mini Speaker - Blue



