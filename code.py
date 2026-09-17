"""Keybow lighting and key actions. Hardware imports are kept inside run()."""

import math
import time

# Settings: brightness values range from 0 (off) to 1 (full brightness).
BRIGHTNESS = 0.7
BACKGROUND_BRIGHTNESS = 0.10
EFFECT_DURATION = 3.0
FRAME_INTERVAL = 1 / 30
COLUMN_COLORS = (
    (50, 255, 50),   # Bulbasaur
    (255, 100, 0),   # Charmander
    (50, 50, 255),   # Squirtle
    (255, 255, 0),   # Pikachu
)


def clamp(value):
    return min(1.0, max(0.0, value))


def wave(phase):
    return (math.sin(phase) + 1) * 0.5


def position(number):
    # USB port at the top: keys run bottom-to-top within each column.
    return divmod(number, 4)


def smoothstep(value):
    value = clamp(value)
    return value * value * (3 - 2 * value)


def moss_arrival(column, row):
    """Small fixed delays give neighbouring patches uneven, repeatable growth."""
    distance = column + (3 - row)
    patch = (column * 3 + (3 - row) * 5) % 4
    return distance * 0.065 + patch * 0.008


# Each effect returns (RGB colour, intensity). Progress runs from 0 to 1.
# Lighting mixes effects with idle colours and fades all except the water pulse.
def leaf_effect(column, row, progress):
    # Moss grows from Bulbasaur (0, 3), then stays until the shared final fade.
    age = progress - moss_arrival(column, row)
    coverage = smoothstep(age / 0.18)
    maturity = smoothstep(age / 0.22)
    # Soft yellow-green tips settle into emerald rather than blinking on.
    color = (int(110 - 86 * maturity), int(190 - 25 * maturity),
             int(40 + 5 * maturity))
    # A low-contrast breeze drifts across established patches, slightly delayed
    # in each neighbour. The slower second sway keeps the motion organic.
    breeze = wave(progress * 7 - column * 0.65 - (3 - row) * 0.45)
    sway = wave(progress * 3.5 + column * 0.4 - row * 0.55)
    strength = coverage * (0.72 + maturity * (0.06 * breeze + 0.025 * sway))
    return color, strength


def fire_effect(column, row, progress):
    # A narrow jet travels down from Charmander (1, 3) to the bottom wall.
    wall_hit = 0.24
    sideways = abs(column - 1)
    if column == 1:
        arrival = (3 - row) * wall_hit / 3
    else:
        # On impact, fire runs along the wall before curling upwards.
        arrival = wall_hit + sideways * 0.07 + row * 0.075
    ignition = clamp((progress - arrival) / 0.055)

    # The jet's heat moves down; the spreading flames lick upwards.
    direction = row if column == 1 else -row
    flicker = wave(progress * 72 + direction * 2.4 + column * 1.7)
    heat = wave(progress * 45 + direction * 3.1 - column)
    core = 1.0 if column == 1 else 0.0
    # The impact point briefly flares hotter as the jet reaches the wall.
    impact = clamp(1 - abs(progress - (wall_hit + 0.055)) / 0.09)
    impact *= 1.0 if row == 0 and column == 1 else 0.0
    color = (255, int(40 + 125 * heat + 45 * core + 35 * impact),
             int(10 * heat + 35 * core + 45 * impact))
    strength = ignition * min(1.0, 0.45 + 0.4 * flicker + 0.1 * core + 0.15 * impact)
    return color, strength


def water_effect(column, row, progress):
    # One broad crest enters at the top right and exits at the bottom left.
    diagonal = (3 - column) + (3 - row)
    local_progress = progress - diagonal * 0.085
    # A finite pulse has smooth leading/trailing edges and no repeating waves.
    # The last key clears at 6 * 0.085 + 0.44 = 0.95 of the effect duration.
    width = 0.44
    if local_progress <= 0 or local_progress >= width:
        return (25, 160, 255), 0.0
    crest = math.sin(math.pi * local_progress / width) ** 2
    return (25, 160, 255), 0.8 * crest


# Unbranched paths, each starting at the top-right Pikachu cap (key 15).
# Consecutive keys share an edge. Only one path fires at a time.
LIGHTNING_PATHS = (
    (15, 11, 10, 6, 5, 1, 0),
    (15, 14, 10, 9, 5, 4, 0),
    (15, 14, 13, 9, 8, 4, 0),
)
LIGHTNING_TRAIL = 2.6  # Bright head plus up to two fading keys behind it.


