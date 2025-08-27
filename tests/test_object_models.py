from typing import Any, Dict

import numpy as np
import pytest
from copick.impl.filesystem import CopickRootFSSpec
from copick.ops.add import add_object, add_object_volume


@pytest.fixture(params=pytest.common_cases)
def test_payload(request) -> Dict[str, Any]:
    payload = request.getfixturevalue(request.param)
    payload["root"] = CopickRootFSSpec.from_file(payload["cfg_file"])
    return payload


class TestCopickRootNewObject:
    """Test cases for the CopickRoot.new_object method."""

    def test_new_object_basic(self, test_payload):
        """Test creating a basic object with required parameters."""
        root = test_payload["root"]

        obj = root.new_object(
            name="test-object",
            is_particle=True,
        )

        assert obj.name == "test-object"
        assert obj.is_particle is True
        assert obj.label > 0  # Should get auto-assigned label
        assert obj.color is not None  # Should get default color

    def test_new_object_with_all_parameters(self, test_payload):
        """Test creating an object with all parameters specified."""
        root = test_payload["root"]

        metadata_dict = {"key1": "value1", "key2": 42, "nested": {"inner": True}}

        obj = root.new_object(
            name="detailed-object",
            is_particle=False,
            label=42,
            color=(255, 128, 64, 255),
            emdb_id="EMD-1234",
            pdb_id="4V9D",
            identifier="GO:0005840",
            map_threshold=0.7,
            radius=150.0,
            metadata=metadata_dict,
        )

        assert obj.name == "detailed-object"
        assert obj.is_particle is False
        assert obj.label == 42
        assert obj.color == (255, 128, 64, 255)
        assert obj.emdb_id == "EMD-1234"
        assert obj.pdb_id == "4V9D"
        assert obj.identifier == "GO:0005840"
        assert obj.map_threshold == 0.7
        assert obj.radius == 150.0
        assert obj.metadata == metadata_dict

    def test_new_object_auto_label_assignment(self, test_payload):
        """Test automatic label assignment for multiple objects."""
        root = test_payload["root"]

        # Create multiple objects and verify they get different labels
        obj1 = root.new_object(name="obj1", is_particle=True)
        obj2 = root.new_object(name="obj2", is_particle=True)
        obj3 = root.new_object(name="obj3", is_particle=False)

        labels = {obj1.label, obj2.label, obj3.label}
        assert len(labels) == 3, "All objects should have unique labels"
        assert all(label > 0 for label in labels), "All labels should be positive"

    def test_new_object_duplicate_name_no_exist_ok(self, test_payload):
        """Test creating object with duplicate name (should fail)."""
        root = test_payload["root"]

        # Create first object
        root.new_object(name="duplicate-name", is_particle=True)

        # Try to create second object with same name
        with pytest.raises(ValueError, match="already exists"):
            root.new_object(name="duplicate-name", is_particle=True, exist_ok=False)

    def test_new_object_duplicate_name_with_exist_ok(self, test_payload):
        """Test creating object with duplicate name with exist_ok=True."""
        root = test_payload["root"]

        # Create first object
        obj1 = root.new_object(name="duplicate-name", is_particle=True)

        # Create second object with same name and exist_ok=True
        obj2 = root.new_object(name="duplicate-name", is_particle=False, exist_ok=True)

        # Should return the existing object (obj1) - compare by name and properties
        assert obj1.name == obj2.name
        assert obj1.label == obj2.label

    def test_new_object_duplicate_label_no_exist_ok(self, test_payload):
        """Test creating object with duplicate label (should fail)."""
        root = test_payload["root"]

        # Create first object with specific label
        root.new_object(name="obj1", is_particle=True, label=100)

        # Try to create second object with same label
        with pytest.raises(ValueError, match="already exists"):
            root.new_object(name="obj2", is_particle=True, label=100, exist_ok=False)

    def test_new_object_invalid_name_characters(self, test_payload):
        """Test creating object with invalid name characters (should fail)."""
        root = test_payload["root"]

        # Test various invalid characters from [<>:"/\\|?*\x00-\x1F\x7F\s_]
        invalid_names = [
            "invalid/name",  # forward slash
            "invalid\\name",  # backslash
            "invalid:name",  # colon
            "invalid<name",  # less than
            "invalid>name",  # greater than
            'invalid"name',  # quote
            "invalid|name",  # pipe
            "invalid?name",  # question mark
            "invalid*name",  # asterisk
            "invalid name",  # space
            "invalid_name",  # underscore
            "invalid\x00name",  # null character
            "invalid\x1fname",  # control character
            "invalid\x7fname",  # del character
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ValueError, match="invalid characters"):
                root.new_object(name=invalid_name, is_particle=True)

    def test_new_object_valid_name_characters(self, test_payload):
        """Test creating object with valid name characters."""
        root = test_payload["root"]

        # Test valid names (letters, numbers, hyphens, dots)
        valid_names = [
            "validname",
            "valid-name",
            "valid.name",
            "valid123",
            "123valid",
            "VALIDNAME",
            "Valid-Name.123",
        ]

        for valid_name in valid_names:
            # Should not raise an exception
            obj = root.new_object(name=valid_name, is_particle=True)
            assert obj.name == valid_name

    def test_new_object_zero_label(self, test_payload):
        """Test creating object with label=0 (should fail)."""
        root = test_payload["root"]

        from pydantic_core import ValidationError

        with pytest.raises(ValidationError, match="Label 0 is reserved"):
            root.new_object(name="zero-label", is_particle=True, label=0)

    def test_new_object_invalid_color(self, test_payload):
        """Test creating object with invalid color (should fail)."""
        root = test_payload["root"]

        from pydantic_core import ValidationError

        # Test color with wrong number of values
        with pytest.raises(ValidationError, match="Field required"):
            root.new_object(name="bad-color", is_particle=True, color=(255, 0, 0))  # Missing alpha

        # Test color with values out of range
        with pytest.raises(ValidationError, match="Color values must be in the range"):
            root.new_object(name="bad-color2", is_particle=True, color=(256, 0, 0, 255))  # 256 > 255

    def test_new_object_with_metadata(self, test_payload):
        """Test creating object with metadata."""
        root = test_payload["root"]

        metadata_dict = {
            "key1": "value1",
            "key2": 42,
            "key3": {"nested": {"inner": True}},
            "array": [1, 2, 3],
            "boolean": False,
        }

        obj = root.new_object(name="test-with-metadata", is_particle=True, metadata=metadata_dict)

        assert obj.name == "test-with-metadata"
        assert obj.metadata == metadata_dict

    def test_new_object_without_metadata(self, test_payload):
        """Test creating object without metadata (should default to empty dict)."""
        root = test_payload["root"]

        obj = root.new_object(name="test-no-metadata", is_particle=True)

        assert obj.name == "test-no-metadata"
        assert obj.metadata == {}

    def test_new_object_with_none_metadata(self, test_payload):
        """Test creating object with None metadata (should default to empty dict)."""
        root = test_payload["root"]

        obj = root.new_object(name="test-none-metadata", is_particle=True, metadata=None)

        assert obj.name == "test-none-metadata"
        assert obj.metadata == {}

    def test_new_object_with_empty_metadata(self, test_payload):
        """Test creating object with empty metadata dict."""
        root = test_payload["root"]

        obj = root.new_object(name="test-empty-metadata", is_particle=True, metadata={})

        assert obj.name == "test-empty-metadata"
        assert obj.metadata == {}


