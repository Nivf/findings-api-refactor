import dataclasses
import logging

from flask import Flask, jsonify, request

from service.findings_service import FindingsQuery, FindingsService, InvalidFindingsQueryError
from store.findings_store import SqlAlchemyFindingsStore

logger = logging.getLogger(__name__)


# App factory instead of a module-level `app`/`findings_service` built at
# import time. That original pattern meant importing app.py had the side
# effect of constructing a real FindingsService(FindingsStore()) wired to a
# real DB -- so no test could import the route handlers without a live DB
# connection. This makes findings_service an injected dependency, same DI
# pattern as everywhere else, and lets tests build a Flask test client
# around a fake FindingsService.
def create_app(findings_service: FindingsService) -> Flask:
    app = Flask(__name__)

    @app.route("/api/findings", methods=["GET"])
    def get_findings():
        try:
            query = _parse_query(request)
        except InvalidFindingsQueryError as exc:
            # Was previously indistinguishable from a real server bug --
            # both fell into the bare `except Exception` below and came
            # back as a 500. A bad request is a 400.
            return jsonify({"error": str(exc)}), 400

        logger.info(
            "findings query: delta_hours=%s algorithm_type=%s min_findings=%s page=%s",
            query.delta_time_hours, query.algorithm_type, query.min_findings, query.page,
        )

        try:
            result = findings_service.get_findings(query)
        except Exception:
            # Log the full exception server-side; never return str(e) to
            # the caller -- the original code did, which can leak internal
            # details (table/column names, stack fragments) to any client.
            # Worth flagging extra hard here: this endpoint returns patient
            # name/age/gender with no auth/authorization check visible
            # anywhere in this codebase. That's a bigger gap than this
            # refactor can respond to (needs a real auth story), but it's
            # exactly the kind of thing to say out loud in an interview on
            # a healthcare-data codebase.
            logger.exception("failed to fetch findings")
            return jsonify({"error": "Internal server error"}), 500

        return jsonify(dataclasses.asdict(result)), 200

    return app


def _parse_query(req) -> FindingsQuery:
    # "2. validate input" -- Flask's `type=int` bug: request.args.get(...,
    # type=int) does NOT raise on a bad value like "abc"; it silently
    # returns None, which then falls through to the default. A caller who
    # typos delta_time gets no error at all and unknowingly gets the
    # default 24h window instead of what they asked for. Parsing manually
    # here so bad input is a 400, not silent wrong behavior -- this is the
    # "another missing bug, like pagination" gap.
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
