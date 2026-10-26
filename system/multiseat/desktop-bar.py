#!/usr/bin/env python3
"""Small clickable bar for the second desktop; no background polling."""
import json,os,select,subprocess,sys,time
print('{"version":1,"click_events":true}\n[',flush=True)
items=[('apps','Applications'),('browser','Browser'),('files','Files'),('terminal','Terminal')]
while True:
    blocks=[{'name':key,'full_text':'  '+label+'  ','color':'#f9dfce','separator':False} for key,label in items]
    blocks.append({'full_text':time.strftime('  %a  %H:%M  '),'color':'#d6beb0','separator':False})
    print(json.dumps(blocks)+',',flush=True)
    ready,_,_=select.select([sys.stdin],[],[],10)
    if ready:
        line=sys.stdin.readline().strip().lstrip(',')
        if not line:break
        try:name=json.loads(line).get('name')
        except ValueError:continue
        commands={'apps':['fuzzel'],'browser':[os.path.expanduser('~/.local/bin/caelestia-multiseat'),'browser'],
                  'files':[os.path.expanduser('~/.local/bin/caelestia-multiseat'),'files'],'terminal':['foot']}
        if name=='browser':
            try:
                state=json.loads((__import__('pathlib').Path(os.environ.get('XDG_RUNTIME_DIR','/run/user/'+str(os.getuid())))/'caelestia-multiseat/state.json').read_text())
                if state.get('testing'):commands['browser']=[os.path.expanduser('~/.local/bin/caelestia-agent-desktop'),'browser']
            except (OSError,ValueError):pass
        if name in commands:
            try:subprocess.Popen(commands[name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:pass
