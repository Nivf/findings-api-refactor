"""Tests the request parser directly, with a plain fake standing in for
Flask's `request` -- no Flask app, no test client needed."""

import pytest

from request_parser import FindingsRequestParser
from service.findings_service import InvalidFindingsQueryError, InvalidStatusUpdateRequestError


class FakeArgs:
    def __init__(self, values):
        self._values = values

    def get(self, key, default=None):
        return self._values.get(key, default)


class FakeRequest:
    def __init__(self, args=None, json_body=None):
        self.args = FakeArgs(args or {})
        self._json_body = json_body

    def get_json(self, silent=True):
        return self._json_body


def test_parse_query_defaults_when_nothing_supplied():
    parser = FindingsRequestParser()

    query = parser.parse_query(FakeRequest())

    assert query.delta_time_hours == 24
    assert query.page == 1


def test_parse_query_rejects_non_integer_delta_time():
    parser = FindingsRequestParser()

    with pytest.raises(InvalidFindingsQueryError):
        parser.parse_query(FakeRequest(args={"delta_time": "abc"}))


def test_parse_update_request_builds_valid_request():
    parser = FindingsRequestParser()

    update_request = parser.parse_update_request(
        FakeRequest(json_body={"finding_ids": ["f1", "f2"], "status": "completed"})
    )

    assert update_request.finding_ids == ["f1", "f2"]
    assert update_request.new_status == "completed"


def test_parse_update_request_rejects_missing_body():
    parser = FindingsRequestParser()

    with pytest.raises(InvalidStatusUpdateRequestError):
        parser.parse_update_request(FakeRequest(json_body=None))
