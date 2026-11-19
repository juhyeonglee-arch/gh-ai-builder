# 사용: python3 views.py <정의.json> <이름표> [슬라이더id=값 ...]
import os as _os; _T=_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'..')
import sys,json,math,subprocess,os,time; sys.path.insert(0,_T); sys.path.insert(0,_os.path.join(_T,'render'))
import numpy as np, ghsim as S, export_tris as E
f=sys.argv[1]; tag=sys.argv[2]
t=time.time(); s=S.Sim(json.load(open(f,encoding='utf-8'))).run(); geo=s.baked(); print('sim',time.time()-t)
info=json.load(open(tag+'_data/info.json')) if os.path.exists(tag+'_data/info.json') and '--reuse' in sys.argv else E.export(geo,tag+'_data'); print('export',info)
ev=s.items('ev','Point'); P=ev[len(ev)//2+3]
rad=P*np.array([1,1,0]); rad/=np.linalg.norm(rad); tan=np.cross([0,0,1],rad)
lo,hi=np.array(info['_bbox'][0]),np.array(info['_bbox'][1]); C=(lo+hi)/2
env=dict(os.environ,THREE_JS=os.environ.get('THREE_JS','node_modules/three/build/three.module.js'))
def shot(name,eye,target,fov=30,w=1200,h=1500,**kw):
    p=dict(w=w,h=h,eye=[float(v) for v in eye],target=[float(v) for v in target],fov=fov,**kw)
    t=time.time(); r=subprocess.run(['node',_os.path.join(_T,'render','render.js'),os.path.abspath(tag+'_data'),os.path.abspath(tag+'_'+name+'.png'),json.dumps(p)],env=env,capture_output=True,text=True); print(name,time.time()-t,r.stdout[-300:],r.stderr[-500:])
shot('ext',C+np.array([230000,-290000,90000]),C+np.array([0,0,-6000]),fov=36,w=1000,h=1500)
shot('struct',C+np.array([230000,-290000,90000]),C+np.array([0,0,-6000]),fov=36,w=1000,h=1500,hide=['glass','aluminum','spandrel'])
shot('node',P+rad*9000+tan*5000-np.array([0,0,1500]),P,fov=55,w=1400,h=1000,hide=['glass','aluminum','spandrel'])
shot('facade',P+rad*7000+tan*4000+np.array([0,0,2000]),P+np.array([0,0,1000]),fov=55,w=1400,h=1000,glassOpacity=0.35)