class TestCopickRootSaveConfig:
    """Test cases for the CopickRoot.save_config method."""

    def test_save_config_basic(self, test_payload, tmp_path):
        """Test saving configuration to a file."""
        root = test_payload["root"]

        # Add an object to modify the config
        root.new_object(name="test-save", is_particle=True)

        # Save to temporary file
        config_path = tmp_path / "test-config.json"
        root.save_config(str(config_path))

        # Verify file was created
        assert config_path.exists()

        # Verify we can load the saved config
        new_root = CopickRootFSSpec.from_file(str(config_path))
        saved_obj = new_root.get_object("test-save")
        assert saved_obj is not None
        assert saved_obj.name == "test-save"

    def test_save_config_preserves_objects(self, test_payload, tmp_path):
        """Test that saving config preserves all object properties."""
        root = test_payload["root"]

        # Add object with all properties
        original_obj = root.new_object(
            name="full-object",
            is_particle=False,
            label=99,
            color=(200, 100, 50, 255),
            emdb_id="EMD-9999",
            pdb_id="9ABC",
            identifier="GO:1234567",
            map_threshold=0.3,
            radius=75.0,
        )

        # Save config
        config_path = tmp_path / "full-config.json"
        root.save_config(str(config_path))

        # Load and verify
        new_root = CopickRootFSSpec.from_file(str(config_path))
        loaded_obj = new_root.get_object("full-object")

        assert loaded_obj.name == original_obj.name
        assert loaded_obj.is_particle == original_obj.is_particle
        assert loaded_obj.label == original_obj.label
        assert loaded_obj.color == original_obj.color
        assert loaded_obj.emdb_id == original_obj.emdb_id
        assert loaded_obj.pdb_id == original_obj.pdb_id
        assert loaded_obj.identifier == original_obj.identifier
        assert loaded_obj.map_threshold == original_obj.map_threshold
        assert loaded_obj.radius == original_obj.radius

    def test_save_config_preserves_metadata(self, test_payload, tmp_path):
        """Test that saving config preserves object metadata."""
        root = test_payload["root"]

        # Add object with complex metadata
        metadata_dict = {
            "key1": "value1",
            "key2": 42,
            "key3": {"nested": {"inner": True, "list": [1, 2, 3]}},
            "array": [1, 2, 3],
            "boolean": False,
            "null_value": None,
        }

        original_obj = root.new_object(name="metadata-object", is_particle=True, metadata=metadata_dict)

        # Save config
        config_path = tmp_path / "metadata-config.json"
        root.save_config(str(config_path))

        # Load and verify metadata is preserved
        new_root = CopickRootFSSpec.from_file(str(config_path))
        loaded_obj = new_root.get_object("metadata-object")

        assert loaded_obj.name == original_obj.name
        assert loaded_obj.metadata == metadata_dict


