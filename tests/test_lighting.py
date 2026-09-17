"""Host-side checks; run with python3 -m unittest discover -s tests."""
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class Key:
    def __init__(self, number):
        self.number = number
        self.rgb = (0, 0, 0)
        self.output = (0, 0, 0)

    def set_led(self, *rgb):
        # Like PMK, retain the previous colour when switched off.
        if rgb != (0, 0, 0):
            self.rgb = rgb
        self.output = rgb


class StopLoop(Exception):
    pass


class Board:
    def __init__(self, hardware):
        self.keys = [Key(i) for i in range(16)]
        self.index = 0

    def on_press(self, key):
        def register(handler):
            key.handler = handler
        return register

    def update(self):
        if self.index == 16:
            raise StopLoop
        key = self.keys[self.index]
        key.handler(key)
        self.index += 1


class HID:
    events = []

    def __init__(self, devices):
        pass

    def send(self, *codes):
        self.events.append(codes)


def hardware_modules():
    codes = types.SimpleNamespace(**{name: name for name in (
        'WINDOWS', 'SHIFT', 'M', 'SCAN_PREVIOUS_TRACK', 'PLAY_PAUSE', 'SCAN_NEXT_TRACK')})
    modules = {}
    for name, attrs in {
        'pmk': {'PMK': Board},
        'pmk.platform.keybow2040': {'Keybow2040': object},
        'usb_hid': {'devices': []},
        'adafruit_hid.keyboard': {'Keyboard': HID},
        'adafruit_hid.keycode': {'Keycode': codes},
        'adafruit_hid.consumer_control': {'ConsumerControl': HID},
        'adafruit_hid.consumer_control_code': {'ConsumerControlCode': codes},
    }.items():
        modules[name] = types.ModuleType(name)
        modules[name].__dict__.update(attrs)
    return modules


CODE = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'code.py'))


