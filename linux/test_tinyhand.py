"""Headless checks of every bundled asset and hand-tip positioning."""
import sys
import unittest

import cairo
from tinyhand import ASSETS, Hand


class RenderingTests(unittest.TestCase):
    def test_assets_and_tip_alignment(self):
        for path in ASSETS.glob('hand_*.png'):
            with self.subTest(hand=path.stem):
                hand = Hand(path.stem[5:])
                self.assertLess(hand.top, hand.wrist)
                self.assertLess(hand.wrist, hand.end)
                # At normal reach, the actual fingertip should map to target.
                for x, y in ((200, 100), (640, 360), (1100, 500)):
                    target = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1280, 720)
                    cr = cairo.Context(target)
                    hand.paint(cr, x, y, 1280, 720, .13)
                    target.flush()
                    pixels, stride = target.get_data(), target.get_stride()
                    # The measured tip is an opaque pixel; allow for interpolation.
                    alpha = 3 if sys.byteorder == 'little' else 0
                    nearby = [pixels[py * stride + px * 4 + alpha]
                              for py in range(y - 4, y + 5)
                              for px in range(x - 4, x + 5)]
                    self.assertGreater(max(nearby), 20)


if __name__ == '__main__':
    unittest.main()
