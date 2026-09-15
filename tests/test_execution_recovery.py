import pytest

from src.domain import ExecutionStatus, TargetResponse, TargetType
from src.execution import ExecutionEngine, ExecutionPolicy
from src.targets import TargetAdapter


class HTTPFailure(TargetAdapter):
    target_type = TargetType.EXTERNAL_API
    version = "failure-v1"

    def __init__(self, status):
        self.status = status
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return TargetResponse(status=ExecutionStatus.FAILED, http_status=self.status)


@pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
def test_non_transient_client_error_is_not_blindly_retried(status):
    target = HTTPFailure(status)
    record = ExecutionEngine(target, ExecutionPolicy(max_retries=2), sleep=lambda _: None).run([{"case_id": "one"}])[0]
    assert target.calls == record.attempt_count == 1
    assert record.status == ExecutionStatus.FAILED


@pytest.mark.parametrize("status", [408, 429, 500, 503])
def test_transient_errors_retain_bounded_retries(status):
    target = HTTPFailure(status)
    record = ExecutionEngine(target, ExecutionPolicy(max_retries=2), sleep=lambda _: None).run([{"case_id": "one"}])[0]
    assert target.calls == record.attempt_count == 3
