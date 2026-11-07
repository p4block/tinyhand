# Full Linux overlay and settings port

Status: phase 1 implemented; see PLAN.md for verification and remaining checks.
Continue with phase 2. Primary target: user's Sway/Wayland,
5120×1440 at 240 Hz. Hyprland next; KDE where layer-shell is available. A GNOME
backend is a separate optional project. Settings follow the usable overlay.

## Preserve the working baseline

Current entry point: `python3 linux/tinyhand.py`. GPU hand/rod textures, cached
ink, cached libcanberra tap sound, per-output overlays, frame-clock animation,
idle tick shutdown. Measured 239.8 rendered fps / 5.7% of one CPU core in a
six-second benchmark; this is a local observation, not a universal guarantee.

Always keep the transparent 1×1 texture render node: without an initial buffer,
the empty overlay never mapped and received no mouse events. Handle pointer
enter as well as motion. Every phase must pass a NORMAL launch test; benchmark
animation bypasses real pointer acquisition and previously concealed this bug.

Do not implement settings controls for behavior the backend does not yet support.
Do not replace GPU rendering with a fullscreen software drawing loop.

## Architecture and boundaries

Keep Python/PyGObject, GTK4 and gtk4-layer-shell. One process owns overlays,
settings, configuration and audio. Use Gtk.Application's session-bus single
instance and actions for command forwarding; replace the current flock ownership
only once cold/warm launch tests pass. Settings is a normal desktop window in
this process, independently launchable from the application menu.

Suggested modules (extract incrementally, not an upfront rewrite):

- `tinyhand.py`: compatibility entry point and CLI.
- `app.py`: Gtk.Application, actions, overlay lifecycle and session state.
- `config.py`: schema, validation, migration, atomic writes and notifications.
- `styles.py`: built-in/custom style registry, metadata, thumbnails, GPU cache.
- `overlay.py`: presentation surfaces, input routing, per-output state.
- `render.py`: hand/rod/laser, ink nodes, animation and frame diagnostics.
- `toolbar.py`: GTK controls and pointer picker inside each overlay.
- `audio.py`: cached samples and preview/playback.
- `settings.py`: ordinary GTK settings window, shared application actions.

Use a GTK overlay container: GPU Canvas below a bottom-aligned GTK toolbar.
Put popovers within the existing layer surface where feasible. Pointer tracking
uses capture-phase motion so hovering toolbar controls does not lose location;
presentation click/draw handlers belong to the canvas, not the root capture
controller. Toolbar clicks must never make ink or trigger a presentation tap.
Show the ordinary cursor over interactive controls and suppress the hand there.

Settings/interaction state must be explicit:
`inactive`, `presenting`, `settings`, optional `interacting`.
Opening settings hides/unmaps presentation surfaces and releases exclusive
keyboard input BEFORE presenting the ordinary window. Keep an in-window GPU
preview for live changes. Closing settings leaves presentation inactive; a
prominent Start presenting action resumes it. No invisible overlay may block
settings, dialogs, file pickers, or other applications.

Configuration: `${XDG_CONFIG_HOME:-~/.config}/tinyhand/config.json`, versioned,
validated, atomic same-directory replace; corrupt file gets a recoverable backup
and defaults. Only the owner process writes. User data lives in
`${XDG_DATA_HOME:-~/.local/share}/tinyhand/`. Resolve assets relative to installed
resources, never current working directory. CLI overrides are session-only;
explicit UI changes persist. Config notifications update open settings, toolbar
and renderer together. Debounce disk writes, never rendering updates.

## Phase 1 — usable overlay cursor selector

1. Extract style metadata from Swift PointerStyle: stable IDs, display names,
   ink colors, default pins; add laser style using GPU nodes.
2. Add minimal validated persistence: selected style, ordered pins (max eight),
   sound toggles, pointer size. Preserve CLI overrides.
