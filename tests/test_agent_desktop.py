"""Routing regressions; no host GUI or physical input is used."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
def load(name):
 loader=importlib.machinery.SourceFileLoader(name,str(ROOT/'bin'/name))
 spec=importlib.util.spec_from_loader(loader.name,loader)
 module=importlib.util.module_from_spec(spec);loader.exec_module(module);return module

class Routing(unittest.TestCase):
 def test_default_target_does_not_follow_monitor_focus(self):
  helper=load('caelestia-multiseat')
  monitors=[{'name':'HDMI-A-1','focused':False},{'name':'eDP-1','focused':True}]
  with patch.object(helper,'monitors',return_value=monitors):
   self.assertEqual(helper.choose_output(None,True)['name'],'eDP-1')
   for m in monitors:m['focused']=not m['focused']
   self.assertEqual(helper.choose_output(None,True)['name'],'eDP-1')
 def test_missing_laptop_does_not_choose_external(self):
  helper=load('caelestia-multiseat')
  with patch.object(helper,'monitors',return_value=[{'name':'DP-1'},{'name':'HDMI-A-1'}]):
   with self.assertRaisesRegex(RuntimeError,'Laptop display'):helper.choose_output(None,True)
 def test_mirrored_display_is_not_an_independent_desktop(self):
  helper=load('caelestia-multiseat')
  with patch.object(helper,'monitors',return_value=[{'name':'eDP-1'},{'name':'HDMI-A-1','mirrorOf':'eDP-1'}]):
   with self.assertRaisesRegex(RuntimeError,'joined'):helper.choose_output(None,True)
 def test_unrelated_pid_cannot_authorize_an_old_desktop(self):
  helper=load('caelestia-multiseat')
  with tempfile.TemporaryDirectory() as tmp,patch.object(helper,'RUNTIME',Path(tmp)):
   (Path(tmp)/'state.json').write_text(json.dumps({'running':True,'enabled':True,'supervisor_pid':os.getpid()}))
   value=helper.state()
   self.assertFalse(value['running']);self.assertFalse(value['enabled'])
 def test_paused_exec_has_no_host_fallback(self):
  helper=load('caelestia-multiseat')
  with patch.object(helper,'state',return_value={'running':True,'enabled':False}):
   with self.assertRaisesRegex(RuntimeError,'host fallback'):helper.private_env()
 def test_native_two_person_mode_blocks_agent_input(self):
  cli=load('caelestia-agent-desktop')
  with patch.object(cli,'status',return_value={'inputReady':False}):
   with self.assertRaisesRegex(RuntimeError,'No host input'):cli.environment()
 def test_profiles_are_separate_and_cannot_override_user_directory(self):
  cli=load('caelestia-agent-desktop')
  with tempfile.TemporaryDirectory() as tmp,patch.object(cli,'HOME',Path(tmp)):
   command=cli.prepare_command(['google-chrome','about:blank'])
   self.assertTrue(any(a.startswith('--user-data-dir='+tmp+'/.local/share/caelestia/agent-desktop/')for a in command))
   with self.assertRaisesRegex(ValueError,'dedicated app profile'):
    cli.prepare_command(['google-chrome','--user-data-dir=/home/someone/.config/google-chrome'])
 def test_selected_chrome_profile_cannot_point_to_original(self):
  cli=load('caelestia-agent-desktop')
  with tempfile.TemporaryDirectory() as tmp,patch.object(cli,'HOME',Path(tmp)):
   config=Path(tmp)/'.config/caelestia/agent-desktop.json';config.parent.mkdir(parents=True)
   config.write_text(json.dumps({'chromeProfileRoot':tmp+'/.config/google-chrome','chromeProfileDirectory':'Profile 4'}))
   with self.assertRaisesRegex(ValueError,'private agent profile'):cli.prepare_command(['google-chrome'])
 def test_window_controls_remain_private(self):
  cli=load('caelestia-agent-desktop')
  env={'SWAYSOCK':'/private/socket'}
  with patch.object(cli,'run') as run:
   run.return_value.stdout='[{"success":false,"error":"No matching node"}]'
   with self.assertRaisesRegex(RuntimeError,'No matching node'):cli.ipc('[con_id=123] focus',env=env)
   self.assertEqual(run.call_args.args[0][:3],['swaymsg','-s','/private/socket'])

if __name__=='__main__':unittest.main()
