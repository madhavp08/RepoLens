import pytest

from app.services.github_service import (
    GitHubError,
    classify_doc_path,
    doc_priority,
    parse_github_url,
)


@pytest.mark.parametrize(
    ("raw", "owner", "name"),
    [
        ("https://github.com/company/product", "company", "product"),
        ("https://github.com/company/product.git", "company", "product"),
        ("http://www.github.com/acme/api/", "acme", "api"),
        ("github.com/acme/api", "acme", "api"),
    ],
)
def test_parse_github_url_accepts_common_forms(raw: str, owner: str, name: str) -> None:
    ref = parse_github_url(raw)
    assert ref.owner == owner
    assert ref.name == name
    assert ref.slug == f"{owner}/{name}"


@pytest.mark.parametrize(
    "raw",
    [
        "https://gitlab.com/acme/api",
        "https://github.com/explore",
        "not a url",
        "https://github.com/settings",
    ],
)
def test_parse_github_url_rejects_non_repos(raw: str) -> None:
    with pytest.raises(GitHubError):
        parse_github_url(raw)


def test_classify_doc_path_keeps_history_sources() -> None:
    assert classify_doc_path("README.md") == "readme"
    assert classify_doc_path("docs/architecture.md") == "markdown"
    assert classify_doc_path("adr/0001-postgres.md") == "adr"
    assert classify_doc_path("CHANGELOG.md") == "changelog"


def test_classify_doc_path_skips_vendor_and_source() -> None:
    assert classify_doc_path("node_modules/pkg/README.md") is None
    assert classify_doc_path("src/auth/service.go") is None
    assert classify_doc_path("package-lock.json") is None


def test_doc_priority_ranks_readme_first() -> None:
    assert doc_priority("README.md") < doc_priority("docs/guide.md")
    assert doc_priority("docs/guide.md") < doc_priority("notes.md")
