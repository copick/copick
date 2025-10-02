import copick
import pytest
from copick.util.uri import (
    get_copick_objects_by_type,
    parse_copick_uri,
    resolve_copick_objects,
    serialize_copick_uri,
    serialize_copick_uri_from_dict,
)


class TestParseURI:
    """Test URI parsing functionality."""

    def test_parse_pick_uri_complete(self):
        """Test parsing a complete pick URI."""
        result = parse_copick_uri("ribosome:gapstop/0", "picks")
        assert result["object_type"] == "picks"
        assert result["pattern_type"] == "glob"
        assert result["object_name"] == "ribosome"
        assert result["user_id"] == "gapstop"
        assert result["session_id"] == "0"

    def test_parse_pick_uri_incomplete(self):
        """Test parsing incomplete pick URIs with wildcard defaults."""
        # Just object name
        result = parse_copick_uri("ribosome", "picks")
        assert result["object_name"] == "ribosome"
        assert result["user_id"] == "*"
        assert result["session_id"] == "*"

        # Object name and user ID
        result = parse_copick_uri("ribosome:gapstop", "picks")
        assert result["object_name"] == "ribosome"
        assert result["user_id"] == "gapstop"
        assert result["session_id"] == "*"

    def test_parse_pick_uri_glob_patterns(self):
        """Test parsing pick URIs with glob patterns."""
        result = parse_copick_uri("ribo*:gapstop/*", "picks")
        assert result["object_name"] == "ribo*"
        assert result["user_id"] == "gapstop"
        assert result["session_id"] == "*"

    def test_parse_pick_uri_regex(self):
        """Test parsing pick URIs with regex patterns."""
        result = parse_copick_uri("re:ribo.*:gapstop/\\d+", "picks")
        assert result["pattern_type"] == "regex"
        assert result["object_name"] == "ribo.*"
        assert result["user_id"] == "gapstop"
        assert result["session_id"] == "\\d+"

    def test_parse_mesh_uri(self):
        """Test parsing mesh URIs (same format as picks)."""
        result = parse_copick_uri("membrane:membrain/0", "mesh")
        assert result["object_type"] == "mesh"
        assert result["object_name"] == "membrane"
        assert result["user_id"] == "membrain"
        assert result["session_id"] == "0"

    def test_parse_segmentation_uri_complete(self):
        """Test parsing a complete segmentation URI."""
        result = parse_copick_uri("painting:test.user/123@10.0?multilabel=true", "segmentation")
        assert result["object_type"] == "segmentation"
        assert result["name"] == "painting"
        assert result["user_id"] == "test.user"
        assert result["session_id"] == "123"
        assert result["voxel_spacing"] == "10.0"
        assert result["multilabel"] is True

    def test_parse_segmentation_uri_no_multilabel(self):
        """Test parsing segmentation URI without multilabel parameter."""
        result = parse_copick_uri("membrane:membrain/0@20.0", "segmentation")
        assert result["name"] == "membrane"
        assert result["user_id"] == "membrain"
        assert result["session_id"] == "0"
        assert result["voxel_spacing"] == "20.0"
        assert result["multilabel"] is None  # Default: match both

    def test_parse_segmentation_uri_incomplete(self):
        """Test parsing incomplete segmentation URIs."""
        # Just name
        result = parse_copick_uri("painting", "segmentation")
        assert result["name"] == "painting"
        assert result["user_id"] == "*"
        assert result["session_id"] == "*"
        assert result["voxel_spacing"] == "*"

        # Name and user
        result = parse_copick_uri("painting:test.user", "segmentation")
        assert result["name"] == "painting"
        assert result["user_id"] == "test.user"
        assert result["session_id"] == "*"
        assert result["voxel_spacing"] == "*"

        # Name, user, session
        result = parse_copick_uri("painting:test.user/123", "segmentation")
        assert result["name"] == "painting"
        assert result["user_id"] == "test.user"
        assert result["session_id"] == "123"
        assert result["voxel_spacing"] == "*"

    def test_parse_tomogram_uri_complete(self):
        """Test parsing a complete tomogram URI."""
        result = parse_copick_uri("wbp@10.0", "tomogram")
        assert result["object_type"] == "tomogram"
        assert result["tomo_type"] == "wbp"
        assert result["voxel_spacing"] == "10.0"

    def test_parse_tomogram_uri_incomplete(self):
        """Test parsing incomplete tomogram URI."""
        result = parse_copick_uri("wbp", "tomogram")
        assert result["tomo_type"] == "wbp"
        assert result["voxel_spacing"] == "*"

    def test_parse_feature_uri_complete(self):
        """Test parsing a complete feature URI."""
        result = parse_copick_uri("wbp@10.0:sobel", "feature")
        assert result["object_type"] == "feature"
        assert result["tomo_type"] == "wbp"
        assert result["voxel_spacing"] == "10.0"
        assert result["feature_type"] == "sobel"

    def test_parse_feature_uri_incomplete(self):
        """Test parsing incomplete feature URIs."""
        # Just tomo type
        result = parse_copick_uri("wbp", "feature")
        assert result["tomo_type"] == "wbp"
        assert result["voxel_spacing"] == "*"
        assert result["feature_type"] == "*"

        # Tomo type and voxel spacing
        result = parse_copick_uri("wbp@10.0", "feature")
        assert result["tomo_type"] == "wbp"
        assert result["voxel_spacing"] == "10.0"
        assert result["feature_type"] == "*"

    def test_parse_uri_invalid_object_type(self):
        """Test parsing with invalid object type."""
        with pytest.raises(ValueError, match="Unknown object type"):
            parse_copick_uri("test:user/session", "invalid_type")


