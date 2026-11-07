"""GTK overlay controls. Presentation gestures stay on the canvas below."""
from gi.repository import Gtk
from styles import STYLES


class Toolbar(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.win = win
        self.buttons = {}
        self.add_css_class('tinyhand-toolbar')
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.END)
        self.set_margin_bottom(20)
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.set_cursor_from_name('default')
        for style in win.app.config.data['pins']:
            button = self.style_button(style)
            self.append(button)
        self.menu = Gtk.MenuButton(icon_name='view-grid-symbolic', tooltip_text='All pointers')
        self.menu.set_direction(Gtk.ArrowType.UP)
        self.popover = Gtk.Popover()
        self.menu.set_popover(self.popover)
        self.menu.connect('notify::active', self.open_picker)
        self.append(self.menu)
        self.mute = Gtk.Button()
        self.mute.connect('clicked', lambda *_: win.app.toggle_sound())
        self.append(self.mute)
        clear = Gtk.Button(icon_name='edit-clear-all-symbolic', tooltip_text='Clear drawing (C)')
        clear.connect('clicked', lambda *_: win.app.clear())
        self.append(clear)
        close = Gtk.Button(icon_name='window-close-symbolic', tooltip_text='Exit presentation (Esc)')
        close.connect('clicked', lambda *_: win.app.quit())
        self.append(close)
        self.picker_built = False
        self.refresh()

    def style_button(self, style, label=False):
        button = Gtk.Button(tooltip_text=STYLES[style][0])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        image = Gtk.Image()
        image.set_pixel_size(38 if not label else 48)
        image.set_size_request(38 if not label else 48, 40 if not label else 48)
        self.win.app.thumbnail(style, image)
        box.append(image)
        if label:
            title = Gtk.Label(label=STYLES[style][0], width_chars=14,
                              max_width_chars=18, wrap=True, justify=Gtk.Justification.CENTER)
            button.set_size_request(140, -1)
            box.append(title)
        button.set_child(box)
        button.connect('clicked', lambda *_: self.pick(style))
        self.buttons.setdefault(style, []).append(button)
        return button

    def pick(self, style):
        self.win.app.pick(style)
        self.menu.popdown()

    def open_picker(self, *_):
        if not self.menu.get_active() or self.picker_built:
            return
        self.picker_built = True
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                           min_children_per_line=5, max_children_per_line=5,
                           homogeneous=True,
                           row_spacing=6, column_spacing=6)
        for style in STYLES:
            flow.append(self.style_button(style, True))
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,
                                   vscrollbar_policy=Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_width(min(780, max(180, self.win.canvas.get_width() - 64)))
        # Respect small outputs instead of forcing a fixed-height popup.
        scroll.set_max_content_height(max(100, min(410, self.win.canvas.get_height() - 130)))
        scroll.set_propagate_natural_height(True)
        scroll.set_child(flow)
        self.popover.set_child(scroll)
        self.refresh()

    def refresh(self):
        for style, buttons in self.buttons.items():
            for button in buttons:
                if style == self.win.app.style:
                    button.add_css_class('suggested-action')
                else:
                    button.remove_css_class('suggested-action')
        muted = not self.win.app.sound_enabled()
        self.mute.set_icon_name('audio-volume-muted-symbolic' if muted else 'audio-volume-high-symbolic')
        self.mute.set_tooltip_text('Unmute taps' if muted else 'Mute taps')
