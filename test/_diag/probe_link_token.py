import json, sys, urllib.request, urllib.error
sys.path.insert(0, "/Users/lute/project/audit_multi_content/tools")
import feishu_index as fi

tok = fi.token_of()
BASE = "https://open.feishu.cn/open-apis"
TOKEN = "IWbobAGHAoDcycxRFWNcBYd1nY6"

def req(url, payload=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    r = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    r.add_header("Authorization", f"Bearer {tok}")
    if data: r.add_header("Content-Type", "application/json; charset=utf-8")
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"_http": e.code, "body": e.read().decode()[:400]}
    except Exception as e:
        return {"_err": f"{type(e).__name__}: {e}"}

print("== drive metas (doc_type=file)")
print(json.dumps(req(f"{BASE}/drive/v1/metas/batch_query", {"request_docs":[{"doc_token":TOKEN,"doc_type":"file"}],"with_url":True}), ensure_ascii=False)[:1200])

print("== drive metas (doc_type=docx)")
print(json.dumps(req(f"{BASE}/drive/v1/metas/batch_query", {"request_docs":[{"doc_token":TOKEN,"doc_type":"docx"}],"with_url":True}), ensure_ascii=False)[:600])

print("== docx raw_content")
r = req(f"{BASE}/docx/v1/documents/{TOKEN}/raw_content")
print(json.dumps({k:v for k,v in r.items() if k!='data'}, ensure_ascii=False)[:600])
if r.get("code")==0:
    c = r["data"].get("content","")
    print("content chars=", len(c))
    print(c[:600])
