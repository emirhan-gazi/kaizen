"""PR body template builder for auto-generated optimization PRs.

Builds a self-contained PR description so engineers can make merge/reject
decisions purely from the PR body without visiting the dashboard (D-05).

Sections: score comparison (D-06), prompt diff (D-07), few-shot examples (D-08),
job metadata (D-09). Title follows conventional-commit style (D-10).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PRContext:
    """All data needed to render a PR title and body."""

    task_name: str
    version_number: int
    before_score: float | None
    after_score: float
    feedback_count: int
    optimizer: str
    teacher_model: str
    judge_model: str
    trials_completed: int
    duration_seconds: float
    train_size: int
    val_size: int
    old_prompt_text: str | None
    new_prompt_text: str
    few_shot_examples: list[dict] | None
    job_id: str
    dspy_version: str | None = None
    litellm_version: str | None = None
    cost_usd: float | None = None
    judge_score: float | None = None


def build_pr_title(ctx: PRContext) -> str:
    """Build PR title in conventional-commit style (D-10).

    Format: tune({task_name}): optimize prompt v{version} (+{delta}% score)
    """
    if ctx.before_score is not None and ctx.before_score > 0:
        delta = ((ctx.after_score - ctx.before_score) / ctx.before_score) * 100
        delta_str = f"+{delta:.1f}" if delta >= 0 else f"{delta:.1f}"
    else:
        delta_str = "new"

    return (
        f"tune({ctx.task_name}): optimize prompt "
        f"v{ctx.version_number} ({delta_str}% score)"
    )


def build_pr_body(ctx: PRContext) -> str:
    """Build the full PR body with all four sections (D-05 through D-09)."""
    sections = [
        _section_score_comparison(ctx),
        _section_prompt_diff(ctx),
        _section_few_shot_examples(ctx),
        _section_job_metadata(ctx),
        _section_footer(),
    ]
    return "\n\n".join(sections)


def _section_score_comparison(ctx: PRContext) -> str:
    """Section 1: Before/after eval score with delta (D-06)."""
    lines = ["## Score Comparison", ""]

    if ctx.before_score is not None:
        delta = ctx.after_score - ctx.before_score
        pct = ((delta / ctx.before_score) * 100) if ctx.before_score > 0 else 0
        direction = "improved" if delta > 0 else "regressed" if delta < 0 else "unchanged"

        lines.append("| Metric | Before | After | Delta |")
        lines.append("|--------|--------|-------|-------|")
        lines.append(
            f"| Dataset Score | {ctx.before_score:.4f} | {ctx.after_score:.4f} "
            f"| {'+' if delta >= 0 else ''}{delta:.4f} ({'+' if pct >= 0 else ''}{pct:.1f}%) |"
        )
        if ctx.judge_score is not None:
            lines.append(f"| Judge Score | — | {ctx.judge_score:.4f} | — |")
        lines.append("")
        lines.append(f"**Result:** Score {direction}")
    else:
        lines.append("| Metric | Score |")
        lines.append("|--------|-------|")
        lines.append(f"| Dataset Score | {ctx.after_score:.4f} |")
        if ctx.judge_score is not None:
            lines.append(f"| Judge Score | {ctx.judge_score:.4f} |")
        lines.append("")
        lines.append("**Result:** First optimization (no prior baseline)")

    return "\n".join(lines)


def _section_prompt_diff(ctx: PRContext) -> str:
    """Section 2: Full text diff of old vs new prompt (D-07)."""
    lines = ["## Prompt Diff", ""]

    if ctx.old_prompt_text:
        lines.append("**Before:**")
        lines.append("```")
        lines.append(ctx.old_prompt_text)
        lines.append("```")
        lines.append("")

    lines.append("**After:**")
    lines.append("```")
    lines.append(ctx.new_prompt_text)
    lines.append("```")

    return "\n".join(lines)


def _section_few_shot_examples(ctx: PRContext) -> str:
    """Section 3: Bootstrapped few-shot examples from DSPy (D-08)."""
    lines = ["## Few-Shot Examples", ""]

    if not ctx.few_shot_examples:
        lines.append("No few-shot examples were selected by the optimizer.")
        return "\n".join(lines)

    # Truncate to at most 5 examples to keep PR readable
    shown = ctx.few_shot_examples[:5]
    total = len(ctx.few_shot_examples)

    for i, example in enumerate(shown, 1):
        lines.append(f"### Example {i}")
        lines.append("")
        for key, value in example.items():
            text = str(value)
            if len(text) > 500:
                text = text[:500] + "... (truncated)"
            lines.append(f"- **{key}:** {text}")
        lines.append("")

    if total > 5:
        lines.append(f"*Showing 5 of {total} examples. See full details in the dashboard.*")

    return "\n".join(lines)


def _section_job_metadata(ctx: PRContext) -> str:
    """Section 4: Optimizer name, trials, feedback, model, duration (D-09)."""
    lines = ["## Job Metadata", ""]

    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Job ID | `{ctx.job_id}` |")
    lines.append(f"| Optimizer | {ctx.optimizer} |")
    lines.append(f"| Trials | {ctx.trials_completed} |")
    lines.append(f"| Feedback entries | {ctx.feedback_count} |")
    lines.append(f"| Train / Val split | {ctx.train_size} / {ctx.val_size} |")
    lines.append(f"| Teacher model | {ctx.teacher_model} |")
    lines.append(f"| Judge model | {ctx.judge_model} |")
    lines.append(f"| Duration | {ctx.duration_seconds:.1f}s |")

    if ctx.cost_usd is not None:
        lines.append(f"| Estimated cost | ${ctx.cost_usd:.4f} |")
    if ctx.dspy_version:
        lines.append(f"| DSPy version | {ctx.dspy_version} |")
    if ctx.litellm_version:
        lines.append(f"| LiteLLM version | {ctx.litellm_version} |")

    return "\n".join(lines)


def _section_footer() -> str:
    """Footer with auto-generation notice."""
    return (
        "---\n"
        "*This PR was auto-generated by [Kaizen](https://github.com/kaizen-prompt). "
        "Review the prompt changes above before merging.*"
    )