class TestSerializeURI:
    """Test URI serialization functionality."""

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_serialize_picks_roundtrip(self, case, request):
        """Test that picks can be serialized and parsed back."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get a pick and serialize it
        run = root.runs[0]
        picks = run.picks
        if picks:
            pick = picks[0]
            uri = serialize_copick_uri(pick)

            # URI should match expected format
            assert ":" in uri
            assert "/" in uri

            # Parse it back
            parsed = parse_copick_uri(uri, "picks")
            assert parsed["object_name"] == pick.pickable_object_name
            assert parsed["user_id"] == pick.user_id
            assert parsed["session_id"] == pick.session_id

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_serialize_meshes_roundtrip(self, case, request):
        """Test that meshes can be serialized and parsed back."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        meshes = run.meshes
        if meshes:
            mesh = meshes[0]
            uri = serialize_copick_uri(mesh)

            parsed = parse_copick_uri(uri, "mesh")
            assert parsed["object_name"] == mesh.pickable_object_name
            assert parsed["user_id"] == mesh.user_id
            assert parsed["session_id"] == mesh.session_id

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_serialize_segmentations_roundtrip(self, case, request):
        """Test that segmentations can be serialized and parsed back."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        segs = run.segmentations
        if segs:
            seg = segs[0]
            uri = serialize_copick_uri(seg)

            # URI should contain @ for voxel spacing
            assert "@" in uri

            parsed = parse_copick_uri(uri, "segmentation")
            assert parsed["name"] == seg.name
            assert parsed["user_id"] == seg.user_id
            assert parsed["session_id"] == seg.session_id
            assert float(parsed["voxel_spacing"]) == seg.voxel_size

            # Check multilabel flag
            if seg.is_multilabel:
                assert "?multilabel=true" in uri
                assert parsed["multilabel"] is True

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_serialize_tomograms_roundtrip(self, case, request):
        """Test that tomograms can be serialized and parsed back."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        if run.voxel_spacings:
            vs = run.voxel_spacings[0]
            tomos = vs.tomograms
            if tomos:
                tomo = tomos[0]
                uri = serialize_copick_uri(tomo)

                assert "@" in uri

                parsed = parse_copick_uri(uri, "tomogram")
                assert parsed["tomo_type"] == tomo.tomo_type
                assert float(parsed["voxel_spacing"]) == tomo.voxel_spacing.voxel_size

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_serialize_features_roundtrip(self, case, request):
        """Test that features can be serialized and parsed back."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        if run.voxel_spacings:
            vs = run.voxel_spacings[0]
            tomos = vs.tomograms
            for tomo in tomos:
                features = tomo.features
                if features:
                    feat = features[0]
                    uri = serialize_copick_uri(feat)

                    assert "@" in uri
                    assert ":" in uri

                    parsed = parse_copick_uri(uri, "feature")
                    assert parsed["tomo_type"] == feat.tomo_type
                    assert float(parsed["voxel_spacing"]) == feat.tomogram.voxel_spacing.voxel_size
                    assert parsed["feature_type"] == feat.feature_type
                    return

    def test_serialize_from_dict_picks(self):
        """Test serializing picks from dict parameters."""
        uri = serialize_copick_uri_from_dict(
            object_type="picks",
            object_name="ribosome",
            user_id="gapstop",
            session_id="0",
        )
        assert uri == "ribosome:gapstop/0"

    def test_serialize_from_dict_segmentations(self):
        """Test serializing segmentations from dict parameters."""
        uri = serialize_copick_uri_from_dict(
            object_type="segmentation",
            name="painting",
            user_id="test.user",
            session_id="123",
            voxel_spacing=10.0,
            multilabel=True,
        )
        assert uri == "painting:test.user/123@10.0?multilabel=true"

    def test_serialize_from_dict_tomograms(self):
        """Test serializing tomograms from dict parameters."""
        uri = serialize_copick_uri_from_dict(
            object_type="tomogram",
            tomo_type="wbp",
            voxel_spacing=10.0,
        )
        assert uri == "wbp@10.0"

    def test_serialize_from_dict_features(self):
        """Test serializing features from dict parameters."""
        uri = serialize_copick_uri_from_dict(
            object_type="feature",
            tomo_type="wbp",
            voxel_spacing=10.0,
            feature_type="sobel",
        )
        assert uri == "wbp@10.0:sobel"

    def test_serialize_from_dict_missing_params(self):
        """Test that missing required parameters raise errors."""
        with pytest.raises(ValueError, match="require"):
            serialize_copick_uri_from_dict(object_type="picks", object_name="ribosome")


class TestResolveObjects:
    """Test object resolution from URIs."""

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_picks_exact(self, case, request):
        """Test resolving picks with exact match."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Find a specific pick to test
        run = root.runs[0]
        if run.picks:
            pick = run.picks[0]
            uri = f"{pick.pickable_object_name}:{pick.user_id}/{pick.session_id}"

            resolved = resolve_copick_objects(uri, root, "picks", run.name)
            assert len(resolved) == 1
            assert resolved[0].pickable_object_name == pick.pickable_object_name
            assert resolved[0].user_id == pick.user_id
            assert resolved[0].session_id == pick.session_id

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_picks_wildcard(self, case, request):
        """Test resolving picks with wildcards."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get all picks for ribosome
        resolved = resolve_copick_objects("ribosome", root, "picks")
        ribosome_picks = [p for p in resolved if p.pickable_object_name == "ribosome"]
        assert len(ribosome_picks) > 0

        # All should be ribosome picks
        for pick in ribosome_picks:
            assert pick.pickable_object_name == "ribosome"

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_picks_glob_pattern(self, case, request):
        """Test resolving picks with glob patterns."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Match all picks with user_id starting with 'gap'
        resolved = resolve_copick_objects("*:gap*/*", root, "picks")
        assert len(resolved) > 0

        for pick in resolved:
            assert pick.user_id.startswith("gap")

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_meshes_exact(self, case, request):
        """Test resolving meshes with exact match."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        if run.meshes:
            mesh = run.meshes[0]
            uri = f"{mesh.pickable_object_name}:{mesh.user_id}/{mesh.session_id}"

            resolved = resolve_copick_objects(uri, root, "mesh", run.name)
            assert len(resolved) == 1
            assert resolved[0].pickable_object_name == mesh.pickable_object_name

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_segmentations_exact(self, case, request):
        """Test resolving segmentations with exact match."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        if run.segmentations:
            seg = run.segmentations[0]
            uri = f"{seg.name}:{seg.user_id}/{seg.session_id}@{seg.voxel_size}"

            resolved = resolve_copick_objects(uri, root, "segmentation", run.name)
            assert len(resolved) == 1
            assert resolved[0].name == seg.name
            assert resolved[0].voxel_size == seg.voxel_size

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_segmentations_multilabel_default(self, case, request):
        """Test that segmentations match both multilabel and non-multilabel by default."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get all segmentations without specifying multilabel
        resolved = resolve_copick_objects("*:*/*@*", root, "segmentation")

        # Should include both multilabel and non-multilabel segmentations
        has_multilabel = any(seg.is_multilabel for seg in resolved)
        has_non_multilabel = any(not seg.is_multilabel for seg in resolved)

        # At least one type should exist (depends on test data)
        assert has_multilabel or has_non_multilabel

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_segmentations_multilabel_filter(self, case, request):
        """Test filtering segmentations by multilabel flag."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get multilabel segmentations only
        resolved = resolve_copick_objects("*:*/*@*?multilabel=true", root, "segmentation")

        if resolved:
            # All should be multilabel
            for seg in resolved:
                assert seg.is_multilabel

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_tomograms_exact(self, case, request):
        """Test resolving tomograms with exact match."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        if run.voxel_spacings:
            vs = run.voxel_spacings[0]
            tomos = vs.tomograms
            if tomos:
                tomo = tomos[0]
                uri = f"{tomo.tomo_type}@{vs.voxel_size}"

                resolved = resolve_copick_objects(uri, root, "tomogram", run.name)
                assert len(resolved) >= 1

                # Find our specific tomogram
                found = [t for t in resolved if t.tomo_type == tomo.tomo_type]
                assert len(found) >= 1

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_tomograms_wildcard(self, case, request):
        """Test resolving all tomograms with wildcards."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get all tomograms
        resolved = resolve_copick_objects("*@*", root, "tomogram")
        assert len(resolved) > 0

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_features_exact(self, case, request):
        """Test resolving features with exact match."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        if run.voxel_spacings:
            vs = run.voxel_spacings[0]
            for tomo in vs.tomograms:
                if tomo.features:
                    feat = tomo.features[0]
                    uri = f"{feat.tomo_type}@{vs.voxel_size}:{feat.feature_type}"

                    resolved = resolve_copick_objects(uri, root, "feature", run.name)
                    assert len(resolved) >= 1

                    found = [f for f in resolved if f.feature_type == feat.feature_type]
                    assert len(found) >= 1
                    return

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_resolve_features_wildcard(self, case, request):
        """Test resolving all features with wildcards."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get all features
        resolved = resolve_copick_objects("*@*:*", root, "feature")

        # Should have at least some features
        if resolved:
            for feat in resolved:
                assert feat.feature_type is not None


