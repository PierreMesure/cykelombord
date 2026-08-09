import pytest

from cykelombord.guide import (
    GuideError,
    add_markdown_provenance,
    extract_guide_pdf_url,
    normalise_markdown_layout,
)


def test_extracts_the_swedish_guide_and_ignores_other_pdfs() -> None:
    page = """
    [Cykel på tåg](https://example.org/uploads/2026/Cykel_pa_Tag_2026-06-07.pdf)
    [Beskrivning och kartor](https://example.org/uploads/2026/Cykel_pa_Tag_2026-06-07.pdf)
    [Fahrrad im Zug](https://example.org/uploads/2026/Fahrrad-im-Zug-2026-06-26.pdf)
    [Affisch cykel på tåg](https://example.org/uploads/2023/LNF-affisch-cykel-pa-tag-2023-05.pdf)
    """

    assert extract_guide_pdf_url(page) == "https://example.org/uploads/2026/Cykel_pa_Tag_2026-06-07.pdf"


def test_rejects_an_ambiguous_guide_page() -> None:
    page = """
    [Beskrivning](https://example.org/Cykel_pa_Tag_A.pdf)
    [Beskrivning](https://example.org/Cykel_pa_Tag_B.pdf)
    """

    with pytest.raises(GuideError, match="equally likely"):
        extract_guide_pdf_url(page)


def test_rejects_a_page_without_a_swedish_guide() -> None:
    with pytest.raises(GuideError, match="No Swedish"):
        extract_guide_pdf_url("[Fahrrad im Zug](https://example.org/Fahrrad-im-Zug.pdf)")


def test_joins_an_incomplete_lower_case_column_continuation() -> None:
    markdown = normalise_markdown_layout(
        "Innan vi startar en tur bestämmer vi oss för om det ska vara prestations- eller \n\n"
        "slöcykling. Ibland vill vi helt enkelt cykla."
    )

    assert markdown == (
        "Innan vi startar en tur bestämmer vi oss för om det ska vara prestations- eller "
        "slöcykling. Ibland vill vi helt enkelt cykla."
    )


def test_preserves_a_complete_paragraph_boundary() -> None:
    markdown = normalise_markdown_layout("Första stycket är färdigt.\n\nNästa stycke börjar här.")

    assert markdown == "Första stycket är färdigt.\n\nNästa stycke börjar här."


def test_adds_provenance_to_pymupdf4llm_markdown() -> None:
    markdown = add_markdown_provenance(
        "# Original heading\r\n\r\nA paragraph.\r\n",
        pdf_url="https://example.org/Cykel_pa_Tag.pdf",
        pdf_sha256="abc123",
    )

    assert markdown.startswith("> Generated from the current Naturskyddsföreningen PDF.")
    assert "https://example.org/Cykel_pa_Tag.pdf" in markdown
    assert markdown.endswith("# Original heading\n\nA paragraph.\n")
