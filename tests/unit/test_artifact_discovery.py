"""
Unit tests for artifact discovery and classification.
"""

import pytest
from pathlib import Path

from iris.artifacts import (
    DiscoveredArtifact,
)
from iris.artifacts.artifact_discovery import (
    discover_artifacts,
    get_extractor_for_artifact,
    _classify_path,
)


class TestClassifyPath:
    """Test the path classification logic."""

    def test_recognized_phase_and_type(self):
        phase, mat_type = _classify_path(
            Path("during-project/presentations/week1.pptx")
        )
        assert phase == "during-project"
        assert mat_type == "presentations"

    def test_pre_project_readouts(self):
        phase, mat_type = _classify_path(Path("pre-project/readouts/kickoff.docx"))
        assert phase == "pre-project"
        assert mat_type == "readouts"

    def test_post_project_production_readiness(self):
        phase, mat_type = _classify_path(
            Path("post-project/production_readiness/report.pdf")
        )
        assert phase == "post-project"
        assert mat_type == "production_readiness"

    def test_unrecognized_phase(self):
        phase, mat_type = _classify_path(Path("random-folder/file.pptx"))
        assert phase == "unclassified"
        assert mat_type == "unclassified"

    def test_unrecognized_type_under_known_phase(self):
        phase, mat_type = _classify_path(Path("during-project/unknown_type/file.pptx"))
        assert phase == "unclassified"
        assert mat_type == "unclassified"

    def test_single_component_path(self):
        phase, mat_type = _classify_path(Path("file.pptx"))
        assert phase == "unclassified"
        assert mat_type == "unclassified"

    def test_deeply_nested_path(self):
        phase, mat_type = _classify_path(
            Path("during-project/presentations/subdir/deep/file.pptx")
        )
        assert phase == "during-project"
        assert mat_type == "presentations"


class TestDiscoverArtifacts:
    """Test artifact discovery with real filesystem."""

    def test_discover_empty_directory(self, temp_dir):
        artifacts = discover_artifacts(temp_dir)
        assert artifacts == []

    def test_discover_nonexistent_directory(self, temp_dir):
        artifacts = discover_artifacts(temp_dir / "nonexistent")
        assert artifacts == []

    def test_discover_supported_files(self, temp_dir):
        (temp_dir / "doc.md").write_text("# Test")
        (temp_dir / "notes.txt").write_text("Notes")

        artifacts = discover_artifacts(temp_dir)

        assert len(artifacts) == 2
        paths = {a.file_path for a in artifacts}
        assert "doc.md" in paths
        assert "notes.txt" in paths

    def test_discover_ignores_unsupported_extensions(self, temp_dir):
        (temp_dir / "doc.md").write_text("# Test")
        (temp_dir / "image.png").write_bytes(b"\x89PNG")
        (temp_dir / "data.csv").write_text("a,b,c")

        artifacts = discover_artifacts(temp_dir)

        assert len(artifacts) == 1
        assert artifacts[0].file_path == "doc.md"

    def test_discover_skips_office_temp_files(self, temp_dir):
        (temp_dir / "doc.docx").write_bytes(b"fake docx")
        (temp_dir / "~$doc.docx").write_bytes(b"temp file")

        artifacts = discover_artifacts(temp_dir)

        assert len(artifacts) == 1
        assert artifacts[0].file_path == "doc.docx"

    def test_discover_with_recommended_structure(self, temp_dir):
        # Create recommended folder structure
        pres_dir = temp_dir / "during-project" / "presentations"
        pres_dir.mkdir(parents=True)
        (pres_dir / "week1.pptx").write_bytes(b"fake pptx")

        readout_dir = temp_dir / "pre-project" / "readouts"
        readout_dir.mkdir(parents=True)
        (readout_dir / "kickoff.docx").write_bytes(b"fake docx")

        artifacts = discover_artifacts(temp_dir)

        assert len(artifacts) == 2

        by_path = {a.file_path: a for a in artifacts}

        presentation = by_path["during-project/presentations/week1.pptx"]
        assert presentation.project_phase == "during-project"
        assert presentation.source_material_type == "presentations"
        assert presentation.file_format == "pptx"

        readout = by_path["pre-project/readouts/kickoff.docx"]
        assert readout.project_phase == "pre-project"
        assert readout.source_material_type == "readouts"

    def test_discover_unclassified_files(self, temp_dir):
        (temp_dir / "random.pdf").write_bytes(b"fake pdf")

        artifacts = discover_artifacts(temp_dir)

        assert len(artifacts) == 1
        assert artifacts[0].project_phase == "unclassified"
        assert artifacts[0].source_material_type == "unclassified"

    def test_discover_returns_sorted_results(self, temp_dir):
        (temp_dir / "b.md").write_text("b")
        (temp_dir / "a.md").write_text("a")
        (temp_dir / "c.md").write_text("c")

        artifacts = discover_artifacts(temp_dir)

        paths = [a.file_path for a in artifacts]
        assert paths == sorted(paths)

    def test_discover_sets_absolute_path(self, temp_dir):
        (temp_dir / "doc.md").write_text("test")

        artifacts = discover_artifacts(temp_dir)

        assert artifacts[0].absolute_path.is_absolute()
        assert artifacts[0].absolute_path.exists()


class TestGetExtractorForArtifact:
    """Test extractor selection based on file format."""

    @pytest.mark.parametrize(
        "file_format,expected_extractor",
        [
            ("pptx", "pptx"),
            ("docx", "docx"),
            ("xlsx", "xlsx"),
            ("pdf", "pdf"),
            ("md", "docs"),
            ("txt", "docs"),
            ("mp4", "video"),
            ("mov", "video"),
            ("avi", "video"),
            ("mkv", "video"),
        ],
    )
    def test_extractor_mapping(self, file_format, expected_extractor, temp_dir):
        artifact = DiscoveredArtifact(
            file_path=f"test.{file_format}",
            absolute_path=temp_dir / f"test.{file_format}",
            project_phase="unclassified",
            source_material_type="unclassified",
            file_format=file_format,
        )

        assert get_extractor_for_artifact(artifact) == expected_extractor

    def test_unsupported_format_raises(self, temp_dir):
        artifact = DiscoveredArtifact(
            file_path="test.xyz",
            absolute_path=temp_dir / "test.xyz",
            project_phase="unclassified",
            source_material_type="unclassified",
            file_format="xyz",
        )

        with pytest.raises(ValueError, match="No extractor"):
            get_extractor_for_artifact(artifact)
