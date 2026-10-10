"""Tests for the issue #1 concept document in docs/concept/."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONCEPT_DIR = ROOT / "docs" / "concept"
CONCEPT = CONCEPT_DIR / "README.md"

# Two A4 pages hold roughly 1000-1100 words of prose next to three diagrams,
# two screenshots and a table; experiments/render_concept_pdf.py measures the
# real page count. The word budget catches growth without a browser.
MAX_PROSE_WORDS = 1050


def read_concept() -> str:
    """Read the concept document."""
    return CONCEPT.read_text(encoding="utf-8")


def prose_words(text: str) -> int:
    """Count words outside code fences, ignoring link targets."""
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    return len(text.split())


def test_concept_has_both_parts_and_two_examples() -> None:
    """The assignment asks for two reference examples and a proposal."""
    headings = re.findall(r"^#{2,3} (.+)$", read_concept(), flags=re.MULTILINE)

    assert any(h.startswith("Часть 1") for h in headings)
    assert any(h.startswith("Часть 2") for h in headings)
    assert len([h for h in headings if h.startswith("Пример")]) == 2


def test_each_example_covers_the_required_points() -> None:
    """Each example needs adoption, limits, source of knowledge, and a visual."""
    text = read_concept()
    examples = re.split(r"^### ", text, flags=re.MULTILINE)[1:]
    examples = [e for e in examples if e.startswith("Пример")]

    for example in examples:
        assert "Что делает и роль AI" in example
        assert "Что взять" in example
        assert "Ограничения" in example
        assert "Источник знаний" in example
        assert "```mermaid" in example
        assert re.search(r"!\[[^\]]+\]\([^)]+\.png\)", example)
        assert re.search(r"\]\(https://", example)


def test_proposal_covers_the_required_points() -> None:
    """Part 2 needs build vs buy, daily use, a scenario, and a pilot."""
    part2 = read_concept().split("## Часть 2", 1)[1]

    for marker in (
        "Купить или собрать",
        "Как пользуются",
        "Сквозной сценарий",
        "Обнаружение",
        "Предложение",
        "Утверждение",
        "Исполнение",
        "Проверка",
        "Пилот",
        "Что проверяем",
        "Метрика",
        "Главный риск",
        "Открытые вопросы",
    ):
        assert marker in part2, marker
    assert "```mermaid" in part2
    assert "tasks.task.add" in part2


def test_referenced_images_exist_next_to_the_document() -> None:
    """Screenshots must be image files stored next to the concept."""
    images = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", read_concept())

    assert len(images) >= 2
    for image in images:
        assert "/" not in image, image
        assert (CONCEPT_DIR / image).is_file(), image


def test_local_links_resolve() -> None:
    """Relative links in the concept and its appendix point to real files."""
    for doc in (CONCEPT, CONCEPT_DIR / "sources.md"):
        for target in re.findall(r"\]\(([^)]+)\)", doc.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            assert (doc.parent / target).is_file(), f"{doc.name}: {target}"


def test_concept_stays_within_the_length_budget() -> None:
    """The assignment limits the result to two pages."""
    assert prose_words(read_concept()) <= MAX_PROSE_WORDS


def test_readme_links_to_the_result_first() -> None:
    """The project README must point to the concept before any other link."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    first_link = re.search(r"\]\(([^)]+)\)", readme)

    assert first_link is not None
    assert first_link.group(1) == "docs/concept/README.md"


def test_concept_is_in_the_sphinx_toctree() -> None:
    """Sphinx builds with -W, so the concept pages must be in a toctree."""
    index = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")

    assert "concept/README" in index
    assert "concept/sources" in index
