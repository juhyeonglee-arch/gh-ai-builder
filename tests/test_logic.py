# Rhino 없이 순수 로직만 시험한다.
import importlib.util, json, sys, os
here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ghai", os.path.join(here, "..", "src", "GH_AI_builder.py"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
assert not m.IN_RHINO

cat = [
 {"key":"Params/Input/Number Slider","guid":"a","desc":"slider","kind":"param","inputs":[],"outputs":[]},
 {"key":"Curve/Primitive/Line SDL","guid":"b","desc":"line","kind":"component",
  "inputs":[["Start","S","Point","item"],["Direction","D","Vector","item"],["Length","L","Number","item"]],
  "outputs":[["Line","L","Line","item"]]},
 {"key":"Curve/Division/Divide Curve","guid":"c","desc":"divide","kind":"component",
  "inputs":[["Curve","C","Curve","item"],["Count","N","Integer","item"],["Kinks","K","Boolean","item"]],
  "outputs":[["Points","P","Point","list"],["Tangents","T","Vector","list"],["Parameters","t","Number","list"]]},
 {"key":"Params/Geometry/Line","guid":"d","desc":"","kind":"param","inputs":[],"outputs":[]},
]
idx = m.CatalogIndex(cat)
txt = m.catalog_text(cat); print(txt)
assert idx.resolve("Curve/Division/Divide Curve")["guid"] == "c"
assert idx.resolve("curve/division/divide curve")["guid"] == "c"
assert idx.resolve("Divide Curve")["guid"] == "c"
assert idx.resolve("Line")["guid"] == "d"  # 이름이 하나뿐이면 찾아 준다
assert idx.resolve("Nope") is None

P = [("Points","P"),("Tangents","T"),("Parameters","t")]
assert m.match_param(P,"Points")==0 and m.match_param(P,"T")==1 and m.match_param(P,"t")==2
assert m.match_param(P,"parameters")==2 and m.match_param(P,"1")==1 and m.match_param(P,"x") is None
assert m.match_param([("Line","L")],"")==0

assert m.sanitize_slider({"slider_min":10,"slider_max":2,"slider_value":50,"slider_integer":False})[:3]==(2,10,10)
assert m.sanitize_slider({"slider_min":1,"slider_max":1,"slider_value":1,"slider_integer":True})[:3]==(1,2,1)

g = {"title":"t","summary":"s","notes":"","groups":[{"id":"g1","label":"1. 입력","note":""},{"id":"g2","label":"2. 선","note":""}],
 "nodes":[
  {"id":"n1","component":"Params/Input/Number Slider","group":"g1","nickname":"길이","slider_min":0,"slider_max":10,"slider_value":5,"slider_integer":False,"text":"","toggle":False},
  {"id":"n2","component":"Params/Input/Number Slider","group":"g1","nickname":"개수","slider_min":1,"slider_max":20,"slider_value":8,"slider_integer":True,"text":"","toggle":False},
  {"id":"n3","component":"Curve/Primitive/Line SDL","group":"g2","nickname":"","slider_min":0,"slider_max":0,"slider_value":0,"slider_integer":False,"text":"","toggle":False},
  {"id":"n4","component":"Curve/Division/Divide Curve","group":"g2","nickname":"","slider_min":0,"slider_max":0,"slider_value":0,"slider_integer":False,"text":"","toggle":False}],
 "wires":[
  {"from_node":"n1","from_output":"","to_node":"n3","to_input":"Length","mapping":"none"},
  {"from_node":"n3","from_output":"Line","to_node":"n4","to_input":"Curve","mapping":"none"},
  {"from_node":"n2","from_output":"","to_node":"n4","to_input":"Count","mapping":"graft"}]}
assert m.validate_graph(g, idx) == [], m.validate_graph(g, idx)
bad = json.loads(json.dumps(g)); bad["wires"][1]["to_input"]="Crv"; bad["nodes"][2]["component"]="Curve/X/Y"
print(m.validate_graph(bad, idx))
assert len(m.validate_graph(bad, idx)) == 2

sizes = {"n1":(200,20),"n2":(200,20),"n3":(80,60),"n4":(90,64)}
pos = m.layout_positions(g, sizes, (0,0)); print(pos)
assert pos["n3"][0] < pos["n4"][0]           # 흐름 순서
assert pos["n1"][0] + 200 <= pos["n3"][0]    # 그룹 블록 왼→오
assert pos["n1"][1] != pos["n2"][1]          # 겹치지 않음

# 순환이 있어도 끝난다
cyc = json.loads(json.dumps(g)); cyc["wires"].append({"from_node":"n4","from_output":"Points","to_node":"n3","to_input":"Start","mapping":"none"})
m.layout_positions(cyc, sizes, (0,0))

body = m.build_request_body(txt, m.build_user_message("루버", "Millimeters", g, ["node n4: ERROR x"]))
json.dumps(body); assert body["model"]=="claude-opus-5-5" and body["system"][0]["cache_control"]
print(body["messages"][0]["content"][:300])

c = m.StreamCollector()
for ln in ['event: x','data: {"type":"message_start","message":{"model":"claude-opus-5-5","usage":{"input_tokens":5}}}',
           'data: {"type":"content_block_start","index":0,"content_block":{"type":"thinking"}}',
           'data: {"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"hm"}}',
           'data: {"type":"content_block_start","index":1,"content_block":{"type":"text"}}',
           'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"{\\"a\\": "}}',
           'data: {"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"1}"}}',
           'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":9}}']:
    c.feed(ln)
assert c.result()=={"a":1} and c.usage["output_tokens"]==9
c2 = m.StreamCollector(); c2.feed('data: {"type":"message_delta","delta":{"stop_reason":"refusal"}}')
try: c2.result(); raise SystemExit("should fail")
except RuntimeError as e: print("refusal ok:", e)
print("ALL OK")