class TestAddObjectFunction:
    """Test cases for the add_object function."""

    def test_add_object_basic(self, test_payload):
        """Test basic object addition via add_object function."""
        root = test_payload["root"]

        obj = add_object(
            root=root,
            name="func-test-object",
            is_particle=True,
        )

        assert obj.name == "func-test-object"
        assert obj.is_particle is True

        # Verify object is accessible from root
        retrieved_obj = root.get_object("func-test-object")
        assert retrieved_obj is not None
        assert retrieved_obj.name == "func-test-object"

    def test_add_object_with_volume(self, test_payload):
        """Test adding object with volume data."""
        root = test_payload["root"]

        # Create sample volume data
        np.random.seed(42)
        volume_data = np.random.randn(32, 32, 32).astype(np.float32)

        obj = add_object(
            root=root,
            name="object-with-volume",
            is_particle=True,
            volume=volume_data,
            voxel_size=10.0,
        )

        assert obj.name == "object-with-volume"
        # Verify volume data was stored
        assert obj.zarr() is not None

    def test_add_object_save_config(self, test_payload, tmp_path):
        """Test adding object with config saving."""
        root = test_payload["root"]
        config_path = tmp_path / "saved-config.json"

        add_object(
            root=root,
            name="save-test-object",
            is_particle=True,
            save_config=True,
            config_path=str(config_path),
        )

        # Verify config was saved
        assert config_path.exists()

        # Verify object is in saved config
        new_root = CopickRootFSSpec.from_file(str(config_path))
        saved_obj = new_root.get_object("save-test-object")
        assert saved_obj is not None

    def test_add_object_volume_without_voxel_size(self, test_payload):
        """Test adding object with volume but no voxel size (should fail)."""
        root = test_payload["root"]
        volume_data = np.random.randn(32, 32, 32).astype(np.float32)

        with pytest.raises(ValueError, match="voxel_size must be provided"):
            add_object(
                root=root,
                name="no-voxel-size",
                is_particle=True,
                volume=volume_data,
                # Missing voxel_size
            )

    def test_add_object_save_config_without_path(self, test_payload):
        """Test adding object with save_config=True but no config_path (should fail)."""
        root = test_payload["root"]

        with pytest.raises(ValueError, match="config_path must be provided"):
            add_object(
                root=root,
                name="no-config-path",
                is_particle=True,
                save_config=True,
                # Missing config_path
            )

    def test_add_object_functional_api_with_metadata(self, test_payload):
        """Test adding object with metadata via functional API."""
        root = test_payload["root"]

        metadata_dict = {"key1": "value1", "key2": 42, "key3": {"nested": True}, "array": [1, 2, 3]}

        # Add object with metadata
        obj = add_object(
            root=root,
            name="test-functional-metadata",
            is_particle=True,
            metadata=metadata_dict,
        )

        assert obj is not None, "Object should be created"
        assert obj.metadata == metadata_dict, f"Metadata should match. Got: {obj.metadata}"

        # Verify object is accessible from root with metadata
        retrieved_obj = root.get_object("test-functional-metadata")
        assert retrieved_obj is not None, "Object should exist"
        assert retrieved_obj.metadata == metadata_dict, "Metadata should persist"

    def test_add_object_functional_api_without_metadata(self, test_payload):
        """Test adding object without metadata via functional API (should default to empty dict)."""
        root = test_payload["root"]

        # Add object without metadata
        obj = add_object(
            root=root,
            name="test-functional-no-metadata",
            is_particle=True,
        )

        assert obj is not None, "Object should be created"
        assert obj.metadata == {}, "Metadata should default to empty dict"

    def test_add_object_functional_api_with_none_metadata(self, test_payload):
        """Test adding object with None metadata via functional API (should default to empty dict)."""
        root = test_payload["root"]

        # Add object with None metadata
        obj = add_object(
            root=root,
            name="test-functional-none-metadata",
            is_particle=True,
            metadata=None,
        )

        assert obj is not None, "Object should be created"
        assert obj.metadata == {}, "Metadata should default to empty dict when None"

    def test_add_object_with_metadata_and_config_save(self, test_payload, tmp_path):
        """Test adding object with metadata and saving config preserves metadata."""
        root = test_payload["root"]
        config_path = tmp_path / "metadata-saved-config.json"

        metadata_dict = {"key1": "value1", "key2": 42, "nested": {"inner": True}}

        obj = add_object(
            root=root,
            name="test-metadata-save",
            is_particle=True,
            metadata=metadata_dict,
            save_config=True,
            config_path=str(config_path),
        )

        assert obj.metadata == metadata_dict

        # Verify metadata persists after reloading config
        root_reloaded = CopickRootFSSpec.from_file(str(config_path))
        obj_reloaded = root_reloaded.get_object("test-metadata-save")
        assert obj_reloaded is not None, "Object should exist after reload"
        assert obj_reloaded.metadata == metadata_dict, "Metadata should persist after reload"


