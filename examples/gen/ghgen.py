# JSON 그래프를 짧게 쓰기 위한 도우미 (예시 생성용)
import json
class G:
    def __init__(s): s.nodes=[]; s.wires=[]; s.groups=[]; s.blocks=[]; s.g="g1"
    def group(s,i,label,note): s.groups.append({"id":i,"label":label,"note":note}); s.g=i
    def S(s,i,nick,a,b,v,integer=True): s.nodes.append({"id":i,"component":"Params/Input/Number Slider","group":s.g,"nickname":nick,"slider":[a,b,v],"int":integer}); return (i,"")
    def P(s,i,t,nick=None): s.nodes.append({"id":i,"component":"Params/Input/Panel","group":s.g,"nickname":nick or t,"text":t}); return (i,"")
    def T(s,i,nick,v): s.nodes.append({"id":i,"component":"Params/Input/Boolean Toggle","group":s.g,"nickname":nick,"toggle":v}); return (i,"")
    def N(s,i,comp,ins=None,nick="",bake=False,mat="",out=None):
        assert i not in [n["id"] for n in s.nodes], "duplicate id "+i
        d={"id":i,"component":comp,"group":s.g}
        if nick: d["nickname"]=nick
        if bake: d["bake"]=True
        if mat: d["material"]=mat
        s.nodes.append(d)
        for k,v in (ins or {}).items():
            m=None
            if isinstance(v,tuple) and len(v)==3: m=v[2]; v=v[:2]
            s.wires.append([v[0],v[1],i,k]+([m] if m else []))
        return (i,out) if out else i
    def o(s,i,out): return (i,out)
    def op(s,i,kind,a,b,nick=""):
        s.N(i,"Maths/Operators/"+kind,{"A":a,"B":b},nick); return (i,"Result")
    def dump(s,path,title,summary,notes):
        g={"title":title,"summary":summary,"notes":notes,"groups":s.groups,"nodes":s.nodes,"wires":s.wires,"blocks":s.blocks}
        open(path,"w",encoding="utf-8").write(json.dumps(g,ensure_ascii=False,indent=0)); return g
def graft(x): return (x[0],x[1],"graft")
def flat(x): return (x[0],x[1],"flatten")
