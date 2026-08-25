from __future__ import annotations

from sztu_code.core.workflow.model import (
    SingleAgentBaseline,
    WorkflowComparison,
    WorkflowResult,
)


# 用相同场景的结构化证据、完成检查、Token 和耗时比较多智能体与单 Agent 基线
def compare_with_single_agent(
    result: WorkflowResult,
    baseline: SingleAgentBaseline,
) -> WorkflowComparison:
    succeeded = [state for state in result.tasks if state.status == "succeeded"]
    tester_states = [state for state in succeeded if state.task.owner == "tester"]
    reviewer_states = [state for state in succeeded if state.task.owner == "reviewer"]
    workflow_checks = sum(len(state.task.completion_criteria) for state in succeeded)
    has_test = any(
        state.artifact is not None
        and bool(state.artifact.commands)
        and bool(state.artifact.conclusion.strip())
        for state in tester_states
    )
    has_review = any(
        state.artifact is not None
        and state.artifact.review_decision == "accept"
        and bool(state.artifact.diff_summary.strip())
        and bool(state.artifact.test_summary.strip())
        and bool(state.artifact.security_summary.strip())
        for state in reviewer_states
    )
    return WorkflowComparison(
        scenario_id=baseline.scenario_id,
        workflow_completion_checks=workflow_checks,
        baseline_completion_checks=baseline.completion_checks,
        workflow_has_independent_test=has_test,
        baseline_has_independent_test=baseline.independent_test_evidence,
        workflow_has_independent_review=has_review,
        baseline_has_independent_review=baseline.independent_review_evidence,
        workflow_trace_handoffs=sum(
            state.artifact is not None for state in result.tasks
        ),
        baseline_trace_handoffs=baseline.trace_handoffs,
        workflow_tokens=result.total_tokens,
        baseline_tokens=baseline.tokens,
        workflow_elapsed_s=result.elapsed_s,
        baseline_elapsed_s=baseline.elapsed_s,
    )
