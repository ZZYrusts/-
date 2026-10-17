import urllib.request, os, json
for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy","ALL_PROXY","all_proxy"):
    os.environ.pop(k, None)
tests = [
 ("tuna","https://pypi.tuna.tsinghua.edu.cn/simple/mcp/"),
 ("aliyun","https://mirrors.aliyun.com/pypi/simple/mcp/"),
 ("tencent","https://mirrors.cloud.tencent.com/pypi/simple/mcp/"),
 ("ustc","https://pypi.mirrors.ustc.edu.cn/simple/mcp/"),
 ("pypi","https://pypi.org/simple/mcp/"),
]
for name,u in tests:
    try:
        req = urllib.request.Request(u, headers={"User-Agent":"pip/26.2.1"})
        r = urllib.request.urlopen(req, timeout=10)
        print(name, "OK", r.status, len(r.read()))
    except Exception as e:
        print(name, "FAIL", type(e).__name__, str(e)[:80])
