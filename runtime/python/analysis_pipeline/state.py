from dataclasses import dataclass, replace
import hashlib, json
STAGES=("inventory","build","runtime","network","state","risks")
def canonical_json(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",",":"))
def derive_evidence_id(value): return hashlib.sha256(canonical_json(value).encode()).hexdigest()
@dataclass(frozen=True)
class PipelineState:
    binding: str; revision: int=0; outputs: dict=None; evidence: tuple=(); finalized: bool=False
    def __post_init__(self):
        if self.outputs is None: object.__setattr__(self,"outputs",{})
    def digest(self): return hashlib.sha256(canonical_json({"binding":self.binding,"revision":self.revision,"outputs":self.outputs,"evidence":self.evidence,"finalized":self.finalized}).encode()).hexdigest()
def create_state(binding):
    if not isinstance(binding,str) or not binding: raise ValueError("binding required")
    return PipelineState(binding)
