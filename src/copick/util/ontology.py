"""Parsing and external-link resolution for CryoET Data Portal object identifiers.

The Data Portal identifies an annotation's object with an ``object_id`` drawn
from one of several identifier namespaces (see the portal LinkML schema, slot
``annotation_object_id``). copick stores that value verbatim as
:attr:`PickableObject.identifier`. This module maps such an identifier to its
namespace, bare accession, and an external browser URL where available.

Supported namespaces:

===========  ==========================  ==============================
Namespace    Example                     External resource
===========  ==========================  ==============================
GO           ``GO:0005840``              AmiGO (Gene Ontology)
UniProtKB    ``UniProtKB:P0CX35``        UniProt
CHEBI        ``CHEBI:15986``             ChEBI (EBI)
PDB          ``PDB-1BXN`` (dash!)        RCSB PDB
UBERON       ``UBERON:0000955``          OBO PURL
CL           ``CL:0000000``             OBO PURL
CDPO         ``CDPO:0000001``           (no public browser)
===========  ==========================  ==============================
"""

import re
from typing import Callable, List, NamedTuple, Optional, Pattern, Tuple


class OntologyRef(NamedTuple):
    """Parsed representation of an object identifier.

    Attributes:
        namespace: Canonical namespace (e.g. ``"GO"``, ``"PDB"``) or ``None`` if
            the identifier does not match any known namespace.
        accession: The bare accession after the namespace separator (e.g.
            ``"0005840"``, ``"P0CX35"``, ``"1BXN"``). For unrecognized strings
            this is the raw identifier.
        url: External browser URL, or ``None`` when the namespace has no public
            browser (CDPO) or the identifier is unrecognized.
    """

    namespace: Optional[str]
    accession: str
    url: Optional[str]


# Ordered registry: (canonical namespace, regex with named accession group, url_builder | None).
# Matching is case-insensitive on the scheme (preserving the historical
# ``identifier.lower().startswith(...)`` behavior), but URLs are rebuilt from the
# canonical namespace so links are always well-formed regardless of input case.
# NOTE: PDB uses a dash separator (``PDB-1BXN``), unlike the colon namespaces.
_NAMESPACES: List[Tuple[str, Pattern, Optional[Callable[[re.Match], str]]]] = [
    (
        "GO",
        re.compile(r"^GO:(?P<num>[0-9]{7})$", re.IGNORECASE),
        lambda m: f"https://amigo.geneontology.org/amigo/term/GO:{m['num']}",
    ),
    (
        "UniProtKB",
        re.compile(r"^UniProtKB:(?P<acc>\S+)$", re.IGNORECASE),
        lambda m: f"https://www.uniprot.org/uniprotkb/{m['acc']}",
    ),
    (
        "CHEBI",
        re.compile(r"^CHEBI:(?P<num>[0-9]+)$", re.IGNORECASE),
        lambda m: f"https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:{m['num']}",
    ),
    (
        "PDB",
        re.compile(r"^PDB-(?P<acc>[0-9a-zA-Z]{4,8})$", re.IGNORECASE),
        lambda m: f"https://www.rcsb.org/structure/{m['acc']}",
    ),
    (
        "UBERON",
        re.compile(r"^UBERON:(?P<num>[0-9]{7})$", re.IGNORECASE),
        lambda m: f"https://purl.obolibrary.org/obo/UBERON_{m['num']}",
    ),
    (
        "CL",
        re.compile(r"^CL:(?P<num>[0-9]{7})$", re.IGNORECASE),
        lambda m: f"https://purl.obolibrary.org/obo/CL_{m['num']}",
    ),
    (
        # Recognized namespace, but no public web browser -> render as plain text.
        "CDPO",
        re.compile(r"^CDPO:(?P<num>[0-9]{7})$", re.IGNORECASE),
        None,
    ),
]


def parse_identifier(identifier: Optional[str]) -> Optional[OntologyRef]:
    """Map a portal object identifier to its namespace, accession, and URL.

    Args:
        identifier: The object identifier (e.g. ``"GO:0005840"``, ``"PDB-1BXN"``).

    Returns:
        ``None`` when ``identifier`` is ``None`` or empty. Otherwise an
        :class:`OntologyRef`. For recognized namespaces without a public browser
        (CDPO) and for unrecognized strings, ``url`` is ``None``; unrecognized
        strings additionally have ``namespace=None``.
    """
    if not identifier:
        return None

    ident = identifier.strip()
    for namespace, pattern, url_builder in _NAMESPACES:
        m = pattern.match(ident)
        if m:
            groups = m.groupdict()
            accession = groups.get("acc") or groups.get("num")
            return OntologyRef(namespace, accession, url_builder(m) if url_builder else None)

    return OntologyRef(None, ident, None)


def identifier_to_markdown_link(identifier: Optional[str]) -> Optional[str]:
    """Render an identifier as a markdown link when resolvable.

    Args:
        identifier: The object identifier.

    Returns:
        ``"[identifier](url)"`` when the identifier resolves to a URL, the plain
        ``identifier`` string when it is recognized but has no URL (or is
        unrecognized), and ``None`` when ``identifier`` is ``None`` or empty.
    """
    if not identifier:
        return None

    ref = parse_identifier(identifier)
    if ref and ref.url:
        return f"[{identifier}]({ref.url})"
    return identifier
