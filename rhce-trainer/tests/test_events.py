"""Callback privacy tests do not require Ansible on the local computer."""
import json
import os
import runpy
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class EventsTests(unittest.TestCase):
    def callback(self):
        module=types.ModuleType('ansible.plugins.callback')
        module.CallbackBase=object
        with patch.dict('sys.modules',{'ansible.plugins.callback':module}):
            return runpy.run_path(str(Path(__file__).resolve().parents[1]/'rhce_trainer/remote/events.py'))['CallbackModule']()

    def record(self,args,message,no_log=False):
        callback=self.callback()
        result=Mock()
        result._task._role=None
        result._task.action='ansible.builtin.debug'
        result._task.no_log=no_log
        result._task.args=args
        result._host.get_name.return_value='servera'
        result._result={'msg':message}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            with patch.dict(os.environ,{'RHCE_EVENT_FILE':str(path)}):
                callback.record(result,'failed')
            return json.loads(path.read_text())

    def test_freeform_errors_and_urls_are_not_saved(self):
        event=self.record({'url':'https://example.invalid/private?value=sensitive-canary'},'sensitive-canary')
        self.assertNotIn('sensitive-canary',json.dumps(event))
        self.assertEqual(event['status'],'failed')

    def test_only_known_branch_messages_are_saved(self):
        event=self.record({},'sensitive-canary: Volume group does not exist')
        self.assertEqual(event['messages'],['Volume group does not exist'])
        self.assertNotIn('sensitive-canary',json.dumps(event))

    def test_no_log_suppresses_paths_and_messages(self):
        event=self.record({'src':'index.html.j2','dest':'/var/www/html/index.html'},'Volume group does not exist',True)
        self.assertNotIn('src',event)
        self.assertNotIn('dest',event)
        self.assertNotIn('messages',event)
