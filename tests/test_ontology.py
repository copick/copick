import pytest
from copick.models import PickableObject
from copick.ops._markdown import object_to_md
from copick.util.ontology import (
    OntologyRef,
    identifier_to_markdown_link,
    parse_identifier,
)


class TestParseIdentifier:
    """Test cases for copick.util.ontology.parse_identifier."""

    @pytest.mark.parametrize(
        ("identifier", "expected"),
        [
            (
                "GO:0005840",
                OntologyRef("GO", "0005840", "https://amigo.geneontology.org/amigo/term/GO:0005840"),
            ),
            (
                "UniProtKB:P0CX35",
                OntologyRef("UniProtKB", "P0CX35", "https://www.uniprot.org/uniprotkb/P0CX35"),
            ),
            (
                "CHEBI:15986",
                OntologyRef("CHEBI", "15986", "https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:15986"),
            ),
            (
                "PDB-1BXN",
                OntologyRef("PDB", "1BXN", "https://www.rcsb.org/structure/1BXN"),
            ),
            (
                "UBERON:0000955",
                OntologyRef("UBERON", "0000955", "https://purl.obolibrary.org/obo/UBERON_0000955"),
            ),
            (
                "CL:0000000",
                OntologyRef("CL", "0000000", "https://purl.obolibrary.org/obo/CL_0000000"),
            ),
            (
                # Recognized namespace, but no public browser -> url is None.
                "CDPO:0000001",
                OntologyRef("CDPO", "0000001", None),
            ),
        ],
    )
    def test_known_namespaces(self, identifier, expected):
        """Each supported namespace resolves to the expected (namespace, accession, url)."""
        assert parse_identifier(identifier) == expected

    @pytest.mark.parametrize("identifier", ["go:0005840", "pdb-1bxn", "uniprotkb:P0CX35", "chebi:15986"])
    def test_case_insensitive_scheme(self, identifier):
        """Lower-cased schemes still resolve to canonical URLs."""
        ref = parse_identifier(identifier)
        assert ref is not None
        assert ref.namespace is not None
        assert ref.url is not None
        # URL is rebuilt from the canonical namespace, so it is well-formed regardless of input case.
        assert ref.url.startswith("https://")

    @pytest.mark.parametrize("identifier", [None, ""])
    def test_none_or_empty(self, identifier):
        """None/empty identifiers return None."""
        assert parse_identifier(identifier) is None

    @pytest.mark.parametrize("identifier", ["ribosome", "FOO:1", "PDB-1BX"])
    def test_unrecognized(self, identifier):
        """Unrecognized strings yield namespace=None with the raw string echoed and no URL.

        ``PDB-1BX`` (3 accession chars) is below the ``{4,8}`` bound, so it does NOT match PDB.
        """
        assert parse_identifier(identifier) == OntologyRef(None, identifier, None)

    def test_strips_whitespace(self):
        """Leading/trailing whitespace is stripped before matching."""
        assert parse_identifier("  GO:0005840  ").namespace == "GO"


class TestIdentifierToMarkdownLink:
    """Test cases for copick.util.ontology.identifier_to_markdown_link."""

    def test_resolvable(self):
        assert (
            identifier_to_markdown_link("GO:0005840")
            == "[GO:0005840](https://amigo.geneontology.org/amigo/term/GO:0005840)"
        )

    def test_no_url_namespace_returns_plain(self):
        assert identifier_to_markdown_link("CDPO:0000001") == "CDPO:0000001"

    def test_unrecognized_returns_plain(self):
        assert identifier_to_markdown_link("ribosome") == "ribosome"

    @pytest.mark.parametrize("identifier", [None, ""])
    def test_none_or_empty(self, identifier):
        assert identifier_to_markdown_link(identifier) is None


class TestObjectToMd:
    """Test cases for object_to_md identifier rendering."""

    def _obj(self, **kwargs):
        defaults = {"name": "test-object", "is_particle": True}
        defaults.update(kwargs)
        return PickableObject(**defaults)

    @pytest.mark.parametrize(
        ("identifier", "expected_url"),
        [
            ("GO:0005840", "https://amigo.geneontology.org/amigo/term/GO:0005840"),
            ("CHEBI:15986", "https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:15986"),
            ("PDB-1BXN", "https://www.rcsb.org/structure/1BXN"),
            ("UBERON:0000955", "https://purl.obolibrary.org/obo/UBERON_0000955"),
            ("CL:0000000", "https://purl.obolibrary.org/obo/CL_0000000"),
        ],
    )
    def test_identifier_link_rendered(self, identifier, expected_url):
        md = object_to_md(self._obj(identifier=identifier))
        assert f"* Identifier: [{identifier}]({expected_url})\n" in md

    def test_cdpo_rendered_plain(self):
        md = object_to_md(self._obj(identifier="CDPO:0000001"))
        assert "* Identifier: CDPO:0000001\n" in md
        assert "](http" not in md.split("* Identifier:")[1].split("\n")[0]

    def test_none_identifier_does_not_raise(self):
        """Regression: a None identifier must not crash and emits no Identifier line."""
        md = object_to_md(self._obj(identifier=None))
        assert "* Identifier:" not in md

    def test_pdb_identifier_deduplicates_rcsb_link(self):
        """When identifier and pdb_id are the same PDB structure, only one RCSB link appears."""
        md = object_to_md(self._obj(identifier="PDB-1BXN", pdb_id="1BXN"))
        assert md.count("https://www.rcsb.org/structure/1BXN") == 1

    def test_pdb_id_still_links_when_distinct_from_identifier(self):
        """A pdb_id distinct from a non-PDB identifier still renders its own RCSB link."""
        md = object_to_md(self._obj(identifier="GO:0005840", pdb_id="4V9D"))
        assert "* PDB ID: [4V9D](https://www.rcsb.org/structure/4V9D)\n" in md
