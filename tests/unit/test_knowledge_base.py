"""
Unit tests for per-artifact storage and knowledge base assembly.
"""

from iris.artifacts import FORMAT_NAMES, ExtractionResult
from iris.artifacts.knowledge_base import (
    save_extracted_artifact,
    load_extracted_artifact,
    build_knowledge_base,
)


class TestSaveAndLoadExtractedArtifact:
    """Test per-artifact .md file storage."""

    def test_save_and_load_roundtrip(self, output_dir):
        result = ExtractionResult(
            file_path="during-project/presentations/week1.pptx",
            content="# Slide 1\nHello World",
            file_format="pptx",
            project_phase="during-project",
            source_material_type="presentations",
            success=True,
        )

        saved_path = save_extracted_artifact(result, output_dir)

        assert saved_path.exists()
        assert saved_path.suffix == ".md"

        loaded = load_extracted_artifact(result.file_path, output_dir)

        assert loaded is not None
        assert "Hello World" in loaded
        assert "source: during-project/presentations/week1.pptx" in loaded

    def test_save_creates_directory_structure(self, output_dir):
        result = ExtractionResult(
            file_path="pre-project/readouts/deep/nested/kickoff.docx",
            content="Kickoff content",
            file_format="docx",
            project_phase="pre-project",
            source_material_type="readouts",
            success=True,
        )

        saved_path = save_extracted_artifact(result, output_dir)

        assert saved_path.exists()
        assert "extracted_artifacts" in str(saved_path)
        assert "pre-project" in str(saved_path)

    def test_load_nonexistent_returns_none(self, output_dir):
        loaded = load_extracted_artifact("nonexistent/file.pptx", output_dir)
        assert loaded is None

    def test_metadata_header_included(self, output_dir):
        result = ExtractionResult(
            file_path="report.pdf",
            content="Report content",
            file_format="pdf",
            project_phase="post-project",
            source_material_type="production_readiness",
            success=True,
        )

        save_extracted_artifact(result, output_dir)
        loaded = load_extracted_artifact(result.file_path, output_dir)

        assert "---" in loaded
        assert "project_phase: post-project" in loaded
        assert "file_format: pdf" in loaded

    def test_different_formats_same_stem_no_collision(self, output_dir):
        """Two artifacts with same stem but different extensions should not collide."""
        result_pdf = ExtractionResult(
            file_path="report.pdf",
            content="PDF content",
            file_format="pdf",
            project_phase="unclassified",
            source_material_type="unclassified",
            success=True,
        )
        result_docx = ExtractionResult(
            file_path="report.docx",
            content="DOCX content",
            file_format="docx",
            project_phase="unclassified",
            source_material_type="unclassified",
            success=True,
        )

        save_extracted_artifact(result_pdf, output_dir)
        save_extracted_artifact(result_docx, output_dir)

        loaded_pdf = load_extracted_artifact("report.pdf", output_dir)
        loaded_docx = load_extracted_artifact("report.docx", output_dir)

        assert "PDF content" in loaded_pdf
        assert "DOCX content" in loaded_docx


class TestBuildKnowledgeBase:
    """Test knowledge base assembly."""

    def test_build_with_successful_results(self, output_dir):
        results = [
            ExtractionResult(
                file_path="presentations/week1.pptx",
                content="Week 1 slides content",
                file_format="pptx",
                project_phase="during-project",
                source_material_type="presentations",
                success=True,
            ),
            ExtractionResult(
                file_path="readouts/kickoff.docx",
                content="Kickoff readout content",
                file_format="docx",
                project_phase="pre-project",
                source_material_type="readouts",
                success=True,
            ),
        ]

        kb_path, total_chars = build_knowledge_base(results, output_dir)

        assert kb_path.exists()
        assert kb_path.name == "knowledge_base.md"
        assert total_chars > 0

        content = kb_path.read_text()
        assert "Week 1 slides content" in content
        assert "Kickoff readout content" in content
        assert "# Knowledge Base" in content

    def test_build_orders_formats_by_registry(self, output_dir):
        """Within a section, results sort by FORMAT_ORDER: pptx→docx→xlsx→docs→pdf→video.

        Guards the derived FORMAT_ORDER view: a format missing from the
        registry would silently sort last instead of in its declared place.
        """
        formats = ["mp4", "pdf", "txt", "xlsx", "docx", "pptx"]
        results = [
            ExtractionResult(
                file_path=f"reports/file.{fmt}",
                content=f"BODY-{fmt}",
                file_format=fmt,
                project_phase="during-project",
                source_material_type="reports",
                success=True,
            )
            for fmt in formats
        ]

        kb_path, _ = build_knowledge_base(results, output_dir)
        content = kb_path.read_text()

        positions = [
            content.index(f"BODY-{fmt}") for fmt in FORMAT_NAMES if fmt in formats
        ]
        assert positions == sorted(
            positions
        ), "knowledge base sections are not ordered by FORMAT_ORDER"

    def test_build_with_no_successful_results(self, output_dir):
        results = [
            ExtractionResult(
                file_path="corrupted.pdf",
                content="",
                file_format="pdf",
                project_phase="unclassified",
                source_material_type="unclassified",
                success=False,
                error_message="Corrupted",
            ),
        ]

        kb_path, total_chars = build_knowledge_base(results, output_dir)

        assert kb_path.exists()
        assert total_chars == 0

    def test_build_with_empty_results(self, output_dir):
        kb_path, total_chars = build_knowledge_base([], output_dir)

        assert kb_path.exists()
        assert total_chars == 0

    def test_build_groups_by_phase_and_type(self, output_dir):
        results = [
            ExtractionResult(
                file_path="a.pptx",
                content="Presentation A",
                file_format="pptx",
                project_phase="during-project",
                source_material_type="presentations",
                success=True,
            ),
            ExtractionResult(
                file_path="b.docx",
                content="Readout B",
                file_format="docx",
                project_phase="pre-project",
                source_material_type="readouts",
                success=True,
            ),
        ]

        kb_path, _ = build_knowledge_base(results, output_dir)
        content = kb_path.read_text()

        # Check phase headers exist
        assert "During Project" in content or "during-project" in content.lower()
        assert "Pre Project" in content or "pre-project" in content.lower()

    def test_build_with_client_and_project(self, output_dir):
        results = [
            ExtractionResult(
                file_path="doc.md",
                content="Content",
                file_format="md",
                project_phase="unclassified",
                source_material_type="unclassified",
                success=True,
            ),
        ]

        kb_path, _ = build_knowledge_base(
            results, output_dir, client="Acme", project="Widget"
        )
        content = kb_path.read_text()

        assert "Acme" in content
        assert "Widget" in content
