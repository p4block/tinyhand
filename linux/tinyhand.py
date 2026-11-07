#!/usr/bin/env python3
"""TinyHand presentation overlay for layer-shell Wayland compositors."""
import argparse
import ctypes
import time
import fcntl
import math
import os
from pathlib import Path
import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict

from config import Config, SOUNDS
from styles import STYLES, ink_color

# Layer-shell must load before GTK links libwayland (upstream requirement).
ctypes.CDLL('libgtk4-layer-shell.so.0')
import cairo
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Graphene', '1.0')
gi.require_version('GLibUnix', '2.0')
from gi.repository import Gdk, GLib, Gtk, Graphene, GLibUnix

from toolbar import Toolbar

ASSETS = Path(__file__).resolve().parent.parent / 'assets'


class Hand:
    def __init__(self, name):
        self.name = name
        self.image = cairo.ImageSurface.create_from_png(str(ASSETS / f'hand_{name}.png'))
        p = self.image
        w, h, stride = p.get_width(), p.get_height(), p.get_stride()
        pixels = p.get_data()
        alpha = 3 if sys.byteorder == 'little' else 0
        rows = [[x for x in range(w) if pixels[y * stride + x * 4 + alpha] > 128]
                for y in range(h)]
        counts = [len(row) for row in rows]
        top = next(y for y, n in enumerate(counts) if n)
        widest = max(counts[top:min(h, top + int(.45 * h))])
        fist = next(y for y in range(top, h) if counts[y] > .6 * widest)
        self.wrist = next(y for y in range(fist, h) if counts[y] < .35 * widest)
        rod_width = counts[min(h - 1, self.wrist + h // 50)]
        self.end = next((y for y in range(min(h - 1, self.wrist + h // 33), h)
                         if counts[y] > 1.8 * rod_width), max(y for y, n in enumerate(counts) if n))
        def center(y):
            return (rows[y][0] + rows[y][-1]) / 2 if rows[y] else w / 2
        self.tip_y = top
        self.tip_x = center(min(h - 1, top + h // 200))
        self.rod_x = center((self.wrist + self.end) // 2)
        self.top = max(0, top - .004 * h)

    def pose(self, x, y, width, height, size, press=0, grip=None):
        # Local coordinates: rod root at origin, hand points up along negative Y.
        scale = size * height * (1 - .06 * press) / (self.wrist - self.top)
        gx = min(max(x + .30 * width, .15 * width), 1.05 * width) if grip is None else grip
        gy = 1.12 * height
        reach = math.hypot(x - gx, y - gy)
        offset = (self.tip_x - self.rod_x) * scale
        along = math.sqrt(max(0, reach * reach - offset * offset))
        rod = max(.05 * height, along - (self.wrist - self.tip_y) * scale)
        angle = math.atan2(y - gy, x - gx) - math.atan2(-rod - (self.wrist - self.tip_y) * scale, offset)
        return scale, gx, gy, rod, angle

    def paint(self, cr, x, y, width, height, size, press=0, grip=None):
        # Headless reference renderer; the live overlay uses GPU textures below.
        scale, gx, gy, rod, angle = self.pose(x, y, width, height, size, press, grip)
        cr.save()
        cr.translate(gx, gy)
        cr.rotate(angle)
        iw = self.image.get_width() * scale
        def piece(src_top, src_bottom, dest_y, dest_height):
            cr.save()
            cr.rectangle(-self.rod_x * scale, dest_y, iw, dest_height)
            cr.clip()
            cr.translate(-self.rod_x * scale, dest_y)
            cr.scale(scale, dest_height / (src_bottom - src_top))
            cr.set_source_surface(self.image, 0, -src_top)
            cr.paint()
            cr.restore()
        piece(self.wrist, self.end, -rod, rod)
        piece(self.top, self.wrist, -rod - (self.wrist - self.top) * scale,
              (self.wrist - self.top) * scale)
        cr.restore()
        return gx

    def textures(self):
        def crop(top, bottom):
            top, bottom = int(top), int(bottom)
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.image.get_width(), bottom - top)
            cr = cairo.Context(surface)
            cr.set_source_surface(self.image, 0, -top)
            cr.paint()
            surface.flush()
            fmt = (Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED if sys.byteorder == 'little'
                   else Gdk.MemoryFormat.A8R8G8B8_PREMULTIPLIED)
            return Gdk.MemoryTexture.new(surface.get_width(), surface.get_height(), fmt,
                                         GLib.Bytes.new(bytes(surface.get_data())), surface.get_stride())
        return crop(self.top, self.wrist), crop(self.wrist, self.end)


def rect(x, y, w, h):
    return Graphene.Rect().init(x, y, w, h)


class TapSound:
    """Let the audio server cache the sample; no process spawning per click."""
    def __init__(self, enabled=True):
        self.context = ctypes.c_void_p()
        self.lib = None
        if not enabled:
            return
        try:
            self.lib = ctypes.CDLL('libcanberra.so.0')
            self.lib.ca_context_create.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
            for name in ('ca_context_cache', 'ca_context_play'):
                getattr(self.lib, name).restype = ctypes.c_int
            self.lib.ca_context_destroy.argtypes = [ctypes.c_void_p]
            if self.lib.ca_context_create(ctypes.byref(self.context)) < 0:
                raise RuntimeError('cannot create audio context')
            self.samples = {}
            for choice in SOUNDS:
                props = (ctypes.c_char_p(b'event.id'), ctypes.c_char_p(f'tinyhand-tap-{choice}'.encode()),
                         ctypes.c_char_p(b'media.filename'),
                         ctypes.c_char_p(os.fsencode(ASSETS / f'sounds/tap_{choice}.wav')),
                         ctypes.c_char_p(b'canberra.cache-control'), ctypes.c_char_p(b'permanent'),
                         ctypes.c_void_p())
                result = self.lib.ca_context_cache(self.context, *props)
                if result < 0:
                    raise RuntimeError(f'{choice}: audio cache error {result}')
                self.samples[choice] = props
        except (OSError, RuntimeError) as error:
            print(f'Tap audio unavailable: {error}', file=sys.stderr)
            self.close()

    def play(self, choice='thock'):
        if self.lib and self.context:
            result = self.lib.ca_context_play(self.context, ctypes.c_uint32(0), *self.samples[choice])
            if result < 0:
                print(f'Tap audio playback error {result}', file=sys.stderr)

    def close(self):
        if self.lib and self.context:
            self.lib.ca_context_destroy(self.context)
            self.context = ctypes.c_void_p()
        self.lib = None


class Canvas(Gtk.Widget):
    def __init__(self, overlay):
        super().__init__()
        self.overlay = overlay
        self.ink_node = None
        self.ink_dirty = True
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_cursor_from_name('none')
        self.set_focusable(True)

    def do_snapshot(self, snapshot):
        win = self.overlay
        width, height = self.get_width(), self.get_height()
        # Even before pointer enter, submit a nonempty render tree so Wayland
        # maps the surface and starts delivering pointer events. No visible pixel.
        snapshot.append_texture(win.app.transparent_texture, rect(0, 0, 1, 1))
        if self.ink_dirty:
            ink = Gtk.Snapshot.new()
            if any(len(stroke) > 1 for stroke in win.strokes):
                cr = ink.append_cairo(rect(0, 0, width, height))
                cr.set_line_width(max(3, height * .0055))
                cr.set_line_cap(cairo.LINE_CAP_ROUND)
                cr.set_line_join(cairo.LINE_JOIN_ROUND)
                for index, stroke in enumerate(win.strokes):
                    color = win.stroke_colors[index] if index < len(win.stroke_colors) else win.app.color
                    cr.set_source_rgba(*color, .9)
                    if len(stroke) > 1:
                        cr.move_to(*stroke[0])
                        for point in stroke[1:]:
                            cr.line_to(*point)
                        cr.stroke()
                del cr
            self.ink_node = ink.to_node()
            self.ink_dirty = False
        if self.ink_node:
            snapshot.append_node(self.ink_node)
        if win.point and win.app.style == 'laser':
            radius = max(4, height * .0038 * win.app.size / .13) * (1 + .2 * win.press)
            x, y = win.point
            snapshot.append_texture(win.app.laser_texture, rect(x - radius * 4, y - radius * 4,
                                                               radius * 8, radius * 8))
        elif win.point:
            hand = win.app.hand
            scale, gx, gy, rod, angle = hand.pose(*win.point, width, height,
                                                 win.app.size, win.press, win.grip)
            snapshot.save()
            snapshot.translate(Graphene.Point().init(gx, gy))
            snapshot.rotate(math.degrees(angle))
            left, iw = -hand.rod_x * scale, hand.image.get_width() * scale
            hh = (hand.wrist - hand.top) * scale
            snapshot.append_texture(win.app.rod_texture, rect(left, -rod, iw, rod))
            snapshot.append_texture(win.app.hand_texture, rect(left, -rod - hh, iw, hh))
            snapshot.restore()
        if win.app.benchmark:
            win.frames.append(time.monotonic())


class Overlay(Gtk.Window):
    def __init__(self, app, monitor, layer):
        super().__init__()
        self.app = app
        self.point = None
        self.grip = None
        self.press = 0
        self.held = False
        self.strokes = []
        self.stroke_colors = []
        self.frames = []
        self.tick_id = 0
        self.last_tick = None
        self.set_title('TinyHand')
        self.set_decorated(False)
        layer.init_for_window(self)
        layer.set_namespace(self, 'tinyhand')
        layer.set_monitor(self, monitor)
        layer.set_layer(self, layer.Layer.OVERLAY)
        layer.set_exclusive_zone(self, -1)
        for edge in (layer.Edge.TOP, layer.Edge.BOTTOM, layer.Edge.LEFT, layer.Edge.RIGHT):
            layer.set_anchor(self, edge, True)
        layer.set_keyboard_mode(self, layer.KeyboardMode.EXCLUSIVE)
        self.canvas = Canvas(self)
        self.root = Gtk.Overlay()
        self.root.set_child(self.canvas)
        self.set_child(self.root)
        self.toolbar_hover = False
        self.toolbar = Toolbar(self)
        hover = Gtk.EventControllerMotion.new()
        hover.connect('enter', lambda *_: setattr(self, 'toolbar_hover', True))
        hover.connect('leave', lambda *_: setattr(self, 'toolbar_hover', False))
        self.toolbar.add_controller(hover)
        self.revealer = Gtk.Revealer(transition_type=Gtk.RevealerTransitionType.CROSSFADE,
                                    transition_duration=120)
        self.revealer.set_halign(Gtk.Align.CENTER)
        self.revealer.set_valign(Gtk.Align.END)
        self.revealer.set_child(self.toolbar)
        self.root.add_overlay(self.revealer)
        self.hide_timer = 0
        self.reveal_until = time.monotonic() + 2.5
        self.revealer.set_reveal_child(not app.benchmark)
        root_motion = Gtk.EventControllerMotion.new()
        root_motion.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        root_motion.connect('motion', self.track_toolbar)
        root_motion.connect('enter', self.track_toolbar)
        self.root.add_controller(root_motion)
        self.hide_timer = GLib.timeout_add(2600, self.initial_hide)
        self.connect('destroy', self.cleanup)
        motion = Gtk.EventControllerMotion.new()
        motion.connect('motion', self.motion)
        motion.connect('enter', self.motion)
        motion.connect('leave', self.leave)
        self.canvas.add_controller(motion)
        click = Gtk.GestureClick.new()
        click.set_button(0)
        click.connect('pressed', self.button)
        click.connect('released', self.release)
        self.canvas.add_controller(click)
        keys = Gtk.EventControllerKey.new()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key)
        self.add_controller(keys)
        self.connect('close-request', lambda *_: (app.quit(), True)[1])
        self.present()
        if app.benchmark:
            self.wake()

    def cleanup(self, *_):
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = 0
        if self.tick_id:
            self.canvas.remove_tick_callback(self.tick_id)
            self.tick_id = 0
        self.toolbar.menu.popdown()
        self.toolbar.sound_menu.popdown()

    def track_toolbar(self, _, x, y):
        if self.app.benchmark:
            return
        near = y > self.canvas.get_height() - 110
        if near and not self.held:
            self.revealer.set_reveal_child(True)
        elif time.monotonic() > self.reveal_until:
            self.hide_toolbar()

    def initial_hide(self):
        self.hide_timer = 0
        return self.hide_toolbar()

    def hide_toolbar(self):
        focus = self.get_focus()
        focused = focus and (focus == self.toolbar or focus.is_ancestor(self.toolbar))
        if not self.toolbar.menu.get_active() and not self.toolbar.sound_menu.get_active() and not focused:
            # Pointer within the toolbar retains controls, even after startup.
            if not self.toolbar_hover:
                self.revealer.set_reveal_child(False)
        return False

    def wake(self):
        if not self.tick_id:
            self.last_tick = None
            self.tick_id = self.canvas.add_tick_callback(self.tick)

    def motion(self, _, x, y):
        self.point = (x, y)
        if self.held:
            self.strokes[-1].append(self.point)
            self.canvas.ink_dirty = True
        self.canvas.queue_draw()
        self.wake()

    def button(self, gesture, _count, x, y):
        self.canvas.grab_focus()
        self.point = (x, y)
        self.press = 1
        if self.app.sound_enabled():
            self.app.sound.play(self.app.config.data['tap_sound'])
        if gesture.get_current_button() == 1 and not self.held:
            self.held = True
            self.strokes.append([self.point])
            self.stroke_colors.append(self.app.color)
            self.revealer.set_reveal_child(False)
        self.canvas.queue_draw()
        self.wake()

    def release(self, *_):
        self.held = False
        self.wake()

    def leave(self, *_):
        self.point = None
        self.held = False
        self.grip = None
        self.canvas.queue_draw()

    def key(self, _, keyval, _keycode, _state):
        if self.toolbar.menu.get_active() or self.toolbar.sound_menu.get_active():
            if keyval == Gdk.KEY_Escape:
                self.toolbar.menu.popdown()
                self.toolbar.sound_menu.popdown()
                return True
            return False
        if keyval == Gdk.KEY_Escape:
            self.app.quit()
            return True
        if keyval in (Gdk.KEY_c, Gdk.KEY_C, Gdk.KEY_x, Gdk.KEY_X):
            self.app.clear()
            return True
        return False

    def tick(self, _, clock):
        now = clock.get_frame_time()
        dt = min(.1, (now - self.last_tick) / 1e6) if self.last_tick else 1 / 240
        self.last_tick = now
        dirty = False
        if self.app.benchmark:
            t = (now - self.app.started) / 1e6
            self.point = (self.canvas.get_width() * (.5 + .3 * math.sin(t * 2)),
                          self.canvas.get_height() * (.45 + .3 * math.cos(t * 3)))
            dirty = True
        if not self.held and self.press > .002:
            self.press *= math.exp(-11.9 * dt)
            dirty = True
        if self.point:
            width = self.canvas.get_width()
            target = min(max(self.point[0] + .30 * width, .15 * width), 1.05 * width)
            if self.grip is None:
                self.grip = target
            if abs(target - self.grip) > .1:
                self.grip += (target - self.grip) * (1 - math.exp(-5 * dt))
                dirty = True
        if dirty:
            self.canvas.queue_draw()
            return True
        self.tick_id = 0
        return False


class App:
    def __init__(self, hand, size, layer, sound, benchmark, config=None, style=None, mute=False):
        self.config = config or Config(STYLES)
        self.style = style or hand.name
        self.color = ink_color(self.style)
        self.session_mute = mute
        self.hand, self.size, self.layer = hand, size, layer
        self.style_cache = OrderedDict()
        self.thumb_cache = {}
        self.thumb_pending = {}
        self.workers = ThreadPoolExecutor(max_workers=1, thread_name_prefix='tinyhand-thumbnail')
        self.sound, self.benchmark = sound, benchmark
        self.hand_texture, self.rod_texture = hand.textures()
        self.style_cache[hand.name] = (hand, self.hand_texture, self.rod_texture)
        laser = cairo.ImageSurface(cairo.FORMAT_ARGB32, 96, 96)
        cr = cairo.Context(laser)
        glow = cairo.RadialGradient(48, 48, 0, 48, 48, 48)
        for stop, rgba in ((0, (1, .9, .85, 1)), (.10, (1, .3, .2, 1)),
                           (.25, (1, .05, .02, .9)), (.5, (1, 0, 0, .25)), (1, (1, 0, 0, 0))):
            glow.add_color_stop_rgba(stop, *rgba)
        cr.set_source(glow)
        cr.paint()
        self.laser_texture = self.texture(laser)
        self.transparent_texture = Gdk.MemoryTexture.new(
            1, 1, Gdk.MemoryFormat.R8G8B8A8_PREMULTIPLIED,
            GLib.Bytes.new(bytes(4)), 4)
        self.started = GLib.get_monotonic_time()
        self.cpu_started = time.process_time()
        self.loop = GLib.MainLoop()
        self.windows = []
        self.display = Gdk.Display.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_data(b'''
            window { background: transparent; }
            .tinyhand-toolbar { background: rgba(30, 28, 38, .96); color: white;
                border-radius: 18px; padding: 8px; border: 1px solid rgba(255,255,255,.15); }
            .tinyhand-toolbar button { border-radius: 11px; min-width: 30px; }
            popover contents { padding: 10px; }
        ''')
        Gtk.StyleContext.add_provider_for_display(self.display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.monitors = self.display.get_monitors()
        self.rebuild()
        self.monitors.connect('items-changed', self.rebuild)

    @staticmethod
    def texture(surface):
        surface.flush()
        fmt = (Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED if sys.byteorder == 'little'
               else Gdk.MemoryFormat.A8R8G8B8_PREMULTIPLIED)
        return Gdk.MemoryTexture.new(surface.get_width(), surface.get_height(), fmt,
                                    GLib.Bytes.new(bytes(surface.get_data())), surface.get_stride())

    def thumbnail(self, style, image):
        if style == 'laser':
            image.set_from_paintable(self.laser_texture)
        elif style in self.thumb_cache:
            image.set_from_paintable(self.thumb_cache[style])
        else:
            image.set_from_icon_name('image-loading-symbolic')
            self.thumb_pending.setdefault(style, []).append(image)
            if len(self.thumb_pending[style]) == 1:
                def build():
                    source = cairo.ImageSurface.create_from_png(str(ASSETS / f'hand_{style}.png'))
                    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 80, 80)
                    cr = cairo.Context(surface)
                    height = source.get_height() * .46
                    scale = min(76 / source.get_width(), 76 / height)
                    cr.translate((80 - source.get_width() * scale) / 2, 0)
                    cr.scale(scale, scale)
                    cr.set_source_surface(source, 0, 0)
                    cr.paint()
                    return surface
                def ready(future):
                    GLib.idle_add(self.thumbnail_ready, style, future)
                self.workers.submit(build).add_done_callback(ready)

    def thumbnail_ready(self, style, future):
        waiting = self.thumb_pending.pop(style, [])
        try:
            texture = self.texture(future.result())
            self.thumb_cache[style] = texture
            for image in waiting:
                image.set_from_paintable(texture)
        except Exception as error:
            print(f'Thumbnail {style}: {error}', file=sys.stderr)
        return False

    def save(self, **changes):
        error = self.config.update(**changes)
        if error:
            print(error, file=sys.stderr)
            for win in self.windows:
                win.toolbar.set_tooltip_text(error)

    def sound_enabled(self):
        key = 'laser_sound' if self.style == 'laser' else 'hand_sound'
        return not self.session_mute and self.config.data[key]

    def pick_sound(self, choice):
        if choice not in SOUNDS:
            return
        self.save(tap_sound=choice)
        self.set_sound_enabled(True)
        self.sound.play(choice)

    def toggle_sound(self):
        self.set_sound_enabled(not self.sound_enabled())

    def set_sound_enabled(self, enabled):
        self.session_mute = False
        self.save(**{('laser_sound' if self.style == 'laser' else 'hand_sound'): enabled})
        for win in self.windows:
            win.toolbar.refresh()

    def pick(self, style):
        if style not in STYLES:
            return
        if style != 'laser':
            if style not in self.style_cache:
                hand = Hand(style)
                self.style_cache[style] = (hand, *hand.textures())
            self.style_cache.move_to_end(style)
            self.hand, self.hand_texture, self.rod_texture = self.style_cache[style]
            while len(self.style_cache) > 2:
                self.style_cache.popitem(last=False)
        self.style = style
        self.color = ink_color(style)
        self.save(style=style)
        for win in self.windows:
            win.held = False
            win.press = 0
            win.toolbar.refresh()
            win.canvas.queue_draw()

    def clear(self):
        for win in self.windows:
            win.strokes.clear()
            win.stroke_colors.clear()
            win.held = False
            win.canvas.ink_dirty = True
            win.canvas.queue_draw()
            win.wake()

    def rebuild(self, *_):
        for win in self.windows:
            win.destroy()
        self.windows = [Overlay(self, self.monitors.get_item(i), self.layer)
                        for i in range(self.monitors.get_n_items())]

    def quit(self):
        self.workers.shutdown(wait=False, cancel_futures=True)
        self.loop.quit()
        return False

    def report(self):
        seconds = (GLib.get_monotonic_time() - self.started) / 1e6
        print(f'CPU: {100 * (time.process_time() - self.cpu_started) / max(.001, seconds):.1f}% of one core')
        for win in self.windows:
            frames = win.frames
            if len(frames) > 2:
                # Exclude first second (GPU pipeline warmup).
                frames = [t for t in frames if t >= frames[0] + 1] or frames
                if len(frames) > 1:
                    print(f'Output: {(len(frames) - 1) / (frames[-1] - frames[0]):.1f} rendered frames/s')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hand', choices=list(STYLES))
    parser.add_argument('--size', type=float, help='hand height as screen fraction (0.03–0.5)')
    parser.add_argument('--timeout', type=int, default=0, help='quit after N seconds (safe smoke test)')
    parser.add_argument('--mute', action='store_true', help='disable tap sound')
    parser.add_argument('--benchmark', action='store_true', help='animate automatically and report frame rate/CPU on exit')
    parser.add_argument('--render', metavar='PNG', help='headless rendering smoke test')
    args = parser.parse_args()
    if (args.size is not None and not .03 <= args.size <= .5) or args.timeout < 0:
        parser.error('size must be 0.03–0.5 and timeout must be nonnegative')
    config = Config(STYLES)
    if config.error:
        print(config.error, file=sys.stderr)
    style = args.hand or config.data['style']
    size = args.size if args.size is not None else config.data['size']
    hand = Hand(style if style != 'laser' else 'lavender')
    if args.render:
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 1280, 720)
        hand.paint(cairo.Context(surface), 550, 250, 1280, 720, size)
        surface.write_to_png(args.render)
        return
    os.environ['GDK_BACKEND'] = 'wayland'
    if not Gtk.init_check():
        parser.exit(1, 'TinyHand needs a running Wayland session.\n')
    try:
        gi.require_version('Gtk4LayerShell', '1.0')
        from gi.repository import Gtk4LayerShell as GtkLayerShell
    except (ValueError, ImportError):
        parser.exit(1, 'Install gtk4-layer-shell with its GObject introspection bindings.\n')
    if not GtkLayerShell.is_supported():
        parser.exit(1, 'Compositor lacks layer-shell; use Sway/Hyprland or a compatible compositor.\n')
    # Keep repeated compositor keybindings from stacking keyboard-grabbing overlays.
    lock_path = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / f'tinyhand-{os.getuid()}.lock'
    lock = lock_path.open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.exit(0, 'TinyHand is already running; press Escape to close it.\n')
    sound = TapSound()
    app = App(hand, size, GtkLayerShell, sound, args.benchmark, config, style, args.mute)
    for sig in (signal.SIGINT, signal.SIGTERM):
        GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, sig, app.quit)
    if args.timeout:
        GLib.timeout_add_seconds(args.timeout, app.quit)
    print('TinyHand: move to point, click to tap, drag to draw; C clears, Esc exits.', flush=True)
    app.loop.run()
    if args.benchmark:
        app.report()
    sound.close()
    for win in app.windows:
        win.destroy()


if __name__ == '__main__':
    main()