3. Bottom toolbar: pinned style thumbnails, all-pointers grid, mute, clear,
   settings entry (until implemented, omit), and Exit presentation. Default pins:
   lavender, glove, coral, plush, robot, laser.
4. Grid offers every bundled hand and laser; selection immediately updates the
   pointer and matching ink color, persists, and highlights the chosen style.
   Cache resized thumbnails and a bounded number of full-resolution textures;
   do not upload all 36 original PNGs on each click/frame.
5. Reveal toolbar near the bottom edge and briefly at activation; retain it while
   hovering, keyboard-focused, or a picker is open. Hide during drawing. No
   permanent polling timer. Keep controls inside the active monitor's bounds.
6. End an active stroke before changing style/output; keep existing ink colors.

Acceptance: launch normally, enter toolbar without drawing, pick three different
hands and laser, return to canvas, draw/clear/mute, restart and confirm selection.
Picker stays usable at fractional scale and on small outputs. Plain pointing
still sustains approximately the 240 Hz baseline; stationary hand stops ticks.

## Phase 2 — lifecycle, commands and complete overlay behavior

1. Introduce Gtk.Application ownership/actions and CLI commands:
   `--toggle`, `--show`, `--hide`, `--clear`, `--settings`, `--quit`.
   Cold `--toggle` starts presenting; cold `--settings` opens only settings.
   Plain launch shows presentation; forwarded requests never create duplicates.
   Escape clears/hides presentation; `--quit` stops the process. Keep inactive
   ownership explicitly while waiting for later commands; `--timeout` still
   terminates the whole process for smoke tests.
2. Publish Sway/Hyprland binding examples for toggle/clear. Do not edit the user's
   compositor config automatically. In settings, offer copyable bindings rather
   than claiming an unsupported global shortcut recorder.
3. Complete GPU shadow and tap/laser animation. Implement matching/custom ink
   colors, optional toolbar ink button, and per-stroke fade delays 3/6/10 seconds
   or keep-until-cleared; original fade duration is 0.6 seconds. Bound ink work:
   cache completed strokes, simplify points where appropriate, discard expired
   nodes, and animate only during actual fading. Keep work out of the motion
   handler beyond collecting input and invalidation.
4. Support thock/click/pop/wood/boop/squeak, preview and per-style-group mute
   (hands enabled, laser disabled by default). Give each cached sample a distinct
   event ID to avoid audio-server cache collisions; no per-click processes.
   Switch default to original thock when schema defaults are introduced;
   preserve explicit saved choices. Audio failure never stops presentation.