class TestGetObjectsByType:
    """Test direct object retrieval by type."""

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_get_picks_all(self, case, request):
        """Test getting all picks."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        picks = get_copick_objects_by_type(root, "picks")
        assert len(picks) > 0
        assert all(hasattr(p, "pickable_object_name") for p in picks)

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_get_picks_filtered(self, case, request):
        """Test getting filtered picks."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get all ribosome picks
        picks = get_copick_objects_by_type(root, "picks", object_name="ribosome")
        assert all(p.pickable_object_name == "ribosome" for p in picks)

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_get_picks_by_run(self, case, request):
        """Test getting picks for specific run."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        run = root.runs[0]
        picks = get_copick_objects_by_type(root, "picks", run_name=run.name)

        # All picks should belong to the specified run
        for pick in picks:
            assert pick.run.name == run.name

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_get_segmentations_all(self, case, request):
        """Test getting all segmentations."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        segs = get_copick_objects_by_type(root, "segmentation")
        if segs:
            assert all(hasattr(s, "name") for s in segs)
            assert all(hasattr(s, "voxel_size") for s in segs)

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_get_tomograms_all(self, case, request):
        """Test getting all tomograms."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        tomos = get_copick_objects_by_type(root, "tomogram")
        assert len(tomos) > 0
        assert all(hasattr(t, "tomo_type") for t in tomos)

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_get_features_all(self, case, request):
        """Test getting all features."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        features = get_copick_objects_by_type(root, "feature")
        if features:
            assert all(hasattr(f, "feature_type") for f in features)

    def test_get_objects_invalid_type(self, local):
        """Test getting objects with invalid type."""
        root = copick.from_file(str(local["cfg_file"]))

        with pytest.raises(ValueError, match="Unknown object type"):
            get_copick_objects_by_type(root, "invalid_type")

    def test_get_objects_invalid_run(self, local):
        """Test getting objects with non-existent run."""
        root = copick.from_file(str(local["cfg_file"]))

        with pytest.raises(ValueError, match="not found"):
            get_copick_objects_by_type(root, "picks", run_name="nonexistent_run")


