#!/usr/bin/env python3
"""Preview the real Keybow lighting code in a true-colour terminal (Linux/macOS)."""
from contextlib import contextmanager
from pathlib import Path
import runpy
import select
import sys
import time

FIRMWARE = runpy.run_path(str(Path(__file__).with_name('code.py')))
EFFECTS = ('grass', 'fire', 'water', 'lightning')
RESET = '\033[0m'


class PreviewKey:
    def __init__(self, number):
        self.number = number
        self.rgb = (0, 0, 0)

    def set_led(self, red, green, blue):
        self.rgb = (red, green, blue)


def render(keys, status):
    lines = ['Keybow 2040 | USB at top',
             ' Bulbasaur  Charmander  Squirtle    Pikachu', '']
    for row in range(3, -1, -1):
        cells = []
        for column in range(4):
            key = keys[column * 4 + row]
            red, green, blue = key.rgb
            ink = 0 if max(key.rgb) > 130 else 255
            cells.append(f'\033[48;2;{red};{green};{blue}m'
                         f'\033[38;2;{ink};{ink};{ink}m'
                         f'    {key.number:02d}    {RESET}')
        line = ' '.join(cells)
        lines.extend((line, ''))
    lines.extend((f'Effect: {status}',
                  '1 grass  2 fire  3 water  4 lightning',
                  'Space: idle   q: quit'))
    return '\033[H' + '\n'.join(line + '\033[K' for line in lines) + '\033[J'


@contextmanager
def terminal():
    import termios
    import tty
    fd = sys.stdin.fileno()
    original = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write('\033[?1049h\033[?25l')
        sys.stdout.flush()
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, original)
        sys.stdout.write(RESET + '\033[?25h\033[?1049l')
        sys.stdout.flush()


def main():
    if len(sys.argv) != 1:
        sys.exit('Usage: python3 preview.py (press 1-4 to select an effect)')
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        sys.exit('Run in an interactive terminal with true-colour support.')

    keys = [PreviewKey(i) for i in range(16)]
    lighting = FIRMWARE['Lighting'](keys)
    status = 'idle'
    try:
        with terminal():
            while True:
                now = time.monotonic()
                if select.select([sys.stdin], [], [], 0)[0]:
                    command = sys.stdin.read(1).lower()
                    if command in ('q', '\x1b', ''):
                        break
                    if command in '1234':
                        column = int(command) - 1
                        lighting.trigger(column * 4 + 3, now)
                        status = EFFECTS[column]
                    elif command == ' ':
                        lighting.stop()

                lighting.update(now)
                if lighting.effect is None:
                    status = 'idle'
                sys.stdout.write(render(keys, status))
                sys.stdout.flush()
                time.sleep(FIRMWARE['FRAME_INTERVAL'])
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
