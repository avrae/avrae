from concurrent.futures import ProcessPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
import logging
from math import ceil, floor, sqrt
from typing import Any

import draconic


class SafeEvalTimeout(Exception):
    pass


@dataclass
class SafeCaster:
    attacks: list[str]
    name: str = ""


_SAFE_EVAL_POOL = ProcessPoolExecutor(max_workers=1)
log = logging.getLogger(__name__)
_SAFE_BUILTINS = {
    "floor": floor,
    "ceil": ceil,
    "round": round,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "len": len,
    "max": max,
    "min": min,
    "enumerate": enumerate,
    "range": range,
    "sqrt": sqrt,
    "sum": sum,
    "any": any,
    "all": all,
    "abs": abs,
    "sorted": sorted,
    "reversed": reversed,
    "map": map,
    "filter": filter,
    "zip": zip,
}


def _evaluate_expr(expr: str, names: dict[str, Any]) -> Any:
    evaluator = draconic.SimpleInterpreter(builtins={**_SAFE_BUILTINS, **names})
    return evaluator.eval(expr)


def eval_expr(expr: str, names: dict[str, Any], timeout_seconds: float) -> Any:
    log.debug("safe_eval.start timeout=%ss expr=%r", timeout_seconds, expr)
    future = _SAFE_EVAL_POOL.submit(_evaluate_expr, expr, names)
    try:
        result = future.result(timeout=timeout_seconds)
        log.debug("safe_eval.success expr=%r", expr)
        return result
    except FutureTimeoutError as exc:
        future.cancel()
        log.warning("safe_eval.timeout timeout=%ss expr=%r", timeout_seconds, expr)
        raise SafeEvalTimeout(f"Evaluation timed out after {timeout_seconds:g}s.") from exc
    except Exception:
        log.exception("safe_eval.error expr=%r", expr)
        raise
