from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GeServiceWorkflowState:
    template: str | None = None
    post_attempted: bool = False
    post_succeeded: bool = False
    post_failure: str = ""
    cli_verified: bool = False
    cli_failure: str = ""
    put_succeeded: bool = False
    put_cli_verified: bool = False
    put_failure: str = ""
    put_running_config: str = ""
    patch_succeeded: bool = False
    patch_failure: str = ""
    deleted: bool = False

    def begin_post(self, template: str) -> None:
        self.template = str(template)
        self.post_attempted = True
        self.post_succeeded = False
        self.post_failure = ""
        self.cli_verified = False
        self.cli_failure = ""
        self.put_succeeded = False
        self.put_cli_verified = False
        self.put_failure = ""
        self.put_running_config = ""
        self.patch_succeeded = False
        self.patch_failure = ""
        self.deleted = False

    def complete_post(self) -> None:
        self.post_succeeded = True

    def fail_post(self, error: BaseException) -> None:
        self.post_failure = str(error)
        self.post_succeeded = False

    def complete_cli(self) -> None:
        self.cli_verified = True
        self.cli_failure = ""

    def fail_cli(self, error: BaseException) -> None:
        self.cli_failure = str(error)
        self.cli_verified = False

    def complete_put(self, running_config: str) -> None:
        self.put_succeeded = True
        self.put_cli_verified = True
        self.put_failure = ""
        self.put_running_config = running_config

    def fail_put(self, error: BaseException) -> None:
        self.put_failure = str(error)
        self.put_succeeded = False
        self.put_cli_verified = False
        self.put_running_config = ""

    def complete_patch(self) -> None:
        self.patch_succeeded = True
        self.patch_failure = ""

    def fail_patch(self, error: BaseException) -> None:
        self.patch_failure = str(error)
        self.patch_succeeded = False

    def mark_deleted(self) -> None:
        self.deleted = True
        self.cli_verified = False
        self.put_cli_verified = False