class TestAddObjectVolumeFunction:
    """Test cases for the add_object_volume function."""

    def test_add_object_volume_basic(self, test_payload):
        """Test adding volume to existing object."""
        root = test_payload["root"]

        # First create an object
        root.new_object(name="volume-target", is_particle=True)

        # Create volume data
        np.random.seed(42)
        volume_data = np.random.randn(32, 32, 32).astype(np.float32)

        # Add volume to object
        obj = add_object_volume(
            root=root,
            object_name="volume-target",
            volume=volume_data,
            voxel_size=15.0,
        )

        assert obj.name == "volume-target"
        assert obj.zarr() is not None

    def test_add_object_volume_nonexistent_object(self, test_payload):
        """Test adding volume to non-existent object (should fail)."""
        root = test_payload["root"]
        volume_data = np.random.randn(32, 32, 32).astype(np.float32)

        with pytest.raises(ValueError, match="not found in root configuration"):
            add_object_volume(
                root=root,
                object_name="nonexistent-object",
                volume=volume_data,
                voxel_size=10.0,
            )

    def test_add_object_volume_segmentation_object(self, test_payload):
        """Test adding volume to segmentation object (should fail)."""
        root = test_payload["root"]

        # Create a segmentation object (is_particle=False)
        root.new_object(name="segmentation-object", is_particle=False)

        volume_data = np.random.randn(32, 32, 32).astype(np.float32)

        with pytest.raises(ValueError, match="not a particle object"):
            add_object_volume(
                root=root,
                object_name="segmentation-object",
                volume=volume_data,
                voxel_size=10.0,
            )

    def test_add_object_volume_to_particle_object(self, test_payload):
        """Test adding volume to particle object (should succeed)."""
        root = test_payload["root"]

        # Create a particle object (is_particle=True)
        root.new_object(name="particle-object", is_particle=True)

        volume_data = np.random.randn(32, 32, 32).astype(np.float32)

        # This should work
        obj = add_object_volume(
            root=root,
            object_name="particle-object",
            volume=volume_data,
            voxel_size=10.0,
        )

        assert obj.name == "particle-object"
        assert obj.is_particle is True
        assert obj.zarr() is not None

    def test_add_object_volume_to_read_only_object(self, test_payload):
        """Test adding volume to read-only object (should fail)."""
        root = test_payload["root"]

        # Check if we can find an existing object that might be read-only
        existing_obj = root.get_object("proteasome")
        if existing_obj and existing_obj.is_particle and hasattr(existing_obj, "read_only") and existing_obj.read_only:
            volume_data = np.random.randn(32, 32, 32).astype(np.float32)

            with pytest.raises(ValueError, match="read-only"):
                add_object_volume(
                    root=root,
                    object_name="proteasome",
                    volume=volume_data,
                    voxel_size=10.0,
                )
        else:
            # Skip test if no read-only objects available
            pytest.skip("No read-only particle objects available for testing")


