qtran47@atl1-1-03-006-23-0:AutoResearch-SMB$ export OLLAMA_HOST=127.0.0.1:11556

python - <<'PY'
import requests, time

host="http://127.0.0.1:11556"
models=[
 "qwen35-9b-32k:latest",
 "qwen35-9b-q4-32k-chat:latest",
 "qwen35-9b-q4-32k:latest",
 "qwen35-9b-q4-64k:latest",
 "nemotron4b-64k-clean:latest",
 "nemotron4b-64k:latest",
 "qwen35-27b-unsloth-q4-chat64k:latest",
 "qwen3.5:9b",
]

prompt="Reply with exactly: pong"
for m in models:
    payload={
      "model": m,
      "messages":[{"role":"user","content":prompt}],
      "stream": False,
PY      print({"model":m,"ok":False,"wall_s":round(dt,2),"error":str(e)[:140]})" "),"error":r.text[:140]})
{'model': 'qwen35-9b-32k:latest', 'ok': True, 'wall_s': 15.2, 'prompt_eval_count': 15, 'eval_count': 32, 'done_reason': 'length', 'head': ''}
{'model': 'qwen35-9b-q4-32k-chat:latest', 'ok': True, 'wall_s': 3.64, 'prompt_eval_count': 13, 'eval_count': 32, 'done_reason': 'length', 'head': '<think> Thinking Process:  1.  **Analyze the Request:**     *   Input: "Reply wi'}
{'model': 'qwen35-9b-q4-32k:latest', 'ok': True, 'wall_s': 3.15, 'prompt_eval_count': 5, 'eval_count': 14, 'done_reason': 'stop', 'head': 'pong<|endoftext|><|im_start|> <|im_start|> <|im_start|> <|im_start|> <|im_start|'}
{'model': 'qwen35-9b-q4-64k:latest', 'ok': True, 'wall_s': 3.51, 'prompt_eval_count': 5, 'eval_count': 12, 'done_reason': 'stop', 'head': 'pong<|endoftext|><|im_start|> <|im_start|> <|im_start|> <|im_start|>'}
{'model': 'nemotron4b-64k-clean:latest', 'ok': True, 'wall_s': 11.61, 'prompt_eval_count': 7, 'eval_count': 2, 'done_reason': 'stop', 'head': ''}
{'model': 'nemotron4b-64k:latest', 'ok': True, 'wall_s': 2.25, 'prompt_eval_count': 7, 'eval_count': 4, 'done_reason': 'stop', 'head': 'pong'}
{'model': 'qwen35-27b-unsloth-q4-chat64k:latest', 'ok': False, 'wall_s': 90.09, 'error': "HTTPConnectionPool(host='127.0.0.1', port=11556): Read timed out. (read timeout=90)"}
{'model': 'qwen3.5:9b', 'ok': True, 'wall_s': 17.1, 'prompt_eval_count': 15, 'eval_count': 32, 'done_reason': 'length', 'head': ''}
qtran47@atl1-1-03-006-23-0:AutoResearch-SMB$ 











qtran47@atl1-1-03-006-23-0:AutoResearch-SMB$ python - <<'PY'
import requests, json, re
host="http://127.0.0.1:11556"
models=["qwen3.5:9b","qwen35-9b-q4-32k:latest","qwen35-9b-q4-32k-chat:latest"]
for m in models:
    ok=0
    for _ in range(10):
        r=requests.post(f"{host}/api/chat",json={
            "model":m,
            "messages":[{"role":"system","content":"Return valid JSON only."},
                        {"role":"user","content":"Return {\"candidate_index\":0,\"reason\":\"ok\"}"}],
            "format":"json",
            "stream":False,
            "options":{"temperature":0,"num_predict":128}
        },timeout=60)
        if r.status_code!=200: 
            continue
        txt=(r.json().get("message",{}).get("content","") or "").strip()
        try:
            json.loads(txt); ok+=1
        except: pass
    print(m, f"{ok}/10 parse_ok")
PY
qwen3.5:9b 0/10 parse_ok
qwen35-9b-q4-32k:latest 10/10 parse_ok
qwen35-9b-q4-32k-chat:latest 10/10 parse_ok