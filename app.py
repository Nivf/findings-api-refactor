import dataclasses
import logging

from flask import Flask, jsonify, request

from database.models import FindingStatus
from service.findings_service import (
    FindingsQuery,
    FindingsService,
    InvalidFindingsQueryError,
)
from store.findings_store import SqlAlchemyFindingsStore

logger = logging.getLogger(__name__)
VALID_STATUSES = {s.value for s in FindingStatus}


# App factory -- avoids building a real FindingsService (and its DB
# connection) at import time, so route handlers can be tested with a fake
# service and no live database.
def create_app(findings_service: FindingsService) -> Flask:
    app = Flask(__name__)

    @app.route("/api/findings", methods=["GET"])
    def get_findings():
        try:
            query = _parse_query(request)
        except InvalidFindingsQueryError as exc:
            return jsonify({"error": str(exc)}), 400

        logger.info(
            "findings query: delta_hours=%s algorithm_type=%s min_findings=%s page=%s",
            query.delta_time_hours, query.algorithm_type, query.min_findings, query.page,
        )

        try:
            result = findings_service.get_findings(query)
        except Exception:
            # Log full details server-side; never return them to the client.
            logger.exception("failed to fetch findings")
            return jsonify({"error": "Internal server error"}), 500

        return jsonify(dataclasses.asdict(result)), 200

    @app.route("/api/findings/status", methods=["POST"])
    def update_findings_status():
        body = request.get_json(silent=True) or {}
        finding_ids = body.get("finding_ids")
        new_status = body.get("status")

        if not isinstance(finding_ids, list) or not finding_ids:
            return jsonify({"error": "finding_ids must be a non-empty list"}), 400
        if new_status not in VALID_STATUSES:
            return jsonify({"error": f"status must be one of {sorted(VALID_STATUSES)}"}), 400

        try:
            result = findings_service.update_statuses(finding_ids, new_status)
        except Exception:
            logger.exception("failed to update finding statuses")
            return jsonify({"error": "Internal server error"}), 500

        # All-or-nothing: any failure means nothing in the batch committed.
        status_code = 200 if not result.failed else 409
        return jsonify(dataclasses.asdict(result)), status_code

    return app


def _parse_query(req) -> FindingsQuery:
    # request.args.get(key, type=int) returns None on invalid input
    # instead of raising, so we parse manually to surface a 400.
    kwargs = {}

    raw_delta = request.args.get("delta_time")
    if raw_delta is not None:
        kwargs["delta_time_hours"] = _require_int(raw_delta, "delta_time")

    algorithm_type = request.args.get("algorithm_type")
    if algorithm_type:
        kwargs["algorithm_type"] = algorithm_type

    raw_min_findings = request.args.get("min_findings")
    if raw_min_findings is not None:
        kwargs["min_findings"] = _require_int(raw_min_findings, "min_findings")

    raw_page = request.args.get("page")
    if raw_page is not None:
        kwargs["page"] = _require_int(raw_page, "page")

    raw_page_size = request.args.get("page_size")
    if raw_page_size is not None:
        kwargs["page_size"] = _require_int(raw_page_size, "page_size")

    return FindingsQuery(**kwargs)  # raises InvalidFindingsQueryError on bad values


def _require_int(raw_value: str, field_name: str) -> int:
    try:
        return int(raw_value)
    except ValueError:
        raise InvalidFindingsQueryError(f"{field_name} must be an integer, got {raw_value!r}")


if __name__ == "__main__":
    from database.session import get_db_session, init_db

    init_db()
    app = create_app(FindingsService(SqlAlchemyFindingsStore(get_db_session)))
    app.run(debug=True, port=5000)
