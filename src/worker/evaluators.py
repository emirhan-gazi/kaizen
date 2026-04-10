"""Evaluator factory for DSPy optimization pipeline.

Supports 4 evaluator types: judge (LLM-as-judge with bias protections),
exact_match, custom_fn, and composite (weighted combination).

All functions are sync def -- never async def (Pitfall 7).
"""

import importlib
import logging
import random
import statistics
from typing import Any, Callable

import litellm

from src.config import Settings

logger = logging.getLogger(__name__)


def create_evaluator(task: Any, settings: Settings) -> Callable:
    """Return a DSPy-compatible metric fn: (example, prediction, trace=None) -> float.

    Evaluator type is determined by task.evaluator_config["type"].
    Defaults to "judge" if not specified (per D-14).
    """
    config = task.evaluator_config or {}
    eval_type = config.get("type", "judge")

    if eval_type == "judge":
        return _build_judge_evaluator(task, settings, config)
    elif eval_type == "exact_match":
        return _build_exact_match_evaluator()
    elif eval_type == "custom_fn":
        return _build_custom_fn_evaluator(config)
    elif eval_type == "composite":
        return _build_composite_evaluator(task, settings, config)
    else:
        raise ValueError(f"Unknown evaluator type: {eval_type}")


def _build_judge_evaluator(task: Any, settings: Settings, config: dict) -> Callable:
    """Build LLM-as-judge evaluator with bias protections.

    Per D-18 and Pitfall 4:
    - 3 separate LLM calls per example
    - Randomized response ordering in each call
    - Majority vote (median of 3 scores)
    - Explicit anti-verbosity instruction
    """
    judge_model = task.judge_model or settings.JUDGE_MODEL
    criteria = config.get(
        "criteria",
        "Score the quality of the response on a 0-1 scale.",
    )
    timeout = settings.LLM_TIMEOUT

    def judge_metric(example: Any, prediction: Any, trace: Any = None) -> float:
        """Score a prediction using LLM-as-judge with 3-call majority vote."""
        expected = getattr(example, "response", "")
        predicted = getattr(prediction, "response", "")
        input_text = _format_inputs(example)

        scores: list[float] = []
        for call_idx in range(3):
            # Randomize ordering to mitigate position bias (Pitfall 4)
            if random.random() < 0.5:
                option_a, option_b = expected, predicted
                label_a, label_b = "Expected", "Candidate"
            else:
                option_a, option_b = predicted, expected
                label_a, label_b = "Candidate", "Expected"

            prompt = (
                f"You are an expert evaluator. Score the Candidate response quality.\n\n"
                f"Task: {task.description or task.name}\n"
                f"Criteria: {criteria}\n\n"
                f"Input: {input_text}\n\n"
                f"Response A ({label_a}):\n{option_a}\n\n"
                f"Response B ({label_b}):\n{option_b}\n\n"
                f"IMPORTANT: Do not favor longer responses. Score based on quality, not length.\n\n"
                f"Score the Candidate response on a scale of 0.0 to 1.0.\n"
                f"Respond with ONLY a single decimal number between 0.0 and 1.0."
            )

            try:
                # Use litellm.completion() directly for raw control (not dspy.LM)
                # Explicit model= per Pitfall 11: no silent fallbacks
                response = litellm.completion(
                    model=judge_model,
                    messages=[{"role": "user", "content": prompt}],
                    timeout=timeout,
                    temperature=0.0,
                    api_base=settings.OPENAI_API_BASE or None,
                    api_key=settings.OPENAI_API_KEY,
                    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
                )
                score_text = response.choices[0].message.content.strip()
                score = _parse_score(score_text)
            except Exception as e:
                logger.warning(
                    "Judge call %d failed for job evaluation: %s", call_idx, e
                )
                score = 0.0

            scores.append(score)

        # Majority vote via median of 3 scores
        majority_score = statistics.median(scores)
        logger.debug(
            "Judge scores: %s -> majority: %.2f", scores, majority_score
        )
        return majority_score

    return judge_metric


def _build_exact_match_evaluator() -> Callable:
    """Build exact match evaluator (per D-15). Deterministic, no LLM calls."""

    def exact_match_metric(example: Any, prediction: Any, trace: Any = None) -> float:
        expected = getattr(example, "response", "")
        predicted = getattr(prediction, "response", "")
        return 1.0 if predicted == expected else 0.0

    return exact_match_metric


def _build_custom_fn_evaluator(config: dict) -> Callable:
    """Build custom function evaluator (per D-16).

    Loads function from config["function_path"], e.g. "my_module.my_scorer".
    Function signature: (inputs: dict, output: str, expected: str) -> float
    """
    function_path = config.get("function_path")
    if not function_path:
        raise ValueError("custom_fn evaluator requires 'function_path' in evaluator_config")

    # Split module path and function name
    parts = function_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"function_path must be 'module.function' format, got: {function_path}"
        )
    module_path, fn_name = parts
    mod = importlib.import_module(module_path)
    custom_fn = getattr(mod, fn_name)

    def custom_metric(example: Any, prediction: Any, trace: Any = None) -> float:
        inputs = {}
        # Extract input fields from example (all non-response fields)
        for key in example.keys():
            if key != "response":
                inputs[key] = getattr(example, key, "")
        expected = getattr(example, "response", "")
        predicted = getattr(prediction, "response", "")
        score = custom_fn(inputs=inputs, output=predicted, expected=expected)
        return float(score)

    return custom_metric


