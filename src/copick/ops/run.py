from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Iterable, Literal, Union

from tqdm.auto import tqdm

from copick.models import CopickRoot, CopickRun
from copick.util.log import get_logger

logger = get_logger(__name__)


def _materialize_run(root: CopickRoot, run: str, run_args: Dict[str, Any], callback: Callable, **kwargs) -> Any:
    run = root.get_run(name=run)
    return callback(run, **run_args, **kwargs)


def map_runs(
    callback: Callable,
    root: CopickRoot,
    runs: Union[Iterable[str], Iterable[CopickRun]],
    workers: int = 8,
    parallelism: Literal["thread", "process"] = "thread",
    run_args: Iterable[Dict[str, Any]] = None,
    show_progress: bool = True,
    task_desc: str = None,
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

    if parallelism == "thread":
        executor_class = ThreadPoolExecutor
    elif parallelism == "process":
        executor_class = ProcessPoolExecutor
    else:
        logger.critical(f"Invalid parallelism type: {parallelism}, must be 'thread' or 'process'")
        raise ValueError(f"Invalid parallelism type: {parallelism}, must be 'thread' or 'process'")

    with executor_class(max_workers=workers) as executor:
        # TODO: zip(..., strict=True)
        if len(list(runs)) != len(run_args):
            logger.critical("Length of runs and run_args must be the same.")
            raise ValueError("Length of runs and run_args must be the same.")

        for run, rargs in zip(runs, run_args):
            if isinstance(run, str):
                future = executor.submit(_materialize_run, root, run, rargs, callback, **kwargs)
                results[future] = run
            elif isinstance(run, CopickRun):
                future = executor.submit(callback, run, **rargs, **kwargs)
                results[future] = run.name
            else:
                logger.critical(f"Invalid run type: {type(run)}")
                raise ValueError(f"Invalid run type: {type(run)}")

        ret = {}
        for fut in tqdm(
            as_completed(results),
            total=len(results),
            desc=task_desc,
            unit="runs",
            disable=not show_progress,
        ):
            run_name = results[fut]
            try:
                ret[run_name] = fut.result()
            except Exception as e:
                logger.error(f"Error processing run {run_name}", exc_info=e)
                ret[run_name] = None

    return ret


def report_results(
    results: Dict[str, Any],
    total_files: int,
    logger=None,
) -> None:
    """
    Report the results of parallel processing operations.

    Args:
        results: Results dictionary from map_runs
        total_files: Total number of files that were supposed to be processed
        logger: Logger instance
    """
    total_processed = 0
    all_errors = []

    # Collect results
    for run_name, result in results.items():
        if result is None:
            all_errors.append(f"Run {run_name} failed completely")
        else:
            total_processed += result["processed"]
            all_errors.extend(result["errors"])

    # Report results
    if all_errors:
        logger.error(f"Failed to process {len(all_errors)} items:")
        for error in all_errors:
            logger.error(error)

        if total_processed > 0:
            logger.info(f"Successfully processed {total_processed} out of {total_files} items")
    else:
        logger.info(f"Successfully processed all {total_processed} items")
