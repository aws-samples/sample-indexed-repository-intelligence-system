"""
Unit tests for artifact data models (DiscoveredArtifact, ExtractionResult, ArtifactOverview).
"""

import pytest

from iris.artifacts import (
    ExtractionResult,
    ArtifactOverview,
    ARTIFACT_FORMATS,
    SUPPORTED_EXTENSIONS,
    KNOWN_PHASES,
    KNOWN_TYPES,
    EXTENSION_TO_EXTRACTOR,
    FORMAT_ORDER,
    FORMAT_NAMES,
    RECOMMENDED_FOLDER_MAP,
    format_extension_list,
)

# Extractor names recognised by artifact_extractors.extract_artifact
KNOWN_EXTRACTOR_NAMES = {"pptx", "docx", "xlsx", "docs", "pdf", "video"}


class TestConstants:
    """Test module-level constants."""

    def test_supported_extensions_include_all_formats(self):
        expected = {
            ".pptx",
            ".docx",
            ".xlsx",
            ".pdf",
            ".md",
            ".txt",
            ".mp4",
            ".mov",
            ".avi",
            ".mkv",
        }
        assert SUPPORTED_EXTENSIONS == expected

    def test_known_phases(self):
        assert KNOWN_PHASES == {"pre-project", "during-project", "post-project"}

    def test_known_types_per_phase(self):
        assert "presentations" in KNOWN_TYPES["during-project"]
        assert "readouts" in KNOWN_TYPES["pre-project"]
        assert "production_readiness" in KNOWN_TYPES["post-project"]

    def test_extension_to_extractor_covers_all_supported(self):
        for ext in SUPPORTED_EXTENSIONS:
            assert ext in EXTENSION_TO_EXTRACTOR, f"Missing extractor for {ext}"


class TestArtifactFormatRegistry:
    """ARTIFACT_FORMATS is the single source of truth; check its derived views."""

    def test_extensions_are_lowercase_and_dotted(self):
        for fmt in ARTIFACT_FORMATS:
            assert fmt.extension.startswith("."), fmt.extension
            assert fmt.extension == fmt.extension.lower(), fmt.extension

    def test_extensions_are_unique(self):
        extensions = [fmt.extension for fmt in ARTIFACT_FORMATS]
        assert len(extensions) == len(set(extensions))

    def test_every_extractor_is_dispatchable(self):
        """A format with no extractor would be discovered then fail extraction."""
        for fmt in ARTIFACT_FORMATS:
            assert (
                fmt.extractor in KNOWN_EXTRACTOR_NAMES
            ), f"{fmt.extension} maps to unknown extractor '{fmt.extractor}'"

    def test_derived_views_cover_the_registry(self):
        assert SUPPORTED_EXTENSIONS == {fmt.extension for fmt in ARTIFACT_FORMATS}
        assert set(EXTENSION_TO_EXTRACTOR) == SUPPORTED_EXTENSIONS
        assert set(FORMAT_NAMES) == {ext.lstrip(".") for ext in SUPPORTED_EXTENSIONS}
        assert set(FORMAT_ORDER) == set(FORMAT_NAMES)

    def test_format_order_matches_registry(self):
        for fmt in ARTIFACT_FORMATS:
            assert FORMAT_ORDER[fmt.extension.lstrip(".")] == fmt.order

    def test_every_format_has_a_description(self):
        for fmt in ARTIFACT_FORMATS:
            assert fmt.description.strip(), fmt.extension

    def test_format_extension_list_is_sorted_and_complete(self):
        rendered = format_extension_list()
        assert rendered == ", ".join(sorted(SUPPORTED_EXTENSIONS))
        for ext in SUPPORTED_EXTENSIONS:
            assert ext in rendered

    def test_recommended_folder_map_uses_registered_extensions(self):
        """Advisory folder extensions must not drift from the registry."""
        for phase, types in RECOMMENDED_FOLDER_MAP.items():
            for material_type, extensions in types.items():
                for ext in extensions:
                    assert (
                        ext in SUPPORTED_EXTENSIONS
                    ), f"{phase}/{material_type} lists unsupported '{ext}'"

    def test_registry_is_immutable(self):
        with pytest.raises(AttributeError):
            ARTIFACT_FORMATS[0].extension = ".zip"


