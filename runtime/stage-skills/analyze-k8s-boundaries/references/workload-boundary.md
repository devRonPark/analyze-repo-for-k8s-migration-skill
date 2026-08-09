# Workload Boundary Decision

A Workload Unit is an application process operated independently. Treat two
runtime processes as separate units only when both have distinct production
start definitions and independent lifecycle operations. State, security,
resource, network, directory, package, port, dependency, or Secret differences
alone never establish a boundary. Record insufficient evidence as `미확인` with
its `검색(...)` scope rather than inferring a boundary from names.

Keep boundary, lifecycle, and state claims independent: a confirmed boundary
may have an unknown state decision. Summary records only the unit, deployable
status, state decision, and scoped unknowns. Detailed additionally records the
two boundary conditions, lifecycle, candidate inclusion or exclusion, and
supporting evidence.
