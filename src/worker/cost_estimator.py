"""Pre-dispatch cost estimation for optimization jobs (D-08, D-09, D-10)."""

# Approximate cost per 1K tokens (input+output blended) by model
PRICE_PER_1K_TOKENS: dict[str, float] = {
    "gpt-4o": 0.005,
    "gpt-4o-mini": 0.00015,
    "gpt-4-turbo": 0.01,
    "claude-3-5-sonnet": 0.003,
}

# Conservative average tokens per LLM call (prompt + completion)
AVG_TOKENS_PER_CALL = 500


def estimate_optimization_cost(
    feedback_count: int,
    max_trials: int = 15,
    teacher_model: str = "gpt-4o",
    judge_model: str = "gpt-4o-mini",
) -> dict:
    """Estimate USD cost of an optimization run before dispatching.

    Formula (per D-10):
    - 80% of feedback goes to validation, 20% to training
    - Judge calls = max_trials * val_size * 3 (bias protection: 3 calls per example per D-18)
    - Teacher calls = max_trials * train_size * 2 (bootstrapping estimate)
    - Cost = (calls * avg_tokens_per_call / 1000) * price_per_1k_tokens
    """
    val_size = int(feedback_count * 0.8)
    train_size = feedback_count - val_size

    judge_calls = max_trials * val_size * 3
    teacher_calls = max_trials * train_size * 2

    teacher_price = PRICE_PER_1K_TOKENS.get(teacher_model, 0.005)
    judge_price = PRICE_PER_1K_TOKENS.get(judge_model, 0.00015)

    teacher_cost = (teacher_calls * AVG_TOKENS_PER_CALL / 1000) * teacher_price
    judge_cost = (judge_calls * AVG_TOKENS_PER_CALL / 1000) * judge_price

    total_cost = teacher_cost + judge_cost

    return {
        "estimated_cost_usd": round(total_cost, 2),
        "estimated_llm_calls": judge_calls + teacher_calls,
        "train_size": train_size,
        "val_size": val_size,
        "max_trials": max_trials,
        "teacher_model": teacher_model,
        "judge_model": judge_model,
    }
