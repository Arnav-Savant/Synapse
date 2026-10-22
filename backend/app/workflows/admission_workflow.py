"""Limits how many ingest pipelines execute at once (spec §8.1).

One long-lived workflow, id `pipeline-admission`. Job workflows signal
`acquire` and `release`; it grants slots first-in-first-out by signalling the
job workflow's `slot_granted`. A job sitting at an owner gate has released
its slot, so waiting on the owner never blocks the queue. Duplicate acquires
and releases are ignored, so retries and cancellations cannot corrupt it.
"""

from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from app.workflows.models import ADMISSION_CONTINUE_AS_NEW_AFTER, MAX_ACTIVE_PIPELINES, AdmissionState


@workflow.defn
class PipelineAdmissionWorkflow:
    def __init__(self) -> None:
        self._waiting: list[str] = []
        self._active: list[str] = []
        self._signals = 0

    @workflow.signal
    def acquire(self, job_workflow_id: str) -> None:
        self._signals += 1
        if job_workflow_id not in self._waiting and job_workflow_id not in self._active:
            self._waiting.append(job_workflow_id)

    @workflow.signal
    def release(self, job_workflow_id: str) -> None:
        self._signals += 1
        if job_workflow_id in self._waiting:
            self._waiting.remove(job_workflow_id)
        if job_workflow_id in self._active:
            self._active.remove(job_workflow_id)

    @workflow.query
    def state(self) -> AdmissionState:
        return AdmissionState(waiting=list(self._waiting), active=list(self._active))

    def _can_grant(self) -> bool:
        return bool(self._waiting) and len(self._active) < MAX_ACTIVE_PIPELINES

    def _should_restart(self) -> bool:
        return self._signals >= ADMISSION_CONTINUE_AS_NEW_AFTER

    @workflow.run
    async def run(self, state: AdmissionState | None = None) -> None:
        if state is not None:
            self._waiting, self._active = list(state.waiting), list(state.active)
        while True:
            await workflow.wait_condition(lambda: self._can_grant() or self._should_restart())
            while self._can_grant():
                job_id = self._waiting.pop(0)
                self._active.append(job_id)
                try:
                    await workflow.get_external_workflow_handle(job_id).signal("slot_granted")
                    workflow.logger.info("pipeline slot granted to %s (%d active, %d waiting)", job_id[:8], len(self._active), len(self._waiting))
                except Exception as exc:  # the job workflow has already ended; do not keep its slot
                    self._active.remove(job_id)
                    workflow.logger.warning("could not grant a slot to %s (workflow gone?): %s", job_id[:8], exc)
            if self._should_restart():
                await workflow.wait_condition(workflow.all_handlers_finished)
                workflow.continue_as_new(AdmissionState(waiting=list(self._waiting), active=list(self._active)))
