from pmk import PMK
from pmk.platform.keybow2040 import Keybow2040 as Hardware

import usb_hid
from adafruit_hid.consumer_control import ConsumerControl

keybow = PMK(Hardware()) 
keys = keybow.keys

# https://www.usb.org/sites/default/files/documents/hut1_12v2.pdf#page=75
# https://docs.circuitpython.org/projects/hid/en/latest/_modules/adafruit_hid/consumer_control.html
consumer_controls = ConsumerControl(usb_hid.devices)

rgb = (0, 255, 255)

for key in keys:
    key.rgb = (255, 0, 255)

    # https://github.com/pimoroni/pmk-circuitpython/blob/main/examples/decorator-key-test.py
    @keybow.on_press(key)
    def hold_handler(key):
        if (key.number < 8):
            consumer_controls.send(182)
        else:
            consumer_controls.send(181)
        key.toggle_led()

while True:
    keybow.update()
