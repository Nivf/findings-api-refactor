import dataclasses
import logging
from functools import wraps

from flask import Flask, jsonify, request

from request_parser import FindingsRequestParser
from service.findings_service import (
    FindingsService,
    InvalidFindingsQueryError,
    InvalidStatusUpdateRequestError,
)
from store.findings_store import SqlAlchemyFindingsStore

logger = logging.getLogger(__name__)


def create_app(findings_service: FindingsService, request_parser: FindingsRequestParser) -> Flask:
    app = Flask(__name__)

    def parsed(parse_method, error_type):
        """Parses the request via `parse_method` before the view runs,
        and converts `error_type` into a 400. Views only ever see a
        valid, already-parsed request."""

        def decorator(view_func):
            @wraps(view_func)
            def wrapper():
                try:
                    parsed_request = parse_method(request)
                except error_type as exc:
                    return jsonify({"error": str(exc)}), 400
                return view_func(parsed_request)

            return wrapper

        return decorator

    @app.route("/api/findings", methods=["GET"])
    @parsed(request_parser.parse_query, InvalidFindingsQueryError)
    def get_findings(query):
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

    @app.route("/api/findings", methods=["PATCH"])
    @parsed(request_parser.parse_update_request, InvalidStatusUpdateRequestError)
    def update_findings_status(update_request):
        try:
            result = findings_service.update_statuses(update_request)
        except Exception:
            logger.exception("failed to update finding statuses")
            return jsonify({"error": "Internal server error"}), 500

        # All-or-nothing: any failure means nothing in the batch committed.
        # The service already logs *why* it rolled back; this just reports
        # the outcome to the client.
        status_code = 200 if not result.failed else 409
        return jsonify(dataclasses.asdict(result)), status_code

    return app


if __name__ == "__main__":
    from database.session import get_db_session, init_db

    init_db()
    app = create_app(
        FindingsService(SqlAlchemyFindingsStore(get_db_session)),
        FindingsRequestParser(),
    )
    app.run(debug=True, port=5000)