class TestPatternMatching:
    """Test advanced pattern matching with regex."""

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_regex_picks_pattern(self, case, request):
        """Test regex pattern matching for picks."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Match picks with numeric session IDs
        resolved = resolve_copick_objects("re:.*:.*/(\\d+)", root, "picks")

        if resolved:
            for pick in resolved:
                assert pick.session_id.isdigit()

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_glob_voxel_spacing_pattern(self, case, request):
        """Test glob pattern for voxel spacings."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get tomograms at voxel spacing 10.0
        resolved = resolve_copick_objects("*@10.0", root, "tomogram")

        if resolved:
            for tomo in resolved:
                assert tomo.voxel_spacing.voxel_size == 10.0

    @pytest.mark.parametrize("case", pytest.common_cases)
    def test_combined_filters(self, case, request):
        """Test combining multiple filters."""
        fixture = request.getfixturevalue(case)
        root = copick.from_file(str(fixture["cfg_file"]))

        # Get specific object with specific user at specific voxel spacing
        run = root.runs[0]
        resolved = get_copick_objects_by_type(
            root,
            "segmentation",
            run_name=run.name,
            name="painting",
            voxel_spacing="10.0",
            pattern_type="glob",
        )

        # All results should match all filters
        for seg in resolved:
            assert seg.name == "painting"
            assert seg.voxel_size == 10.0
