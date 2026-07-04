import re
from urllib.parse import urlsplit

_REPEATED_SLASHES = re.compile(r"/+")
_PATH_PARAMETER = re.compile(
    r"^(?:\{[^/{}]+\}|:[^/]+|\$\{[^/{}]+\}|\d+)$"
)


def normalize_api_path(raw_path: str) -> str:
    parsed_path = urlsplit(raw_path.strip()).path
    collapsed_path = _REPEATED_SLASHES.sub("/", parsed_path)
    segments = [
        segment
        for segment in collapsed_path.strip("/").split("/")
        if segment
    ]
    normalized_segments = [
        "{param}" if _PATH_PARAMETER.fullmatch(segment) else segment
        for segment in segments
    ]
    if not normalized_segments:
        return "/"
    return "/" + "/".join(normalized_segments)
