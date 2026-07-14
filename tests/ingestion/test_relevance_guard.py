from services.ingestion.relevance import _parse_verdict, enforce_football_relevance


def test_parse_verdict_yes():
    assert _parse_verdict("YES") == "YES"
    assert _parse_verdict("yes.") == "YES"


def test_parse_verdict_no_or_garbage():
    assert _parse_verdict("NO") == "NO"
    assert _parse_verdict("Yes, this is football") == "NO"
    assert _parse_verdict("") == "NO"


def test_enforce_football_relevance(mocker):
    mocker.patch(
        "services.ingestion.relevance.invoke_llm",
        return_value="YES",
    )
    assert enforce_football_relevance("Arsenal beat Chelsea 2-1", "notes.txt") == "YES"


def test_enforce_football_relevance_rejects(mocker):
    mocker.patch(
        "services.ingestion.relevance.invoke_llm",
        return_value="NO",
    )
    from services.ingestion.errors import FootballRelevanceError
    import pytest

    with pytest.raises(FootballRelevanceError):
        enforce_football_relevance("Quarterly revenue report", "earnings.csv")
