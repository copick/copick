from typing import List, Optional, Union

from copick import COPICK_TYPES, from_file
from copick.models import CopickRoot

_copick_types = {ct.__name__: ct for ct in COPICK_TYPES}


def sync(
    source_root: Union[str, CopickRoot],
    dest_root: Union[str, CopickRoot],
    dry_run: bool = False,
    exclude_static: bool = True,
    include_entities: Optional[List[str]] = None,
    exclude_entities: Optional[List[str]] = None,
    include_object: Optional[List[str]] = None,
    exclude_object: Optional[List[str]] = None,
    include_user: Optional[List[str]] = None,
    exclude_user: Optional[List[str]] = None,
    include_session: Optional[List[str]] = None,
    exclude_session: Optional[List[str]] = None,
    include_run: Optional[List[str]] = None,
    exclude_run: Optional[List[str]] = None,
    parallel: bool = True,
    workers: Optional[int] = 8,
    show_progress: bool = True,
):
    """Synchronize the source and destination Copick projects.

    Args:
        source_root: The root of the source Copick project.
        dest_root: The root of the destination Copick project.
        include: A list of Copick types to include in the synchronization. If None, all types are included.

    Returns:
        None
    """

    # Get src and dst projects
    if isinstance(source_root, str):
        source_root = from_file(source_root)

    if isinstance(dest_root, str):
        dest_root = from_file(dest_root)

    # Get the list of Copick types to include in the synchronization
    include_entities = COPICK_TYPES if include_entities is None else [_copick_types[e] for e in include_entities]
    exclude_entities = [] if exclude_entities is None else [_copick_types[e] for e in exclude_entities]
