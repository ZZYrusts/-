import importlib.metadata as md
for p in ("mcp","uiautomation","comtypes","pydantic","anyio","starlette","uvicorn","httpx","sse-starlette"):
    try: print(f"{p:16s} {md.version(p)}")
    except Exception as e: print(f"{p:16s} MISSING")
import mcp, os
print("\nmcp path:", os.path.dirname(mcp.__file__))
print("mcp dirs:", sorted(os.listdir(os.path.dirname(mcp.__file__))))
from mcp.server import fastmcp
print("FastMCP OK")
import inspect
from mcp.server.fastmcp import FastMCP
print("FastMCP.__init__ params:", list(inspect.signature(FastMCP.__init__).parameters))
print("run methods:", [m for m in dir(FastMCP) if 'run' in m.lower() or 'tool' in m.lower()])
