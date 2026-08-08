"""Provider-free MCP lifecycle smoke test."""
import json, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; PY=ROOT/'runtime'/'python'
def main():
    proc=subprocess.Popen([sys.executable,'-m','analysis_pipeline.mcp_server'],cwd=PY,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    def call(i,method,params=None):
        proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params or {}})+'\n'); proc.stdin.flush(); return json.loads(proc.stdout.readline())
    assert call(1,'initialize')['result']['serverInfo']['name']=='trusted-analysis-pipeline'
    assert [x['name'] for x in call(2,'tools/list')['result']['tools']]==['analysis_start']
    started=call(3,'tools/call',{'name':'analysis_start','arguments':{'binding':'smoke'}})['result']['structuredContent']; assert started['revision']==0
    names=[x['name'] for x in call(4,'tools/list')['result']['tools']]; assert 'analysis_discovery' in names and 'analysis_execution' not in names
    proc.terminate(); proc.wait(timeout=5); print('MCP smoke: PASS')
if __name__=='__main__': main()