def _build_composite_evaluator(task: Any, settings: Settings, config: dict) -> Callable:
    """Build composite evaluator with weighted sub-evaluators (per D-17).

    Config example: {"type": "composite", "weights": {"judge": 0.7, "exact_match": 0.3}}
    """
    weights = config.get("weights")
    if not weights:
        raise ValueError("composite evaluator requires 'weights' in evaluator_config")

    # Build sub-evaluators
    sub_evaluators: list[tuple[Callable, float]] = []
    for eval_type, weight in weights.items():
        if eval_type == "judge":
            sub_eval = _build_judge_evaluator(task, settings, config)
        elif eval_type == "exact_match":
            sub_eval = _build_exact_match_evaluator()
        elif eval_type == "custom_fn":
            sub_eval = _build_custom_fn_evaluator(config)
        else:
            raise ValueError(f"Unknown sub-evaluator type in composite: {eval_type}")
        sub_evaluators.append((sub_eval, float(weight)))

    def composite_metric(example: Any, prediction: Any, trace: Any = None) -> float:
        total = 0.0
        for sub_fn, weight in sub_evaluators:
            score = sub_fn(example, prediction, trace)
            total += score * weight
        return total

    return composite_metric


def _parse_score(text: str) -> float:
    """Parse a float score from judge response text. Default 0.0 on failure."""
    try:
        # Try to extract a float from the response
        text = text.strip()
        # Handle cases like "0.8" or "Score: 0.8"
        for token in text.split():
            try:
                score = float(token)
                if 0.0 <= score <= 1.0:
                    return score
            except ValueError:
                continue
        # Last resort: try parsing the whole string
        score = float(text)
        return max(0.0, min(1.0, score))
    except (ValueError, TypeError):
        logger.warning("Failed to parse judge score from: %s", text)
        return 0.0


def batch_evaluate_traces(
    traces: list[Any],
    task: Any,
    settings: Settings,
) -> list[tuple[Any, float]]:
    """Batch auto-evaluate unscored traces using the task's evaluator (D-06, D-07).

    Args:
        traces: List of Trace ORM objects with prompt_text and response_text.
        task: Task ORM object with evaluator_config.
        settings: App settings.

    Returns:
        List of (trace, score) tuples. Scores are 0.0-1.0.
    """
    if not task.evaluator_config:
        logger.warning(
            "Task %s has auto_eval=True but no evaluator_config — skipping",
            task.id,
        )
        return []

    config = task.evaluator_config
    eval_type = config.get("type", "judge")

    if eval_type != "judge":
        logger.warning(
            "Batch auto-eval only supports 'judge' type, got '%s' — skipping",
            eval_type,
        )
        return []

    judge_model = task.judge_model or settings.JUDGE_MODEL
    criteria = config.get(
        "criteria",
        "Score the quality of the response on a 0-1 scale.",
    )
    timeout = settings.LLM_TIMEOUT

    results: list[tuple[Any, float]] = []
    for trace in traces:
        if not trace.prompt_text or not trace.response_text:
            results.append((trace, 0.0))
            continue

        prompt = (
            f"You are an expert evaluator.\n\n"
            f"Task: {task.description or task.name}\n"
            f"Criteria: {criteria}\n\n"
            f"Input prompt: {trace.prompt_text[:2000]}\n\n"
            f"Response: {trace.response_text[:2000]}\n\n"
            f"IMPORTANT: Do not favor longer responses. "
            f"Score based on quality, not length.\n\n"
            f"Score the response on a scale of 0.0 to 1.0.\n"
            f"Respond with ONLY a single decimal number between 0.0 and 1.0."
        )

        try:
            response = litellm.completion(
                model=judge_model,
                messages=[{"role": "user", "content": prompt}],
                timeout=timeout,
                temperature=0.0,
                api_base=settings.OPENAI_API_BASE or None,
                api_key=settings.OPENAI_API_KEY,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
            score_text = response.choices[0].message.content.strip()
            score = _parse_score(score_text)
        except Exception as exc:
            logger.warning("Auto-eval failed for trace %s: %s", trace.id, exc)
            score = 0.0

        results.append((trace, score))

    logger.info(
        "Batch auto-evaluated %d traces for task %s",
        len(results), task.id,
    )
    return results


def _format_inputs(example: Any) -> str:
    """Format example inputs as a readable string."""
    parts = []
    for key in example.keys():
        if key != "response":
            val = getattr(example, key, "")
            parts.append(f"{key}: {val}")
    return "\n".join(parts) if parts else str(example)
