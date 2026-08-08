import re
from .safe_paths import safe_path
SECRET=re.compile(r"(password|passwd|secret|token|api[_ -]?key|private[_ -]?key)(\s*[:=]\s*)([^\s,;]+)",re.I)
SQL=re.compile(r"'(?:''|[^'])*'")
DEFAULT_LINE_LIMIT = 120
MAX_LINE_LIMIT = 200
MAX_LINE_CHARS = 4_000
MAX_OUTPUT_CHARS = 24_000


def render_lines(lines, offset=0, limit=None):
    start = max(0, int(offset or 0))
    requested = DEFAULT_LINE_LIMIT if limit is None else int(limit)
    count = min(MAX_LINE_LIMIT, max(1, requested))
    output = []
    output_size = 0
    for index, line in enumerate(lines[start:start + count], start + 1):
        clipped = line[:MAX_LINE_CHARS]
        suffix = " [LINE_TRUNCATED]" if len(line) > len(clipped) else ""
        rendered = f"{index}: {clipped}{suffix}"
        if output_size + len(rendered) + 1 > MAX_OUTPUT_CHARS:
            output.append(f"{index}: [TRUNCATED output limit reached; use offset for the next range]")
            return "\n".join(output)
        output.append(rendered)
        output_size += len(rendered) + 1
    if len(lines) > start + len(output):
        output.append(f"{start + len(output) + 1}: [TRUNCATED use offset for the next range]")
    return "\n".join(output)


def redact_text(value, suffix=""):
    value = SECRET.sub(lambda m:m.group(1)+m.group(2)+'[REDACTED]', value)
    return SQL.sub("'[REDACTED]'", value) if suffix.lower()=='.sql' else value


def read(worktree,path,offset=0,limit=None,trusted_roots=(),observation_registry=None,stage=None):
    target=safe_path(worktree,path,trusted_roots)
    if target.is_dir(): return "\n".join(sorted(x.name for x in target.iterdir()))
    lines=target.read_text(encoding="utf-8").splitlines()
    rendered = render_lines([redact_text(line, target.suffix) for line in lines], offset, limit)
    if observation_registry is None:
        return rendered
    start = max(0, int(offset or 0)) + 1
    requested = DEFAULT_LINE_LIMIT if limit is None else int(limit)
    end = min(len(lines), start + min(MAX_LINE_LIMIT, max(1, requested)) - 1)
    return {"text": rendered, **observation_registry.issue_present(stage, target, start, end, rendered)}
