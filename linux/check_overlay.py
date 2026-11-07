"""Six-second live overlay check. Requires a Wayland desktop; uses temporary preferences.

Run explicitly: python3 linux/check_overlay.py
This opens the real picker and renders ink. It does not replace a normal launch
and physical-pointer check.
"""
import os,sys,tempfile
import tinyhand as t
import gi
gi.require_version('Gtk4LayerShell','1.0')
from gi.repository import Gtk4LayerShell as L
assert t.Gtk.init_check()
tmp=tempfile.TemporaryDirectory()
config=t.Config(t.STYLES,os.path.join(tmp.name,'config.json'))
a=t.App(t.Hand('lavender'),.13,L,t.TapSound(os.environ.get('TINYHAND_CHECK_AUDIO') == '1'),False,config)
w=a.windows[0]
errors=[]
def check(function):
 def call():
  try:function()
  except Exception as error: errors.append(error); a.quit()
  return False
 return call
def open_picker():
 w.revealer.set_reveal_child(True)
 w.toolbar.menu.popup()
 w.toolbar.open_picker()
 assert len(w.toolbar.buttons)==37, len(w.toolbar.buttons)
def pick():
 assert len(a.thumb_cache)==36, len(a.thumb_cache)
 w.toolbar.buttons['glove'][-1].emit('clicked')
 assert a.style=='glove'
 assert t.Config(t.STYLES,config.path).data['style']=='glove'
 w.point=(700,300)
 # Canvas press/release path, followed by switching pointer. Old ink keeps color.
 class Gesture:
  def get_current_button(self):return 1
 w.button(Gesture(),1,300,400)
 w.motion(None,400,500)
 w.release()
 old_color=w.stroke_colors[0]
 a.pick('laser')
 assert not a.sound_enabled()
 assert w.stroke_colors[0]==old_color
 a.toggle_sound()
 assert a.sound_enabled()
 a.pick('coral')
 assert w.stroke_colors[0]==old_color and old_color!=a.color
 w.canvas.queue_draw()
def finish():
 assert w.canvas.ink_node is not None
 a.clear()
 assert not w.strokes and not w.stroke_colors
 a.quit()
def preview(choice):
 w.toolbar.sound_menu.popup()
 w.toolbar.sound_buttons[choice].emit('clicked')
 assert a.config.data['tap_sound']==choice
 assert t.Config(t.STYLES,config.path).data['tap_sound']==choice
 assert a.sound_enabled()
 assert not w.strokes, 'sound controls must not draw ink'
def sound_off():
 w.toolbar.sound_off.emit('clicked')
 assert not a.sound_enabled()
 assert w.key(None,t.Gdk.KEY_Escape,0,0)
 assert not w.toolbar.sound_menu.get_active()
 assert a.loop.is_running(), 'Escape should close picker, not the application'
for index, choice in enumerate(t.SOUNDS):
 t.GLib.timeout_add(800+index*350,check(lambda choice=choice:preview(choice)))
t.GLib.timeout_add(3200,check(sound_off))
t.GLib.timeout_add(400,check(open_picker))
t.GLib.timeout_add(4500,check(pick))
t.GLib.timeout_add(5500,check(finish))
a.loop.run()
for win in a.windows:win.destroy()
if errors:raise errors[0]
print('Sound picker: six previews, persistence, Off and Escape passed. Picker: 37 styles, 36 thumbnails; selection persistence, laser, mute, ink colors and clear passed')
tmp.cleanup()