class LightingTests(unittest.TestCase):
    def setUp(self):
        self.keys = [Key(i) for i in range(16)]
        self.lights = CODE['Lighting'](self.keys)
        self.lights.update(0)
        self.idle = self.pixels()

    def pixels(self):
        return tuple(key.output for key in self.keys)

    def test_idle_is_static(self):
        for now in (1, 30, 300):
            self.lights.update(now)
            self.assertEqual(self.pixels(), self.idle)

    def test_stop_returns_to_idle_immediately(self):
        self.lights.trigger(7, 1)
        self.lights.update(2)
        self.assertNotEqual(self.pixels(), self.idle)
        self.lights.stop()
        self.lights.update(2.001)
        self.assertEqual(self.pixels(), self.idle)

    def test_effects_cover_board_and_restore_idle(self):
        signatures = []
        for column in range(4):
            self.lights.trigger(column * 4, 10)
            changed = set()
            frames = []
            for frame in range(1, 60):
                self.lights.update(10 + frame * 0.05)
                pixels = self.pixels()
                frames.append(pixels)
                changed.update(i for i in range(16) if pixels[i] != self.idle[i])
                self.assertTrue(all(0 <= v <= 255 for rgb in pixels for v in rgb))
            if column == 3:
                expected = set().union(*CODE['LIGHTNING_PATHS'])
                self.assertEqual(changed, expected)
            else:
                self.assertEqual(changed, set(range(16)))
                if column == 2:
                    self.assertEqual(self.pixels(), self.idle)
                else:
                    self.assertNotEqual(self.pixels(), self.idle)
            self.lights.update(13.1)
            self.assertEqual(self.pixels(), self.idle)
            signatures.append(tuple(frames))
        self.assertEqual(len(set(signatures)), 4)

    def test_water_moves_from_top_right_to_bottom_left(self):
        effect = CODE['water_effect']
        for progress in (0.0, 0.12, 0.3):
            for column in range(1, 4):
                for row in range(1, 4):
                    # The same wave reaches the next left/down key later.
                    original = effect(column, row, progress)[1]
                    delay = 0.085
                    self.assertAlmostEqual(original, effect(column - 1, row, progress + delay)[1])
                    self.assertAlmostEqual(original, effect(column, row - 1, progress + delay)[1])

    def test_water_leading_edge_leaves_unreached_keys_at_idle(self):
        self.lights.trigger(11, 1)
        for progress in (0.02, 0.12, 0.3, 0.6):
            self.lights.update(1 + progress * self.lights.duration)
            changed = set()
            for number, pixel in enumerate(self.pixels()):
                column, row = divmod(number, 4)
                distance = (3 - column) + (3 - row)
                if progress <= distance * 0.085:
                    self.assertEqual(pixel, self.idle[number])
                if pixel != self.idle[number]:
                    changed.add(number)
            if progress == 0.02:
                self.assertEqual(changed, {15})
            if progress == 0.6:
                self.assertNotIn(15, changed)  # The trailing edge has passed.
                self.assertIn(0, changed)  # The leading edge reached the far corner.

    def test_water_changes_gently_between_frames(self):
        self.lights.trigger(11, 1)
        previous = self.pixels()
        largest_change = 0
        for frame in range(95):
            self.lights.update(1 + frame * 0.034)
            current = self.pixels()
            for before, after in zip(previous, current):
                largest_change = max(largest_change,
                                     max(abs(a - b) for a, b in zip(before, after)))
            previous = current
        # Include both travelling edges: no sudden jumps in any LED channel.
        self.assertLessEqual(largest_change, 14)

    def test_water_is_one_crest_and_finishes_without_global_fade(self):
        effect = CODE['water_effect']
        for number in range(16):
            column, row = divmod(number, 4)
            arrival = ((3 - column) + (3 - row)) * 0.085
            samples = [effect(column, row, arrival + i * 0.0044)[1]
                       for i in range(101)]
            self.assertEqual(samples[:51], sorted(samples[:51]))
            self.assertEqual(samples[50:], sorted(samples[50:], reverse=True))
            self.assertAlmostEqual(samples[50], 0.8)
            self.assertAlmostEqual(samples[-1], 0)
        self.lights.trigger(11, 1)
        # The far corner peaks late, but retains the full crest brightness.
        self.lights.update(1 + 0.73 * self.lights.duration)
        background_blue = CODE['COLUMN_COLORS'][0][2] * CODE['BACKGROUND_BRIGHTNESS'] * 0.7
        expected_blue = int((background_blue * 0.2 + 255 * 0.8) * CODE['BRIGHTNESS'])
        self.assertEqual(self.keys[0].output[2], expected_blue)
        self.lights.update(1 + 0.96 * self.lights.duration)
        self.assertEqual(self.pixels(), self.idle)

    def test_fire_and_moss_spread_from_their_pokemon(self):
        for name, origin in (('leaf_effect', 3), ('fire_effect', 7)):
            effect = CODE[name]
            previous = set()
            for progress in (0.02, 0.15, 0.3, 0.5, 0.68):
                reached = {n for n in range(16)
                           if effect(*divmod(n, 4), progress)[1] > 0}
                if progress == 0.02:
                    self.assertEqual(reached, {origin})
                self.assertTrue(previous.issubset(reached))
                previous = reached
            self.assertEqual(previous, set(range(16)))
            # Halfway through the spread, the far corner is still untouched.
            self.assertEqual(effect(3, 0, 0.3)[1], 0)

    def test_moss_takes_over_and_fire_keeps_flickering(self):
        for number in range(16):
            column, row = divmod(number, 4)
            color, strength = CODE['leaf_effect'](column, row, 0.68)
            self.assertGreaterEqual(strength, 0.72)
            self.assertLessEqual(strength, 0.805)
            self.assertEqual(color, (24, 165, 45))
        self.lights.trigger(3, 1)
        self.lights.update(3.04)  # Entire board is moss green before fading.
        for red, green, blue in self.pixels():
            self.assertGreater(green, red * 3)
            self.assertGreater(green, blue * 3)
        flames = [CODE['fire_effect'](1, 3, p)[1] for p in (0.2, 0.3, 0.4)]
        self.assertGreater(max(flames) - min(flames), 0.1)

    def test_moss_matures_and_sways_gently(self):
        effect = CODE['leaf_effect']
        # Equally distant patches grow at slightly different times.
        self.assertNotEqual(CODE['moss_arrival'](1, 3), CODE['moss_arrival'](0, 2))
        fresh, _ = effect(0, 3, 0.04)
        mature, _ = effect(0, 3, 0.4)
        self.assertGreater(fresh[0], mature[0])
        self.assertGreater(fresh[1], mature[1])
        strengths = [effect(0, 3, p / 100)[1] for p in range(30, 70)]
        self.assertGreater(max(strengths) - min(strengths), 0.01)
        self.assertLess(max(strengths) - min(strengths), 0.085)
        self.lights.trigger(3, 1)
        previous = self.pixels()
        largest_change = 0
        for frame in range(95):
            self.lights.update(1 + frame * 0.034)
            current = self.pixels()
            largest_change = max(largest_change, max(
                abs(a - b) for old, new in zip(previous, current)
                for a, b in zip(old, new)))
            previous = current
        self.assertLessEqual(largest_change, 10)

    def test_flamethrower_hits_wall_then_spreads_upwards(self):
        effect = CODE['fire_effect']

        def burning(progress):
            return {(column, row) for column in range(4) for row in range(4)
                    if effect(column, row, progress)[1] > 0}

        self.assertEqual(burning(0.02), {(1, 3)})
        self.assertEqual(burning(0.20), {(1, 3), (1, 2), (1, 1)})
        self.assertEqual(burning(0.28), {(1, row) for row in range(4)})
        self.assertEqual(burning(0.34), {(1, row) for row in range(4)} | {(0, 0), (2, 0)})
        self.assertIn((3, 0), burning(0.42))
        self.assertIn((2, 1), burning(0.42))
        self.assertNotIn((2, 2), burning(0.42))
        self.assertNotIn((3, 3), burning(0.55))
        self.assertEqual(len(burning(0.68)), 16)

    def test_lightning_is_a_single_bolt_from_pikachu(self):
        effect = CODE['electric_effect']
        paths = CODE['LIGHTNING_PATHS']
        for index, path in enumerate(paths):
            self.assertEqual(path[0], 15)
            for a, b in zip(path, path[1:]):
                ax, ay = divmod(a, 4)
                bx, by = divmod(b, 4)
                self.assertEqual(abs(ax - bx) + abs(ay - by), 1)
            start = index / len(paths) + 0.001
            lit = [n for n in range(16) if effect(*divmod(n, 4), start)[1] > 0]
            self.assertEqual(lit, [15])
            for frame in range(100):
                progress = (index + frame / 100) / len(paths)
                lit = [n for n in range(16) if effect(*divmod(n, 4), progress)[1] > 0]
                self.assertLessEqual(len(lit), 3)
                self.assertTrue(set(lit).issubset(path))
                steps = sorted(path.index(n) for n in lit)
                if steps:
                    self.assertEqual(steps, list(range(steps[0], steps[-1] + 1)))
            # A visible tail follows the head, with brightness falling backwards.
            progress = (index + 2.2 / len(path) * 0.78) / len(paths)
            tail = [effect(*divmod(n, 4), progress)[1] for n in path[:3]]
            self.assertGreater(tail[0], 0)
            self.assertLess(tail[0], tail[1])
            self.assertLess(tail[1], tail[2])
            gap = (index + 0.99) / len(paths)
            self.assertTrue(all(effect(*divmod(n, 4), gap)[1] == 0 for n in range(16)))

    def test_toggle_survives_effect_and_can_turn_back_on(self):
        self.lights.toggle(1)
        self.lights.update(1)
        self.assertEqual(self.keys[1].output, (0, 0, 0))
        self.lights.trigger(8, 2)
        self.lights.update(3.8)  # Allow the leading water wave to reach key 1.
        self.assertNotEqual(self.keys[1].output, (0, 0, 0))
        self.lights.update(5.1)
        self.assertEqual(self.keys[1].output, (0, 0, 0))
        self.lights.toggle(1)
        self.lights.update(6)
        self.assertEqual(self.keys[1].output, self.idle[1])

    def test_new_press_replaces_effect_and_resets_duration(self):
        self.lights.trigger(0, 1)
        self.lights.trigger(12, 2)
        self.assertIs(self.lights.effect, CODE['electric_effect'])
        self.lights.update(4.5)
        self.assertIsNotNone(self.lights.effect)
        self.lights.update(5.1)
        self.assertIsNone(self.lights.effect)

    def test_all_key_assignments(self):
        HID.events = []
        with patch.dict(sys.modules, hardware_modules()), self.assertRaises(StopLoop):
            CODE['run']()
        self.assertEqual(HID.events, [
            ('WINDOWS', 'SHIFT', 'M'), ('SCAN_PREVIOUS_TRACK',),
            ('PLAY_PAUSE',), ('PLAY_PAUSE',), ('SCAN_NEXT_TRACK',),
        ])


if __name__ == '__main__':
    unittest.main()
