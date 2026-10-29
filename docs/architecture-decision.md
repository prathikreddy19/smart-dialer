# Architecture decision

## Decision

Use a modular FastAPI monolith, SQLAlchemy ORM, and MySQL 8 as the coordination store. Separate pacing, safety, allocation, state transition, provider, simulation, and metric code into small modules. Keep provider integrations behind one interface and ship two deterministic mock implementations.

## Why

The assignment is a local prototype. MySQL row locks, transactions, and uniqueness constraints are enough to show that two workers cannot claim the same agent or borrower and that duplicate provider events do not apply twice. A broker, Redis, or microservice would add operational setup without improving this demonstration.

## Safety invariant

One call is persisted with one reserved active agent before provider dispatch. The safety controller caps a pacing recommendation at the agents and borrowers the allocator successfully locks. Provider work happens after the reservation commit so network latency never holds database locks. If a worker disappears, the recovery endpoint cancels stale setup work and returns agents to `AVAILABLE`.

## Pacing

Predictive pacing uses open agent slots, a bounded historical answer-rate input, call duration, and provider health to recommend a count. It has no provider or database dependency. Safety is a separate object and always runs afterward. This prototype retains the hard one-call-per-reserved-agent bound; it demonstrates a predictive estimate and controlled reduction without claiming an unsafe increase in answered-call capacity.

## Data and duplicate policy

The supplied CSVs define the legacy entities and events. Duplicate primary keys are resolved once per import: exact rows collapse; conflicting rows use the newest `updated_at`, or the first row if there is no such field. Orphan references cannot be represented with enforced foreign keys, so affected rows are reported and skipped rather than fabricated or silently reassigned.

## Failure handling

- Provider timeout: mark the call failed, release the agent, and do not retry an uncertain provider submission.
- Duplicate/out-of-order event: provider event uniqueness and monotonic state transitions make handling idempotent.
- Worker crash during setup: stale in-flight calls are cancelled by recovery; a future real adapter should query the provider with the stable call ID before retrying.
- Availability drop: update the agent state and cancel its in-flight setup calls; future pacing reads current lockable agents.

## Scaling limits

The first likely limit is MySQL contention and the cost of finding eligible borrowers, not Python CPU. At 1,000 agents, profile lock wait, candidate query plans, and provider latency. At 10,000 agents, partition campaigns and borrower work deterministically and consider a transactional outbox plus workers only if measurements justify it.
