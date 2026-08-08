from dataclasses import replace
from .state import STAGES, PipelineState
from .validation import validate_payload
def _check(s,rev,h):
    if s.finalized: raise ValueError("finalized")
    if rev != s.revision or h != s.digest(): raise ValueError("stale state")
def submit(state,stage,payload,expected_revision,expected_hash):
    _check(state,expected_revision,expected_hash); validate_payload(stage,payload)
    if stage in state.outputs: raise ValueError("duplicate stage")
    idx=STAGES.index(stage)
    if idx != len(state.outputs): raise ValueError("stage order")
    out=dict(state.outputs); out[stage]=payload
    return replace(state,revision=state.revision+1,outputs=out)
def reopen(state,target_stage,reason,expected_revision,expected_hash):
    _check(state,expected_revision,expected_hash)
    if target_stage not in state.outputs or not isinstance(reason,str) or not reason or len(reason)>500: raise ValueError("invalid reopen")
    out={k:v for k,v in state.outputs.items() if STAGES.index(k)<STAGES.index(target_stage)}
    return replace(state,revision=state.revision+1,outputs=out)
def finalize(state,expected_revision,expected_hash):
    _check(state,expected_revision,expected_hash)
    if len(state.outputs)!=len(STAGES): raise ValueError("incomplete")
    return replace(state,revision=state.revision+1,finalized=True)
