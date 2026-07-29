# Configuration Timing

Classify each major configuration name by when it takes effect:

- `빌드 시점`: included during compilation, image creation, or static bundle
  generation;
- `배포 시점`: selected or rendered by the deployment tool before workload
  creation;
- `프로세스 시작 시점`: read when the process starts and changed by restart or
  rollout;
- `실행 중`: reread without process restart;
- `관리 시점`: applied by an external control plane or manual management action;
- `미확인`: the repository evidence cannot determine the timing.

For each important configuration, record its name, component, purpose, timing,
source or injection method, change effect, secret classification without
revealing values, evidence status, and evidence.

Do not assume every environment variable is process-start configuration. Frontend
variables such as Vite build arguments are often build-time values embedded in
static assets.
