# 사용자 PC(Rhino 8) 실제 컴포넌트 목록으로 예시 JSON을 검사
import sys,re,json,glob,os
sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','src'))
import GH_AI_builder as B
def parse_params(s):
    s=s.strip()
    if s=='-' or not s: return []
    out=[]
    for m in re.finditer(r'([^,\[]+?)\[([^\]]*)\]\s*([A-Za-z ]*?)(\[\]|\{\})?(?:,|$)', s):
        acc='list' if m.group(4)=='[]' else ('tree' if m.group(4)=='{}' else 'item')
        out.append([m.group(1).strip(),m.group(2),m.group(3).strip(),acc])
    return out
def load(path):
    E=[]
    for line in open(path,encoding='utf-8-sig'):
        line=line.rstrip('\n')
        if ' :: ' not in line: continue
        key,rest=line.split(' :: ',1)
        parts=rest.split(' | ')
        if parts[-1].strip()=='PARAM':
            E.append({"key":key,"kind":"param","inputs":[],"outputs":[],"guid":"p","desc":parts[0]}); continue
        ins=[p for p in parts if p.startswith('IN: ')]; outs=[p for p in parts if p.startswith('OUT: ')]
        E.append({"key":key,"kind":"component","guid":"x","desc":parts[0],
          "inputs":parse_params(ins[-1][4:]) if ins else [],"outputs":parse_params(outs[-1][5:]) if outs else []})
    return E
if __name__=='__main__':
    E=load(sys.argv[1] if len(sys.argv)>1 else os.path.join(os.path.dirname(__file__),'real_catalog_rhino8.txt')); idx=B.CatalogIndex(E)
    print(len(E),'entries')
    for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','examples','*.json'))):
        g=B.parse_pasted(open(f,encoding='utf-8').read()) if hasattr(B,'parse_pasted') else None
        if isinstance(g,tuple): g=g[0]
        iss=B.validate_graph(g,idx)
        print('==',os.path.basename(f),len(iss))
        for i in sorted(set(iss)): print('  ',i)
