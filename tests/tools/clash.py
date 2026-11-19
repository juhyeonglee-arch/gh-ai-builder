# 사용: python3 clash.py <정의.json> <이름표> [슬라이더id=값 ...]
import os as _os; _T=_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'..')
import sys,json,math; sys.path.insert(0,_T)
import numpy as np, ghsim as S
f=sys.argv[1]; g=json.load(open(f,encoding='utf-8'))
sl={n['id']:n['slider'][2] for n in g['nodes'] if 'slider' in n}
for k,v in [a.split('=') for a in sys.argv[2:]]:
    for n in g['nodes']:
        if n['id']==k: n['slider'][2]=float(v)
    sl[k]=float(v)
s=S.Sim(g).run(); geo=s.baked()
N,H,Sd,T,sBd=sl['sN'],sl['sH'],sl['sS'],sl['sT'],sl['sBd']
fac=math.radians(T)/(N*H); R=Sd*math.sqrt(.5)
worst={}
for x,mat,name in geo:
    if name in('커튼월 유닛','커튼월 코너','slab','core'): continue
    V=np.vstack(S.faces_of(x))
    z=V[:,2]; k=np.clip(np.floor((z+sBd)/H),0,N); th=k*H*fac
    c,sn=np.cos(-th),np.sin(-th); xr=c*V[:,0]-sn*V[:,1]; yr=sn*V[:,0]+c*V[:,1]
    d=(R-(abs(xr)+abs(yr)))/math.sqrt(2)
    worst[name]=min(worst.get(name,1e9),float(d.min()))
print({k:round(v) for k,v in worst.items()})