def electric_effect(column, row, progress):
    strike = progress * len(LIGHTNING_PATHS)
    index = min(int(strike), len(LIGHTNING_PATHS) - 1)
    phase = strike - index
    path = LIGHTNING_PATHS[index]
    # Travel for most of each strike, then leave a dark gap before the next.
    head = phase / 0.78 * len(path)
    number = column * 4 + row
    strength = 0.0
    for step in range(len(path)):
        if path[step] == number:
            # One bright head and a short fading tail; no board-wide flash.
            behind = head - step
            if 0 <= behind < 1:
                strength = 1 - 0.3 * behind
            elif 1 <= behind < LIGHTNING_TRAIL:
                strength = 0.7 * (1 - (behind - 1) / (LIGHTNING_TRAIL - 1))
            break
    return (255, 245, 100), strength


COLUMN_EFFECTS = (leaf_effect, fire_effect, water_effect, electric_effect)


class Lighting:
    """Static column colours with one temporary effect across the whole keypad."""

    def __init__(self, keys, brightness=BRIGHTNESS,
                 background=BACKGROUND_BRIGHTNESS, duration=EFFECT_DURATION):
        if duration <= 0:
            raise ValueError("Effect duration must be positive")
        self.keys = keys
        self.brightness = clamp(brightness)
        self.background = clamp(background)
        self.duration = duration
        self.enabled = [True] * len(keys)
        self.last_colors = [None] * len(keys)
        self.effect = None
        self.started = 0.0
        self.next_frame = 0.0

    def toggle(self, number):
        self.enabled[number] = not self.enabled[number]

    def trigger(self, number, now):
        # A new press immediately replaces the previous effect; no queue.
        column, _ = position(number)
        self.effect = COLUMN_EFFECTS[column]
        self.started = now
        self.next_frame = now

    def stop(self):
        """Return to idle colours on the next frame."""
        self.effect = None
        self.next_frame = 0.0

    def update(self, now):
        if now < self.next_frame:
            return
        self.next_frame = now + FRAME_INTERVAL
        progress = clamp((now - self.started) / self.duration)
        if progress >= 1:
            self.effect = None
        # Water has its own travelling edges; let it clear the board naturally.
        envelope = 1.0
        if self.effect is not water_effect:
            envelope = clamp(progress / 0.025) * clamp((1 - progress) / 0.3)
        for key in self.keys:
            rgb = self.color_at(key.number, progress, envelope)
            # PMK retains key.rgb when off; cache the actual output ourselves.
            if self.last_colors[key.number] != rgb:
                key.set_led(*rgb)
                self.last_colors[key.number] = rgb

    def color_at(self, number, progress, envelope):
        """Mix a key's static column colour with the current effect."""
        column, row = position(number)
        color = COLUMN_COLORS[column]
        # The Pokemon caps are slightly brighter than the lower keys.
        background = self.background * (0.7 + row * 0.1)
        if not self.enabled[number]:
            background = 0.0
        red = color[0] * background
        green = color[1] * background
        blue = color[2] * background

        if self.effect is not None:
            color, strength = self.effect(column, row, progress)
            strength = clamp(strength * envelope)
            # Toggled-off keys still join the effect, then return to off.
            red = red * (1 - strength) + color[0] * strength
            green = green * (1 - strength) + color[1] * strength
            blue = blue * (1 - strength) + color[2] * strength

        # Explicit channels avoid generator closures on older CircuitPython.
        return (
            int(red * self.brightness),
            int(green * self.brightness),
            int(blue * self.brightness),
        )


def run():
    import usb_hid

    from pmk import PMK
    from pmk.platform.keybow2040 import Keybow2040 as Hardware
    from adafruit_hid.keyboard import Keyboard
    from adafruit_hid.keycode import Keycode
    from adafruit_hid.consumer_control import ConsumerControl
    from adafruit_hid.consumer_control_code import ConsumerControlCode

    keybow = PMK(Hardware())
    keyboard = Keyboard(usb_hid.devices)
    consumer_controls = ConsumerControl(usb_hid.devices)
    lighting = Lighting(keybow.keys)

    # Existing key assignments. All other keys toggle their background light.
    media_keys = {
        3: ConsumerControlCode.SCAN_PREVIOUS_TRACK,
        7: ConsumerControlCode.PLAY_PAUSE,
        11: ConsumerControlCode.PLAY_PAUSE,
        15: ConsumerControlCode.SCAN_NEXT_TRACK,
    }

    def on_press(key):
        number = key.number
        if number == 0:
            keyboard.send(Keycode.WINDOWS, Keycode.SHIFT, Keycode.M)
        elif number in media_keys:
            consumer_controls.send(media_keys[number])
        else:
            lighting.toggle(number)
        lighting.trigger(number, time.monotonic())

    for key in keybow.keys:
        keybow.on_press(key)(on_press)

    while True:
        keybow.update()
        lighting.update(time.monotonic())


if __name__ == "__main__":
    run()
