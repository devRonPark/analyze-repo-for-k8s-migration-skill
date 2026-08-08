from .state import STAGES, derive_evidence_id
def validate_payload(stage,payload):
    if stage not in STAGES: raise ValueError("unknown stage")
    if not isinstance(payload,dict): raise ValueError("payload must be object")
    if payload.get("binding") is not None: raise ValueError("binding is server-owned")
    if payload.get("evidence"):
        for e in payload["evidence"]:
            if not isinstance(e,dict) or not e.get("source"): raise ValueError("evidence source required")
            if e.get("id") and e["id"] != derive_evidence_id({k:v for k,v in e.items() if k != "id"}): raise ValueError("forged evidence id")
    return payload
