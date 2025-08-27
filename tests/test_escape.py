import warnings
from typing import Any, Dict

import pytest
from copick.impl.filesystem import CopickRootFSSpec
from copick.models import CopickConfig, PickableObject
from copick.util.escape import sanitize_name
from pydantic import ValidationError


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


def test_valid_names():
    """Test that valid names are passed through unchanged."""
    # Valid names should remain unchanged
    valid_names = ["test", "test123", "test-name", "valid", "test.name"]

    for name in valid_names:
        result = sanitize_name(name)
        assert result == name, f"Valid name '{name}' was modified to '{result}'"


def test_invalid_characters():
    """Test that invalid characters are replaced with dashes."""
    test_cases = [
        ("test name", "test-name"),  # space
        ("test/name", "test-name"),  # slash
        ("test\\name", "test-name"),  # backslash
        ("test:name", "test-name"),  # colon
        ("test*name", "test-name"),  # asterisk
        ("test?name", "test-name"),  # question mark
        ('test"name', "test-name"),  # quote
        ("test<name", "test-name"),  # less than
        ("test>name", "test-name"),  # greater than
        ("test|name", "test-name"),  # pipe
        ("test_name", "test-name"),  # underscore
    ]

    for input_name, expected in test_cases:
        result = sanitize_name(input_name)
        assert (
            result == expected
        ), f"Invalid name '{input_name}' was not correctly sanitized. Got '{result}', expected '{expected}'"


def test_multiple_invalid_characters():
    """Test that multiple consecutive invalid characters are each replaced with a dash."""
    test_cases = [
        ("test   name", "test---name"),  # multiple spaces
        ("test///name", "test---name"),  # multiple slashes
        ("test<>:name", "test---name"),  # multiple invalid chars
        ("test__name", "test--name"),  # multiple underscores
    ]

    for input_name, expected in test_cases:
        result = sanitize_name(input_name)
        assert (
            result == expected
        ), f"Multiple invalid chars in '{input_name}' were not correctly sanitized. Got '{result}', expected '{expected}'"


def test_trim_dashes():
    """Test that leading and trailing dashes are trimmed."""
    test_cases = [
        ("-test", "test"),  # leading dash
        ("test-", "test"),  # trailing dash
        ("-test-", "test"),  # both leading and trailing
        ("--test--", "test"),  # multiple leading and trailing
    ]

    for input_name, expected in test_cases:
        result = sanitize_name(input_name)
        assert (
            result == expected
        ), f"Dashes in '{input_name}' were not correctly trimmed. Got '{result}', expected '{expected}'"


def test_empty_result():
    """Test that an empty result raises ValueError."""
    invalid_names = ["   ", "___", "*?<>|", "\x00\x01"]

    for name in invalid_names:
        with pytest.raises(ValueError, match="Filename cannot be empty or completely consist of invalid characters"):
            sanitize_name(name)


