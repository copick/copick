from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Iterable, Union

from copick.models import CopickRoot, CopickRun


def _materialize_run(root: CopickRoot, run: str, run_args: Dict[str, Any], callback: Callable, **kwargs) -> Any:
    run = root.get_run(name=run)
    return callback(run, **run_args, **kwargs)


def map_runs(
    callback: Callable,
    root: CopickRoot,
    runs: Union[Iterable[str], Iterable[CopickRun]],
    workers: int = 8,
    run_args: Iterable[Dict[str, Any]] = None,
    **kwargs,
) -> Dict[str, Any]:
    """Execute a callback function on a list of runs in parallel.

    Args:
        callback: The callback function to execute. Must have the signature
        `callback(run: CopickRun, **run_args, **kwargs) -> Any`.
        root: The copick project root.
        runs: The list of run names or CopickRun objects to parallelize over.
        workers: The number of workers (threads) to use.
        run_args: List of run-specific arguments, must have same length as runs.
        **kwargs: Additional keyword arguments to pass to the callback function.
    """

    if run_args is None:
        run_args = [{} for _ in runs]

    results = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        # TODO: zip(..., strict=True)
        for run, rargs in zip(runs, run_args):
            if isinstance(run, str):
                results[run] = executor.submit(_materialize_run, root, run, rargs, callback, **kwargs)
            elif isinstance(run, CopickRun):
                results[run] = executor.submit(callback, run, **rargs, **kwargs)
            else:
                raise ValueError(f"Invalid run type: {type(run)}")

    return {run: result() for run, result in results.items()}