5. Rebuild safely on output changes; finish strokes and remove old callbacks.
   Restrict keyboard ownership so a different output's overlay cannot strand
   popovers or toolbar keyboard focus. Decide and document whether ink survives
   output removal (recommended: discard only removed output's ink).

Acceptance: cold/warm command forwarding, repeated launches, toggle during drag,
Escape, hotplug and fractional scaling. Verify fade timing at both 60 and 240 Hz,
rapid taps, separate laser mute, and no click leakage into underlying apps.

## Phase 3 — settings app

Build one normal GTK window with sidebar pages matching the original:

| Page | Linux behavior |
| --- | --- |
| General | Start/stop presentation, copied compositor binding examples, launch-at-login, supported interaction options, reset preferences |
| Pointers | All 36 hands + laser, selected style, ordered pinned list, add/remove/replace pins, eight-item limit, custom hands entry point |
| Appearance | Size (original UI range 8–20%, default 13%; preserve wider supported CLI values), GPU shadow toggle, live preview |
| Drawing | Match pointer or red/orange/yellow/green/blue/purple/white/black, fade delay, toolbar ink button, clear ink |
| Sound | Off plus six sound tiles with preview, separate laser sound toggle |
| About | Version, MIT attribution, source link, Linux support information, diagnostics copy, reset action |

Start with selection, size and sound; then finish remaining pages. Changes apply
immediately to the preview and next presentation. Pin order supports accessible
move-left/right or up/down buttons first; drag reordering is a polish step.
Reset restores validated defaults and propagates to all views, with confirmation.
Only expose launch-at-login once installation provides a stable executable;
use an XDG autostart entry that launches inactive, never captures the desktop
unexpectedly at login. No Sparkle/macOS permission prompts on Linux. Updates use
the user's package/install mechanism; do not build an unrelated auto-updater.

Acceptance: settings is usable while presentation was active; no trapped input.
All changes persist across restart; changing one setting preserves others.
Keyboard navigation, Escape/popover behavior and readable labels at 100–200%
scaling. Settings-only launch never creates capturing overlay surfaces.

## Phase 4 — custom hands and remaining interaction parity

Custom hands: port Swift HandMaker's transparent-image validation, geometry
measurement, rod composition and color extraction. Import local PNG via file
chooser, preview, name, save, rename/delete, pin/unpin. Preserve original images
and app-owned derivatives separately. Reject invalid dimensions/transparency,
empty or disconnected art with actionable messages. Limit image dimensions and
process thumbnails/composition off the frame path. Offer the original prompt as
copyable text; image generation is a user step, no new service dependency.

The macOS hold-modifier-to-click-through feature needs a separate Wayland design:
ordinary clients lose pointer tracking after input regions become click-through.
Do not fake parity using root/evdev or synthetic input. First ship an explicit
interaction mode: hide/unmap overlays, restore ordinary input, resume through a
compositor-bound `--show`/`--toggle` command. Only expose hold-to-interact if a
compositor-supported route can reliably detect release and recover focus; test
lost focus, modifier release outside the surface and compositor shortcuts.
Keeping a tracking hand while fully passing through is optional backend work.

Acceptance: custom import/restart/delete/pin edge cases and invalid files; explicit
interaction always has a working path back. Unsupported features stay absent
or clearly unavailable, rather than toggles that silently do nothing.

## Phase 5 — installation and compatibility

Provide an installable user app with a stable `tinyhand` executable, desktop entry,
icon, bundled assets/sounds, version and dependency instructions. Installer must
support clean upgrades/uninstall without deleting user preferences/custom hands.
Keep `python3 linux/tinyhand.py` usable from the repository.

Test Sway first, then Hyprland, then KDE. Detect layer-shell capability rather
than guessing desktop names. Settings can work without layer-shell; starting
presentation reports the missing capability without crashing settings. Lazy-load
the layer library before GTK/Wayland linkage when available; do not keep the
current unconditional CDLL failure as the settings-only behavior. GNOME overlay
support requires its own backend/extension and is outside the core milestones.
A tray/status notifier is optional polish; application-menu launcher and compositor
bindings are the required entry points.

## Validation and handoff rules

After each phase record files changed, exact commands run, measured results,
remaining failures and the next unchecked item in PLAN.md. Keep each phase
independently runnable. Do not mark behavior verified from an FPS count alone.

- Headless: all hand geometry/asset checks; config migration/corruption/atomic
  update tests; pin validation; custom-image validation when introduced.
- Live Sway: normal startup from a stationary pointer, pointer movement, exit and
  re-entry, toolbar/picker clicks, drawing/clear, sound, settings transitions,
  duplicate launch and shutdown, multi-output/hotplug, fractional scaling.
- Performance: same six-second benchmark at 240 Hz before/after; compare CPU,
  frame intervals and renderer, distinguish snapshot rate from actual display
  presentation. Also measure stationary idle, open picker, and long ink sessions.
  Target baseline within roughly 10% for plain pointing; investigate regressions
  before proceeding. No continuous animation timers after settling/fading.
- Capture a screenshot or visually verify the actual hand in a normal session.
  The previous successful benchmark did not establish that normal launch worked.

Recommended delivery order: phase 1 cursor selector → phase 2 commands/overlay
parity → phase 3 settings → phase 4 custom/interaction → phase 5 packaging.
Do not parallelize changes to the shared application/input lifecycle without
agreeing interfaces; stable modules can be assigned independently later.
