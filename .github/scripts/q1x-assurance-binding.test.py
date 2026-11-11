import copy,json,os,pathlib,subprocess,tempfile
source=(pathlib.Path(__file__).resolve().parents[1]/'workflows/q1x-central-independent-assurance.yml').read_text()
script=source.split("          cat > \"$verifier\" <<'VERIFY'\n",1)[1].split('          VERIFY\n',1)[0]
script='\n'.join(line[10:] for line in script.splitlines())+'\n'
root=pathlib.Path(tempfile.mkdtemp(prefix='q1x-live-binding-fixture-'));root.chmod(0o700)
(root/'verify.sh').write_text(script)
(root/'gh').write_text('#!/usr/bin/env python3\nimport json,os,sys\nd=json.load(open(os.environ["MOCK_RESPONSES"]))\nk=sys.argv[2]\nif k not in d: sys.exit(1)\nv=d[k]\nprint(json.dumps(v) if isinstance(v,dict) else v)\n')
(root/'gh').chmod(0o700)
repo='Example/central-fixture';head='a'*40;base='b'*40
pr={'number':1,'state':'open','head':{'sha':head},'base':{'sha':base,'ref':'main','repo':{'full_name':repo}}}
event={'repository':{'default_branch':'main'},'pull_request':pr}
cases=[]
def add(name,event_name,event,answers,allowed): cases.append((name,event_name,copy.deepcopy(event),copy.deepcopy(answers),allowed))
answers={f'repos/{repo}/pulls/1':pr}
add('current-pr','pull_request',event,answers,True)
for field,value in [('head','c'*40),('base','c'*40),('ref','other'),('state','closed'),('repo','Foreign/repo')]:
 changed=copy.deepcopy(answers); live=changed[f'repos/{repo}/pulls/1']
 if field in ['head','base']:live[field]['sha']=value
 elif field=='ref':live['base']['ref']=value
 elif field=='repo':live['base']['repo']['full_name']=value
 else:live[field]=value
 if field=='base':changed[f'repos/{repo}/compare/{base}...{value}']={'status':'ahead','base_commit':{'sha':base},'merge_base_commit':{'sha':base}}
 add('changed-'+field,'pull_request',event,changed,field=='base')
retarget=copy.deepcopy(event);retarget['pull_request']['base']['ref']='other';live=copy.deepcopy(pr);live['base']['ref']='other'
add('current-nondefault-target','pull_request',retarget,{f'repos/{repo}/pulls/1':live},True)
add('missing-pr','pull_request',event,{},False)
merge={'repository':{'default_branch':'main'},'merge_group':{'head_sha':head,'base_sha':base,'base_ref':'refs/heads/main','head_ref':'refs/heads/gh-readonly-queue/main/pr-1'}}
mganswers={f'repos/{repo}/branches/main':base,f'repos/{repo}/git/ref/heads/gh-readonly-queue/main/pr-1':head}
add('current-merge-group','merge_group',merge,mganswers,True)
for key in mganswers:
 changed=copy.deepcopy(mganswers);changed[key]='c'*40
 add('changed-merge-'+('base' if 'branches' in key else 'head'),'merge_group',merge,changed,False)
add('destroyed-merge-group','merge_group',merge,{},False)
release=copy.deepcopy(merge)
release['merge_group']['base_ref']='refs/heads/release/stable'
release['merge_group']['head_ref']='refs/heads/gh-readonly-queue/release/stable/pr-1'
release_answers={f'repos/{repo}/branches/release%2Fstable':base,f'repos/{repo}/git/ref/heads/gh-readonly-queue/release/stable/pr-1':head}
add('nondefault-merge-group','merge_group',release,release_answers,True)
for invalid in ['refs/tags/main','refs/heads/','']:
 bad=copy.deepcopy(merge);bad['merge_group']['base_ref']=invalid
 add('invalid-merge-base-'+invalid,'merge_group',bad,mganswers,False)
add('unsupported-event','push',event,answers,False)
graph=root/'graph';graph.mkdir()
def git(*args):
 return subprocess.check_output(['git','-C',str(graph),'-c','user.name=Q1X fixture','-c','user.email=fixture@example.invalid',*args],text=True,stderr=subprocess.DEVNULL).strip()
def commit(label):
 (graph/'history.txt').write_text(label);git('add','history.txt');git('commit','-qm',label);return git('rev-parse','HEAD')
git('init','-q','--initial-branch=main')
initial=commit('initial');event_base=commit('event baseline')
git('checkout','-q','--detach',initial);divergent=commit('divergent target')
git('checkout','-q','--detach',event_base);forward=commit('forward target')
git('checkout','-q','--detach',event_base);candidate_head=commit('candidate')
event_range=git('rev-list',event_base+'..'+candidate_head).splitlines()
rewound_range=git('rev-list',initial+'..'+candidate_head).splitlines()
assert event_base not in event_range and event_base in rewound_range,'Fixture must reproduce the omitted-commit gap'
for name,target,allowed in [('forward',forward,True),('rewind',initial,False),('divergence',divergent,False)]:
 common=git('merge-base',event_base,target)
 status='ahead' if common==event_base else ('behind' if common==target else 'diverged')
 graph_pr=copy.deepcopy(pr);graph_pr['head']['sha']=candidate_head;graph_pr['base']['sha']=event_base
 graph_event={'pull_request':copy.deepcopy(graph_pr)};graph_pr['base']['sha']=target
 graph_answers={f'repos/{repo}/pulls/1':graph_pr,f'repos/{repo}/compare/{event_base}...{target}':{'status':status,'base_commit':{'sha':event_base},'merge_base_commit':{'sha':common}}}
 add('git-graph-target-'+name,'pull_request',graph_event,graph_answers,allowed)
unproved=copy.deepcopy(answers);unproved[f'repos/{repo}/pulls/1']['base']['sha']='c'*40
add('changed-base-without-ancestry-proof','pull_request',event,unproved,False)
for name,kind,event,answers,allowed in cases:
 (root/'event.json').write_text(json.dumps(event));(root/'answers.json').write_text(json.dumps(answers))
 env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],GITHUB_EVENT_PATH=str(root/'event.json'),GITHUB_EVENT_NAME=kind,GITHUB_REPOSITORY=repo,RUNNER_TEMP=str(root),MOCK_RESPONSES=str(root/'answers.json'))
 result=subprocess.run(['bash',str(root/'verify.sh')],env=env,capture_output=True)
 assert (result.returncode==0)==allowed,(name,result.returncode,result.stderr.decode())
 print(name,'PASS')
print(str(len(cases))+' proposal-binding cases passed; '+str(root))
