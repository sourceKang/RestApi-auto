from __future__ import annotations

from dataclasses import dataclass


class OntInventoryPreconditionError(AssertionError):
    """Raised when inventory verification needs an EMS-owned ONT service seed."""


@dataclass
class OntServiceWorkflowState:
    template: str | None = None
    post_attempted: bool = False
    post_succeeded: bool = False
    post_failure: str = ""
    inventory_ready: bool = False
    readiness_failure: str = ""
    readiness_precondition: str = ""
    deleted: bool = False

    def begin_post(self, template: str) -> None:
        self.template = str(template)
        self.post_attempted = True
        self.post_succeeded = False
        self.post_failure = ""
        self.inventory_ready = False
        self.readiness_failure = ""
        self.readiness_precondition = ""
        self.deleted = False

    def complete_post(self) -> None:
        self.post_succeeded = True

    def fail_post(self, error: BaseException) -> None:
        self.post_failure = str(error)

    def mark_inventory_ready(self, template: str) -> None:
        self.template = str(template)
        self.inventory_ready = True
        self.readiness_failure = ""
        self.readiness_precondition = ""

    def fail_readiness(self, error: BaseException) -> None:
        self.readiness_failure = str(error)
        self.readiness_precondition = ""
        self.inventory_ready = False

    def block_readiness_precondition(self, error: BaseException) -> None:
        self.readiness_precondition = str(error)
        self.readiness_failure = ""
        self.inventory_ready = False

    def mark_deleted(self) -> None:
        self.deleted = True
        self.inventory_ready = False
