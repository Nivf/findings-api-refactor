"""Turns raw HTTP request data into validated service-layer request
objects. Kept separate from app.py's routing so parsing/validation logic
is testable without a Flask app or test client, and reusable if another
transport (a CLI, a queue consumer) ever needs the same requests."""

from service.findings_service import (
    FindingsQuery,
    InvalidFindingsQueryError,
    UpdateStatusRequest,
)


class FindingsRequestParser:
    def parse_query(self, req) -> FindingsQuery:
        # req.args.get(key, type=int) returns None on invalid input instead
        # of raising, so we parse manually to surface a 400.
        kwargs = {}

        raw_delta = req.args.get("delta_time")
        if raw_delta is not None:
            kwargs["delta_time_hours"] = self._require_int(raw_delta, "delta_time")

        algorithm_type = req.args.get("algorithm_type")
        if algorithm_type:
            kwargs["algorithm_type"] = algorithm_type

        raw_min_findings = req.args.get("min_findings")
        if raw_min_findings is not None:
            kwargs["min_findings"] = self._require_int(raw_min_findings, "min_findings")

        raw_page = req.args.get("page")
        if raw_page is not None:
            kwargs["page"] = self._require_int(raw_page, "page")

        raw_page_size = req.args.get("page_size")
        if raw_page_size is not None:
            kwargs["page_size"] = self._require_int(raw_page_size, "page_size")

        return FindingsQuery(**kwargs)  # raises InvalidFindingsQueryError on bad values

    def parse_update_request(self, req) -> UpdateStatusRequest:
        body = req.get_json(silent=True) or {}
        return UpdateStatusRequest(
            finding_ids=body.get("finding_ids"),
            new_status=body.get("status"),
        )  # raises InvalidStatusUpdateRequestError on bad values

    def _require_int(self, raw_value: str, field_name: str) -> int:
        try:
            return int(raw_value)
        except ValueError:
            raise InvalidFindingsQueryError(f"{field_name} must be an integer, got {raw_value!r}")
