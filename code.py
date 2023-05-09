from pmk import PMK
from pmk.platform.keybow2040 import Keybow2040 as Hardware

import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.consumer_control_code import ConsumerControlCode

keybow = PMK(Hardware())
keys = keybow.keys

keyboard = Keyboard(usb_hid.devices)
# https://www.usb.org/sites/default/files/documents/hut1_12v2.pdf#page=75
# https://docs.circuitpython.org/projects/hid/en/latest/_modules/adafruit_hid/consumer_control.html
consumer_controls = ConsumerControl(usb_hid.devices)

bulbasaur_green = (50, 255, 50)
charmander_red = (255, 100, 0)
squirtle_blue = (50, 50, 255)
pikachu_yellow = (255, 255, 0)


class CustomKey:
    def __init__(self, color, press_handler):
        self.color = color
        self.press_handler = press_handler


class Unassigned(CustomKey):
    def __init__(self, col=(255, 0, 255), dim=1):
        super().__init__([int(dim * x) for x in col], lambda key: key.toggle_led())


custom_keys = [
    CustomKey(
        (255, 0, 0),
        lambda key: keyboard.send(Keycode.WINDOWS, Keycode.SHIFT, Keycode.M),
    ),
    Unassigned(bulbasaur_green, 0.1),
    Unassigned(bulbasaur_green, 0.5),
    CustomKey(
        bulbasaur_green,
        lambda key: consumer_controls.send(ConsumerControlCode.SCAN_PREVIOUS_TRACK),
    ),
    Unassigned(charmander_red, 0),
    Unassigned(charmander_red, 0.1),
    Unassigned(charmander_red, 0.5),
    CustomKey(
        charmander_red,
        lambda key: consumer_controls.send(ConsumerControlCode.PLAY_PAUSE),
    ),
    Unassigned(squirtle_blue, 0),
    Unassigned(squirtle_blue, 0.1),
    Unassigned(squirtle_blue, 0.5),
    CustomKey(
        squirtle_blue,
        lambda key: consumer_controls.send(ConsumerControlCode.PLAY_PAUSE),
    ),
    Unassigned(pikachu_yellow, 0),
    Unassigned(pikachu_yellow, 0.1),
    Unassigned(pikachu_yellow, 0.5),
    CustomKey(
        pikachu_yellow,
        lambda key: consumer_controls.send(ConsumerControlCode.SCAN_NEXT_TRACK),
    ),
]

for key in keys:
    current_key = custom_keys[key.number]
    key.rgb = current_key.color
    key.led_on()

    # https://github.com/pimoroni/pmk-circuitpython/blob/main/examples/decorator-key-test.py
    @keybow.on_press(key)
    def hold_handler(key):
        custom_keys[key.number].press_handler(key)


while True:
    keybow.update()
