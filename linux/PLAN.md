# Linux port / handoff

Priority: working hand on Sway, then Hyprland, then optional desktops; settings last.

Architecture: Python 3 + GTK4/PyGObject + GPU texture snapshots + gtk4-layer-shell. Reuse original
PNG assets, measure hand/rod geometry like Swift HandAsset, render stretched rod
and fixed-size hand. One transparent overlay per output, logical coordinates for
HiDPI. Overlay receives input while active (presentation mode); no evdev/root,
input injection, or compositor-specific global pointer polling.

MVP checklist:
- [x] Hand tracks pointer, follows from below screen, press animation.
- [x] Consume clicks, drag to draw, clear, Escape to quit; CLI hand/size.
- [x] Multi-output overlays and output hotplug rebuild.
- [ ] Human verification on physical Sway multi-output/fractional scale setup.
- [ ] Verify Hyprland and KDE; GNOME requires a separate shell extension/backend
      if its compositor does not advertise layer-shell. Fail clearly otherwise.

Next work (in order): compositor keybinding toggle, toolbar
and hand picker, temporary interaction/pass-through design, package/install,
settings last. Do not promise global tracking through click-through surfaces:
Wayland deliberately does not provide that to ordinary clients.

Validation: python3 linux/tinyhand.py --render /tmp/tinyhand.png (headless asset
and rendering smoke); python3 linux/test_tinyhand.py. For a safe interactive test
use --timeout 10; move, click, drag, C to clear, Escape to close. Check underlying
apps receive no clicks; repeat across outputs and scale factors. Record actual
results here/readme; do not confuse rendering tests with compositor tests.

## Verification (2026-11-07)

- Native Sway launch with `--timeout 3`: exited successfully; user confirmed it worked.
- Headless rendering inspected; all 36 assets passed fingertip alignment checks at
  three screen positions (`python3 linux/test_tinyhand.py`).
- Multi-output/hotplug/fractional scaling, Hyprland and KDE still need live checks.

## Performance/audio follow-up (2026-11-07)

Replaced fullscreen GTK3/Cairo software redraw with retained GTK4 GPU textures.
Cairo remains for headless reference rendering and ink only; ink nodes are cached
until strokes change. Tick callbacks stop when settled. Easing uses elapsed time
so its speed is consistent at 60/144/240 Hz. libcanberra caches tap_wood.wav on the
audio server (event.id required for PulseAudio cache); --mute disables it.

Verified on user's Sway: 6-second automated animation benchmark, **239.8 fps,
5.7% of one CPU core**, including startup renderer work. Separate live GPU ink
render/clear test passed. One cached tap playback returned success. Fullscreen
software implementation had no comparable recorded baseline. Repeat using:
`python3 linux/tinyhand.py --benchmark --timeout 6`.

## Normal-launch visibility fix

An empty initial GTK4 snapshot submitted no buffer, so the Wayland surface never
mapped and could not receive pointer enter/motion. The benchmark hid this bug by
always drawing a hand. Always append a fully transparent 1x1 texture node to
bootstrap mapping; handle pointer enter as well as motion. Reproduced no events
before the fix, then real enter/motion after it; user confirmed hand visible.
Future live checks must include a normal launch, not only --benchmark or injected
point values. Preserve the transparent node when no hand/ink is visible.

## Next requested work

Full overlay cursor selector and settings-app implementation is specified in
[FULL_PORT_PLAN.md](FULL_PORT_PLAN.md). Phase 1 is implemented (see results below). Next: phase 2 lifecycle commands and
overlay parity, then the settings window. Preserve current GPU performance
and the transparent-texture startup fix throughout.

## Phase 1 implementation / handoff

Implemented in `tinyhand.py`, `toolbar.py`, `styles.py`, `config.py`:
- Bottom-edge GTK toolbar with six default pinned styles, all-pointers popover,
  per-group mute, clear and exit; controls consume their own input.
- 36 hands plus GPU laser, selected-style highlights and matching ink colors.
  Existing ink retains its original color across pointer changes.
- Two-entry full-size hand/texture cache; thumbnails load on a background worker
  and remain cached. No per-frame PNG decoding or loading all full-size textures.
- Versioned validated atomic JSON preferences for style, pins, size and separate
  hand/laser sound; CLI overrides remain session-only. Corrupt JSON backed up.
- Preserve transparent bootstrap texture, frame-based rendering and idle shutdown.

Verified: normal Sway launch exited cleanly; `python3 linux/test_config.py` (three
cases) and `python3 linux/test_tinyhand.py` (all assets) passed.
`python3 linux/check_overlay.py` passed live picker population (37 styles, 36
thumbnails), selection persistence, laser, mute, ink color retention and clear.
The live check uses temporary preferences. It calls UI callbacks, so human
checks of physical picker clicks, keyboard navigation and small/fractional outputs
remain necessary; settings and compositor commands are NOT implemented yet.

Six-second benchmark: 239.8 rendered fps, 7.4% of one CPU core including startup
and initial toolbar thumbnails. Same FPS as prior 5.7% run, but higher aggregate
CPU; separate startup cost and steady-state CPU before accepting more rendering
work. User's prior renderer benchmark lacked toolbar overhead; do not claim CPU
improved. Reproduce: `python3 linux/tinyhand.py --benchmark --timeout 6`.

Next unchecked items:
1. Human toolbar/picker acceptance on Sway, then multi-output/fractional scale.
2. Phase 2 Gtk.Application command ownership; retain backward-compatible launch.
3. Sound variants, ink fading, GPU shadows, then phase 3 settings.

## Arch packaging

Root `PKGBUILD` builds `tinyhand-git` from this fork's main branch. Installs the
`tinyhand` launcher, desktop entry/icon, runtime modules, original hand/sound
assets, license and Linux docs; no Swift toolchain needed. `check()` runs config
and asset tests plus desktop-entry validation. Staged install and rendering from
the installed resource layout passed. Full makepkg verification recorded below.

Full `makepkg --cleanbuild --force --nodeps` passed using a local Git snapshot
with identical package sources (remote source URL replaced only for the test).
`pacman -T` confirmed all runtime/build/check dependencies installed. Package
archive produced in `/tmp/tinyhand-makepkg`; no system installation performed.