class TestPickableObjectModel:
    """Test cases for the PickableObject model metadata functionality."""

    def test_pickable_object_model_with_metadata(self):
        """Test PickableObject model with metadata field."""
        from copick.models import PickableObject

        metadata_dict = {"key1": "value1", "key2": 42}

        obj = PickableObject(name="test-object", is_particle=True, metadata=metadata_dict, identifier=None)

        assert obj.metadata == metadata_dict, "Metadata should be preserved in model"

    def test_pickable_object_model_without_metadata(self):
        """Test PickableObject model without metadata field (should default to empty dict)."""
        from copick.models import PickableObject

        obj = PickableObject(name="test-object", is_particle=True)

        assert obj.metadata == {}, "Metadata should default to empty dict"

    def test_pickable_object_model_with_none_metadata(self):
        """Test PickableObject model with None metadata."""
        from copick.models import PickableObject

        obj = PickableObject(name="test-object", is_particle=True, metadata=None, identifier=None)

        assert obj.metadata == {}, "Metadata should default to empty dict when None"

    def test_pickable_object_model_complex_metadata(self):
        """Test PickableObject model with complex metadata structures."""
        from copick.models import PickableObject

        complex_metadata = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "nested": {"inner": "nested_value", "array": [1, 2, 3], "nested_object": {"deep": "value"}},
            "array": ["a", "b", "c"],
            "mixed_array": [1, "two", {"three": 3}],
        }

        obj = PickableObject(name="complex-object", is_particle=True, metadata=complex_metadata)

        assert obj.metadata == complex_metadata, "Complex metadata should be preserved"