class TestArtifactOverview:
    """Test ArtifactOverview data model."""

    def test_create_from_dict(self):
        data = {
            "purpose": "Weekly status presentation",
            "source_material_type": "presentations",
            "project_phase": "during-project",
            "file_format": "pptx",
            "key_topics": ["status", "blockers"],
            "related_artifacts": ["readouts/week1.docx"],
            "summary": "Covers week 1 progress.",
        }

        overview = ArtifactOverview.from_dict(data)

        assert overview.purpose == "Weekly status presentation"
        assert overview.source_material_type == "presentations"
        assert overview.project_phase == "during-project"
        assert overview.file_format == "pptx"
        assert overview.key_topics == ["status", "blockers"]
        assert overview.related_artifacts == ["readouts/week1.docx"]
        assert overview.summary == "Covers week 1 progress."

    def test_to_dict_roundtrip(self):
        original = ArtifactOverview(
            purpose="Test",
            source_material_type="presentations",
            project_phase="during-project",
            file_format="pptx",
            key_topics=["a", "b"],
            related_artifacts=[],
            summary="Summary.",
        )

        data = original.to_dict()
        restored = ArtifactOverview.from_dict(data)

        assert restored.purpose == original.purpose
        assert restored.key_topics == original.key_topics
        assert restored.summary == original.summary

    def test_to_json_roundtrip(self):
        original = ArtifactOverview(
            purpose="Test",
            source_material_type="reports",
            project_phase="post-project",
            file_format="pdf",
        )

        json_str = original.to_json()
        restored = ArtifactOverview.from_json(json_str)

        assert restored.purpose == original.purpose
        assert restored.file_format == "pdf"

    def test_from_dict_missing_required_field_raises(self):
        data = {"purpose": "Test"}  # missing required fields

        with pytest.raises((KeyError, TypeError)):
            ArtifactOverview.from_dict(data)

    def test_from_dict_optional_fields_default(self):
        data = {
            "purpose": "Test",
            "source_material_type": "presentations",
            "project_phase": "during-project",
            "file_format": "pptx",
        }

        overview = ArtifactOverview.from_dict(data)

        assert overview.key_topics == []
        assert overview.related_artifacts == []
        assert overview.summary == ""


class TestExtractionResult:
    """Test ExtractionResult data model."""

    def test_successful_extraction(self):
        result = ExtractionResult(
            file_path="presentations/week1.pptx",
            content="Slide 1: Hello\nSlide 2: World",
            file_format="pptx",
            project_phase="during-project",
            source_material_type="presentations",
            success=True,
        )

        assert result.success
        assert result.error_message is None
        assert "Hello" in result.content

    def test_failed_extraction(self):
        result = ExtractionResult(
            file_path="corrupted.pdf",
            content="",
            file_format="pdf",
            project_phase="unclassified",
            source_material_type="unclassified",
            success=False,
            error_message="File is corrupted",
        )

        assert not result.success
        assert result.error_message == "File is corrupted"
        assert result.content == ""


@pytest.mark.unit
class TestResolveArtifactDir:
    """Test resolve_artifact_dir config gating."""

    def test_unset_returns_none(self):
        from iris.artifacts import resolve_artifact_dir

        assert resolve_artifact_dir({}) is None

    def test_none_returns_none(self):
        from iris.artifacts import resolve_artifact_dir

        assert resolve_artifact_dir({"artifact_dir": None}) is None

    def test_blank_returns_none(self):
        from iris.artifacts import resolve_artifact_dir

        assert resolve_artifact_dir({"artifact_dir": "   "}) is None

    def test_template_placeholder_returns_none(self):
        """The shipped config placeholder must not enable artifact indexing."""
        from iris.artifacts import resolve_artifact_dir, ARTIFACT_DIR_PLACEHOLDER

        assert resolve_artifact_dir({"artifact_dir": ARTIFACT_DIR_PLACEHOLDER}) is None

    def test_nonexistent_path_returns_none(self):
        from iris.artifacts import resolve_artifact_dir

        assert (
            resolve_artifact_dir({"artifact_dir": "/does/not/exist/anywhere"}) is None
        )

    def test_file_instead_of_dir_returns_none(self, tmp_path):
        from iris.artifacts import resolve_artifact_dir

        f = tmp_path / "notadir.txt"
        f.write_text("x")
        assert resolve_artifact_dir({"artifact_dir": str(f)}) is None

    def test_real_directory_is_returned(self, tmp_path):
        from iris.artifacts import resolve_artifact_dir

        assert resolve_artifact_dir({"artifact_dir": str(tmp_path)}) == str(tmp_path)
