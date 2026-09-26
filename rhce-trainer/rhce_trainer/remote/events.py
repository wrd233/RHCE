from ansible.plugins.callback import CallbackBase
import json,os,re

class CallbackModule(CallbackBase):
    CALLBACK_VERSION=2.0
    CALLBACK_TYPE='aggregate'
    CALLBACK_NAME='rhce_events'
    CALLBACK_NEEDS_WHITELIST=True
    def record(self,result,status):
        task=result._task
        role=task._role.get_name() if task._role else ''
        d={'host':result._host.get_name(),'action':task.action,'role':role,'status':status}
        # Secret-bearing task arguments and module results are never logged.
        if not result._result.get('_ansible_no_log') and not task.no_log:
            args=task.args or {}
            d['src']=str(args.get('src',''));d['dest']=str(args.get('dest',''))
            d['url']=str(args.get('url',''))
            raw=str(args.get('_raw_params',''))
            if 'http://172.25.254.254/content/hwreport.empty' in raw:d['url']='http://172.25.254.254/content/hwreport.empty'
            msg=str(result._result.get('msg',''))
            if status in ('failed','unreachable') and not re.search(r'password|secret|vault|token',msg,re.I):d['error']=msg[:800]
            for phrase in ('Could not create logical volume of that size','Volume group does not exist','Could not create partition of that size','disk /dev/vdd does not exist'):
                if phrase in msg:d.setdefault('messages',[]).append(phrase)
        with open(os.environ['RHCE_EVENT_FILE'],'a') as f:f.write(json.dumps(d)+'\n')
    def v2_runner_on_ok(self,result):self.record(result,'ok')
    def v2_runner_on_failed(self,result,ignore_errors=False):self.record(result,'failed')
    def v2_runner_on_unreachable(self,result):self.record(result,'unreachable')
    def v2_runner_on_skipped(self,result):self.record(result,'skipped')