def test_warning_on_modification():
    """Test that a warning is issued when the input is modified."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = sanitize_name("test space")

        assert len(w) == 1
        assert issubclass(w[0].category, UserWarning)
        assert "has been sanitized" in str(w[0].message)
        assert result == "test-space"


def test_no_warning_on_valid():
    """Test that no warning is issued for valid names."""
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sanitize_name("valid")

        assert len(w) == 0, "Warning was issued for valid name"


def test_pickable_object_name_validation():
    """Test that PickableObject raises errors for invalid names."""
    # Names with invalid characters should raise a validation error
    with pytest.raises(Exception) as excinfo:
        PickableObject(
            name="invalid name with spaces",
            is_particle=True,
            label=1,
        )

    # Verify that the error message suggests using sanitize_name
    assert "invalid characters" in str(excinfo.value)
    assert "sanitize_name" in str(excinfo.value)


def test_pickable_object_name_sanitized():
    """Test that pre-sanitized names are accepted by PickableObject."""
    # Sanitize the name before creating the object
    invalid_name = "invalid name with spaces"
    sanitized_name = sanitize_name(invalid_name)

    # Create object with sanitized name
    obj = PickableObject(
        name=sanitized_name,
        is_particle=True,
        label=1,
    )

    # Check that the name is correctly set
    assert obj.name == "invalid-name-with-spaces"


def test_pickable_object_name_unicode():
    """Test that PickableObject handles Unicode characters correctly."""
    # Create a PickableObject with a name containing Unicode characters
    obj = PickableObject(
        name="mitochondria-üéêë",
        is_particle=True,
        label=1,
    )

    # Check that Unicode characters are preserved
    assert obj.name == "mitochondria-üéêë"


def test_copick_config_name_validation():
    """Test that CopickConfig does not automatically sanitize its name."""
    # Create a CopickConfig with an invalid name
    config = CopickConfig(
        name="CoPick Project/with:invalid*chars",
        pickable_objects=[],
    )

    # Check that the name is not sanitized
    assert config.name == "CoPick Project/with:invalid*chars"


def test_copick_config_object_name_validation():
    """Test that CopickConfig requires valid object names."""
    # Attempt to create a CopickConfig with objects that have invalid names
    with pytest.raises(ValidationError):
        CopickConfig(
            name="CoPick",
            pickable_objects=[
                PickableObject(name="object 1", is_particle=True, label=1),
            ],
        )

    # Create with pre-sanitized object names
    config = CopickConfig(
        name="CoPick",
        pickable_objects=[
            PickableObject(name=sanitize_name("object 1"), is_particle=True, label=1),
            PickableObject(name=sanitize_name("object/2"), is_particle=False, label=2),
            PickableObject(name=sanitize_name("object:3"), is_particle=True, label=3),
        ],
    )

    # Check that the objects have sanitized names
    assert [obj.name for obj in config.pickable_objects] == ["object-1", "object-2", "object-3"]


def test_sanitize_outputs():
    """Diagnostic test to check actual outputs of sanitize_name for integration test inputs."""
    test_inputs = [
        "tomo type/with*invalid:chars",
        "feature_type with spaces/and*special:chars",
        "segmentation<>name",
        "session?id",
        "user|id",
    ]

    for input_str in test_inputs:
        result = sanitize_name(input_str)
        print(f"Input: '{input_str}' → Output: '{result}'")


def test_integration_new_picks(test_payload: Dict[str, Any]):
    """Test that sanitize_name is correctly applied when creating new picks."""
    copick_root = test_payload["root"]
    run = copick_root.get_run("TS_001")

    copick_root.config.pickable_objects.append(
        PickableObject(
            name="mito-chondria",
            identifier="GO:123456",
            is_particle=True,
            label=1,
            emdb_id="EMD-1234",
            pdb_id="1abc",
        ),
    )

    # Try to create picks with invalid object name, session ID, and user ID
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        picks = run.new_picks("mito*chondria", "session with spaces", "user:with:invalid/chars")

        # Check that the names were sanitized
        assert picks.pickable_object_name == "mito-chondria"
        assert picks.session_id == "session-with-spaces"
        assert picks.user_id == "user-with-invalid-chars"
        assert len(w) >= 3
        assert any("has been sanitized" in str(msg.message) for msg in w)


def test_integration_new_mesh(test_payload: Dict[str, Any]):
    """Test that sanitize_name is correctly applied when creating a new mesh."""
    copick_root = test_payload["root"]
    run = copick_root.get_run("TS_001")

    copick_root.config.pickable_objects.append(
        PickableObject(
            name="object-name",
            identifier="GO:123456",
            is_particle=True,
            label=1,
            emdb_id="EMD-1234",
            pdb_id="1abc",
        ),
    )

    # Try to create a mesh with invalid object name, session ID, and user ID
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        mesh = run.new_mesh("object name", "session_id", "user\\id")

        # Check that the names were sanitized
        assert mesh.pickable_object_name == "object-name"
        assert mesh.session_id == "session-id"
        assert mesh.user_id == "user-id"
        assert len(w) >= 3
        assert any("has been sanitized" in str(msg.message) for msg in w)


def test_integration_new_segmentation(test_payload: Dict[str, Any]):
    """Test that sanitize_name is correctly applied when creating a new segmentation."""
    copick_root = test_payload["root"]
    run = copick_root.get_run("TS_001")

    # Try to create a segmentation with invalid name, session ID, and user ID
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        segmentation = run.new_segmentation(
            10.0,
            "segmentation<>name",
            "session?id",
            is_multilabel=True,
            user_id="user|id",
        )

        # Check that the names were sanitized
        assert segmentation.name == "segmentation--name"
        assert segmentation.session_id == "session-id"
        assert segmentation.user_id == "user-id"
        assert len(w) >= 3
        assert any("has been sanitized" in str(msg.message) for msg in w)


def test_integration_new_voxel_spacing(test_payload: Dict[str, Any]):
    """Test that voxel spacing values are unaffected as they are numeric."""
    copick_root = test_payload["root"]
    run = copick_root.get_run("TS_001")

    # Voxel spacing should be unaffected as it's numeric
    voxel_spacing = run.new_voxel_spacing(12.5)
    assert voxel_spacing.voxel_size == 12.5


def test_integration_new_tomogram(test_payload: Dict[str, Any]):
    """Test that sanitize_name is correctly applied when creating a new tomogram."""
    copick_root = test_payload["root"]
    run = copick_root.get_run("TS_001")
    voxel_spacing = run.get_voxel_spacing(10.0)

    # Try to create a tomogram with an invalid type name
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        tomogram = voxel_spacing.new_tomogram("tomo type/with*invalid:chars")

        # Check that the type was sanitized
        assert tomogram.tomo_type == "tomo-type-with-invalid-chars"
        assert len(w) >= 1
        assert any("has been sanitized" in str(msg.message) for msg in w)


def test_integration_new_features(test_payload: Dict[str, Any]):
    """Test that sanitize_name is correctly applied when creating new features."""
    copick_root = test_payload["root"]
    run = copick_root.get_run("TS_001")
    voxel_spacing = run.get_voxel_spacing(10.0)
    tomogram = voxel_spacing.get_tomogram("wbp")

    # Try to create features with an invalid feature type
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        features = tomogram.new_features("feature_type with spaces/and*special:chars")

        # Check that the feature type was sanitized with proper handling of multiple invalid chars
        assert features.feature_type == "feature-type-with-spaces-and-special-chars"
        assert len(w) >= 1
        assert any("has been sanitized" in str(msg.message) for msg in w)
