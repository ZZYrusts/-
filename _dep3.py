import inspect
try:
    from mcp.server.fastmcp import FastMCP
    print("FastMCP import OK")
    print("init params:", list(inspect.signature(FastMCP.__init__).parameters))
    m = FastMCP("t")
    print("tool:", hasattr(m,'tool'), "run:", [x for x in dir(m) if x.startswith('run')])
    print("tool sig:", inspect.signature(m.tool))
    print("run sig:", inspect.signature(m.run))
except Exception as e:
    print("FastMCP FAIL:", type(e).__name__, e)
try:
    from mcp.server import MCPServer
    print("MCPServer OK", inspect.signature(MCPServer.__init__))
except Exception as e:
    print("MCPServer FAIL:", e)
