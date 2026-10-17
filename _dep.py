import importlib
for m in ("mcp","uiautomation","comtypes"):
    try:
        mod = importlib.import_module(m)
        v = getattr(mod, "__version__", "n/a")
        print(f"OK   {m:14s} {v}  {getattr(mod,'__file__','')}")
    except Exception as e:
        print(f"FAIL {m:14s} {type(e).__name__}: {e}")
