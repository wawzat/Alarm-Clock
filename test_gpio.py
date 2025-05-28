from gpiozero import Button

button = Button(12, pull_up=True)
print("Waiting for button press...")
button.wait_for_press()
print("Button pressed!")