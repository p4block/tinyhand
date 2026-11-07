# TinyHand on Linux (MVP)

Run from any directory:

```sh
python3 /path/to/tinyhand/linux/tinyhand.py
```

Move to point, click to tap, hold left button and drag to draw. **C** or **X**
clears ink on every output; **Escape** exits and restores normal input.
Presentation mode consumes mouse and keyboard input while running. Your compositor
shortcuts still apply. No root access or input-device permissions needed.

Options: `--hand glove`, `--size 0.18`, `--timeout 10` (automatic exit).
`--mute` disables tap sound. `--benchmark --timeout 6` animates the hand and
reports rendered frames per second and CPU usage on exit.
Move near the **bottom edge** to reveal the toolbar. Click a pinned hand or the
**grid button** to choose from 36 hands and a laser. Speaker toggles taps for
hands/laser separately. The adjacent sound button opens a picker with **Thock,
Click, Pop, Wood block, Boop, Squeak**, **Choose custom sound**, and **Off**. Click a sound to preview and
select it; the choice is saved. Thock is the default. The eraser clears ink and
× exits. The toolbar appears
briefly on startup and stays visible while its controls or picker are in use.
Toolbar clicks do not draw or tap. Escape closes an open picker first.

Selection and sound preferences save to `~/.config/tinyhand/config.json` (or
`$XDG_CONFIG_HOME/tinyhand/config.json`). Explicit `--hand`, `--size`, and `--mute`
arguments override saved values for the session; toolbar changes persist.
No settings window yet.

Dependencies: Python 3, PyGObject, Pycairo, GTK 4, gtk4-layer-shell including
introspection data, and libcanberra with its PulseAudio backend for tap sound
(also works through PipeWire’s PulseAudio server). On Arch:

```sh
sudo pacman -S python-gobject python-cairo gtk4 gtk4-layer-shell libcanberra
```

On Debian/Ubuntu, install the GTK 4 and **gtk4**-layer-shell introspection
packages for your release, plus `python3-gi python3-gi-cairo python3-cairo
libcanberra0 libcanberra-pulse`. Older releases may lack gtk4-layer-shell.

Sway binding (replace the path):

```text
bindsym $mod+Shift+h exec python3 /path/to/tinyhand/linux/tinyhand.py
```

Hyprland binding:

```text
bind = SUPER SHIFT, H, exec, python3 /path/to/tinyhand/linux/tinyhand.py
```

Targets native Wayland layer-shell compositors, primarily Sway and Hyprland.
KDE can use the same backend if layer-shell is advertised; it is untested.
Unsupported compositors receive a clear error (no GNOME backend yet).
The program creates an overlay per monitor and rebuilds on monitor hotplug;
GTK supplies logical coordinates for scaled displays.

Validation / remaining work: [PLAN.md](PLAN.md). Headless checks:

```sh
python3 linux/test_tinyhand.py
python3 linux/test_config.py
python3 linux/tinyhand.py --render /tmp/tinyhand.png
```

Rendering uses GTK 4 GPU textures for the hand and rod; ink is cached between
stroke changes. Animation follows the output frame clock with time-based easing,
and frame callbacks stop once the hand settles. No fixed 60 Hz timer.

For the live picker/ink integration check (opens a six-second overlay with
temporary preferences): `python3 linux/check_overlay.py`.

## Arch package

From the repository root:

```sh
makepkg -si
```

The `tinyhand-git` package fetches this fork's `main` branch, runs headless tests,
and installs a `tinyhand` command and application-menu launcher. The launcher
starts presentation immediately; **Esc** exits. Use `tinyhand` in compositor
bindings after installation. Preferences and custom user data are not packaged
or removed on uninstall. The settings window is still planned.
