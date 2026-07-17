"""Apartment Detail Page — see docs/32_Web_Dashboard.md "Apartment Detail
Page".
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, url_for

from src.web.application import get_dependencies, get_facade
from src.web.constants import DEFAULT_PROFILE_ID
from src.web.error_handler import WebNotFoundError
from src.web.forms.validation import parse_safe_id
from src.web.presenters.apartment_presenter import present_missing_data_summary
from src.web.presenters.serialization import to_jsonable
from src.web.security import WebSecurity

blueprint = Blueprint("apartments", __name__, url_prefix="/apartments")


@blueprint.route("/<apartment_id>")
def detail(apartment_id: str):
    apartment_id = parse_safe_id(apartment_id, "Apartment id")
    facade = get_facade()
    search_id = request.args.get("search_id")
    data = facade.apartment_detail(apartment_id, search_id=search_id, profile_id=DEFAULT_PROFILE_ID)
    data["missing_data"] = present_missing_data_summary(data["apartment"])
    if request.accept_mimetypes.best == "application/json":
        return jsonify(to_jsonable(data))
    data["images_with_urls"] = [(image, _display_url(apartment_id, image)) for image in data["images"]]
    return render_template("apartments/detail.html", active_nav="search", **data)


def _display_url(apartment_id: str, image) -> str:
    """Prefer the already-downloaded local copy over `image.source_url`.

    A demo/fixture connector's `source_url` is a `file://` path (see
    `src/connectors/demo_platform.py`), which no browser will ever load from
    an `http://` page — this platform's own CSP (`img-src 'self' data:`,
    security.py) already assumes same-origin serving. `image.local_path` is
    already downloaded by `analyzers/engine.py` for every image; this route
    is what was missing to actually serve it.
    """
    if image.local_path:
        return url_for("apartments.media", apartment_id=apartment_id, filename=Path(image.local_path).name)
    return image.source_url


@blueprint.route("/<apartment_id>/media/<filename>")
def media(apartment_id: str, filename: str):
    """Reads the file's bytes eagerly (rather than `send_file`'s streaming
    file-wrapper) so no file handle outlives this request — `send_file` was
    observed leaving a handle open on Windows, which then blocked temp-
    directory cleanup in tests (`PermissionError: [WinError 32]`), the same
    category of Windows file-locking issue already seen elsewhere in this
    project's test suite. These are small listing photos, never a large
    stream, so eager reads are the simpler and more portable choice here.
    """
    apartment_id = parse_safe_id(apartment_id, "Apartment id")
    media_dir = get_dependencies().configuration.data_dir / "media"
    path = WebSecurity.safe_join(media_dir, apartment_id, filename)
    if path is None or not path.is_file():
        raise WebNotFoundError(f"No such media file {filename!r} for apartment {apartment_id!r}")
    mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(path.read_bytes(), mimetype=mimetype)
