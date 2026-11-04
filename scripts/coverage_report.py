"""Statement coverage with the standard library only (coverage.py is not required).

Usage: python scripts/coverage_report.py   (from the repository root)
"""
import sys, os, unittest, ast, collections
root=os.getcwd(); hits=collections.defaultdict(set)
targets={os.path.join(dp,f) for dp,_,fs in os.walk("plantproof") for f in fs if f.endswith(".py")} | {os.path.join(root,"app.py"), os.path.join(root,"reliability_ui.py")}; targets={os.path.abspath(t) for t in targets if os.path.exists(t)}
def tr(frame, event, arg):
    f=frame.f_code.co_filename
    if f in targets:
        if event=="line": hits[f].add(frame.f_lineno)
        return tr
    return None
sys.settrace(tr)
import threading; threading.settrace(tr)
suite=unittest.defaultTestLoader.discover("tests", top_level_dir=".")
unittest.TextTestRunner(stream=open(os.devnull,"w")).run(suite)
sys.settrace(None)
def exec_lines(path):
    src=open(path).read(); lines=set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.stmt) and not isinstance(node,(ast.FunctionDef,ast.ClassDef,ast.AsyncFunctionDef)):
            lines.add(node.lineno)
    # drop docstring-only expr
    return lines
tot_e=tot_h=0
for p in sorted(targets):
    e=exec_lines(p); h=hits[p]&e
    tot_e+=len(e); tot_h+=len(h)
    print(f"{os.path.relpath(p):32} {len(h):4}/{len(e):4}  {100*len(h)/max(1,len(e)):5.1f}%")
print(f"TOTAL {tot_h}/{tot_e} {100*tot_h/tot_e:.1f}%")
