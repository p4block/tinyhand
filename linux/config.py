"""Validated preferences; only explicit UI changes write to disk."""
import json
import math
import os
from pathlib import Path
import tempfile
import time

DEFAULT_PINS = ['lavender', 'glove', 'coral', 'plush', 'robot', 'laser']


class Config:
    def __init__(self, styles, path=None):
        self.styles = set(styles)
        self.path = Path(path) if path else Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'tinyhand/config.json'
        self.data = dict(version=1, style='lavender', pins=DEFAULT_PINS.copy(), size=.13,
                         hand_sound=True, laser_sound=False)
        self.error = None
        try:
            raw = json.loads(self.path.read_text())
            if not isinstance(raw, dict) or raw.get('version', 1) != 1:
                raise ValueError('unsupported preference format')
            self.data.update(self.validate(raw))
        except FileNotFoundError:
            pass
        except (ValueError, OSError) as error:
            self.error = f'Preferences could not be loaded: {error}'
            # Preserve the original for recovery before any future UI save.
            if isinstance(error, ValueError):
                try:
                    self.path.rename(self.path.with_name(f'config.broken-{time.time_ns()}.json'))
                except OSError:
                    pass

    def validate(self, raw):
        out = {}
        if isinstance(raw.get('style'), str) and raw['style'] in self.styles:
            out['style'] = raw['style']
        size = raw.get('size')
        if type(size) in (int, float) and math.isfinite(size) and .03 <= size <= .5:
            out['size'] = size
        for key in ('hand_sound', 'laser_sound'):
            if type(raw.get(key)) is bool:
                out[key] = raw[key]
        if isinstance(raw.get('pins'), list):
            pins = list(dict.fromkeys(x for x in raw['pins'] if isinstance(x, str) and x in self.styles))[:8]
            if pins:
                out['pins'] = pins
        return out

    def update(self, **changes):
        self.data.update(self.validate(changes))
        temp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, prefix='.config-', delete=False) as stream:
                temp = stream.name
                json.dump(self.data, stream, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            self.error = None
        except OSError as error:
            self.error = f'Preferences could not be saved: {error}'
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)
        return self.error
