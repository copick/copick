import click

from copick.cli.util import add_config_option, add_debug_option
from copick.util.log import get_logger


@click.command(short_help="Create a depositable view of a copick project using symlinks.")
@add_config_option
@click.option(
    "--target-dir",
    type=str,
    help="Target directory for the deposited view (required).",
    required=True,
    metavar="PATH",
)
@click.option(
    "--run-names",
    type=str,
    help="Comma-separated list of specific run names to process. If not specified, processes all runs.",
    default="",
    show_default=True,
)
@click.option(
    "--run-name-prefix",
    type=str,
    help="Prefix to prepend to all run names. For data portal projects, if not provided, automatically constructs '{dataset_id}_{portal_run_name}_' for each run.",
    default="",
    show_default=True,
)
@click.option(
    "--run-name-regex",
    type=str,
    help="Optional regex to define how to extract run names from copick run names. Run names will be extracted from the first group defined using parentheses in the pattern.",
    default=None,
)
@click.option(
    "--picks",
    type=str,
    multiple=True,
    help="URIs to filter picks (e.g., 'proteasome:*/*' or 'ribosome:user1/*'). Can be specified multiple times. If not specified, skips picks entirely.",
)
@click.option(
    "--meshes",
    type=str,
    multiple=True,
    help="URIs to filter meshes. Can be specified multiple times. If not specified, skips meshes entirely.",
)
@click.option(
    "--segmentations",
    type=str,
    multiple=True,
    help="URIs to filter segmentations (e.g., 'membrane:*/*@10.0'). Can be specified multiple times. If not specified, skips segmentations entirely.",
)
@click.option(
    "--tomograms",
    type=str,
    multiple=True,
    help="URIs to filter tomograms (e.g., 'wbp@10.0'). Can be specified multiple times. If not specified, skips tomograms entirely.",
)
@click.option(
    "--features",
    type=str,
    multiple=True,
    help="URIs to filter features (e.g., 'wbp@10.0:cellcanvas'). Can be specified multiple times. If not specified, skips features entirely.",
)
@click.option(
    "--max-workers",
    type=int,
    help="Number of parallel workers for processing runs.",
    default=8,
    show_default=True,
)
@add_debug_option
def deposit(
    config,
    target_dir,
    run_names,
    run_name_prefix,
    run_name_regex,
    picks,
    meshes,
    segmentations,
    tomograms,
    features,
    max_workers,
    debug,
):
    """Create a depositable view of a copick project using symlinks.

    This command creates a hierarchical directory structure suitable for uploading to the
    cryoET data portal. It operates on a single copick config and creates symlinks to the
    actual data files, allowing multiple projects to be deposited into the same target
    directory through successive executions.

    The directory structure created conforms to the standard copick filesystem layout.

    Examples:

    \b
    # Deposit all runs from a filesystem project
    copick deposit -c filesystem_config.json --target-dir /path/to/deposit \\
        --picks "*:*/*" --meshes "*:*/*"

    \b
    # Deposit from a data portal project (automatic run name transformation)
    # Runs will be named like: 10301_TS_001_<portal_run_id>
    copick deposit -c portal_config.json --target-dir /path/to/deposit \\
        --picks "proteasome:*/*" --picks "ribosome:*/*" \\
        --segmentations "membrane:*/*@10.0"

    \b
    # Deposit with explicit prefix override
    copick deposit -c config.json --target-dir /path/to/deposit \\
        --run-names "TS_001,TS_002" --run-name-prefix "custom_prefix_" \\
        --picks "*:*/*"

    \b
    # Deposit with regex to extract run names
    copick deposit -c config.json --target-dir /path/to/deposit \\
        --run-name-regex "^(TS_\\d+).*" --tomograms "wbp@10.0"

    \b
    # Multiple projects to same target (successive executions)
    copick deposit -c project1.json --target-dir /deposit --run-name-prefix "proj1_" \\
        --picks "*:*/*"
    copick deposit -c project2.json --target-dir /deposit --run-name-prefix "proj2_" \\
        --picks "*:*/*"

    Notes:
    - For data portal projects, run names are automatically transformed from portal run IDs
      to "{dataset_id}_{portal_run_name}_{portal_run_id}" unless run_name_prefix is provided.
    - Multiple executions to the same target_dir are safe and idempotent.
    - Symlinks that already exist and point to the correct source are skipped.
    - Read-only data from the portal cannot be symlinked and will raise an error.
    """
    from copick.ops.deposit import deposit as deposit_op

    logger = get_logger(__name__, debug=debug)

    # Parse run_names from comma-separated string to list
    run_names_list = None
    if run_names:
        run_names_list = [name.strip() for name in run_names.split(",") if name.strip()]

    # Convert tuple to list or None
    picks_uris_list = list(picks) if picks else None
    meshes_uris_list = list(meshes) if meshes else None
    segmentations_uris_list = list(segmentations) if segmentations else None
    tomograms_uris_list = list(tomograms) if tomograms else None
    features_uris_list = list(features) if features else None

    # Call the deposit operation
    deposit_op(
        config=config,
        target_dir=target_dir,
        run_names=run_names_list,
        run_name_prefix=run_name_prefix,
        run_name_regex=run_name_regex,
        picks_uris=picks_uris_list,
        meshes_uris=meshes_uris_list,
        segmentations_uris=segmentations_uris_list,
        tomograms_uris=tomograms_uris_list,
        features_uris=features_uris_list,
        n_workers=max_workers,
    )

    logger.info("Deposit operation completed successfully.")
