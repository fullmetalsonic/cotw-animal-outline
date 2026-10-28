"""Read public stable-release metadata; never download or install an update."""
from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app_version import GITHUB_OWNER, GITHUB_REPO, VERSION

API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASE_PATH = f"/{GITHUB_OWNER}/{GITHUB_REPO}/releases/tag/"
TIMEOUT_SECONDS = 4
MAX_RESPONSE_BYTES = 256 * 1024
_SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?")


def parse_semver(value):
    if not isinstance(value, str) or not 0 < len(value) <= 128:
        raise ValueError("Invalid version")
    text = value[1:] if value.startswith("v") else value
    match = _SEMVER.fullmatch(text)
    if not match:
        raise ValueError("Invalid version")
    pre = tuple(match[4].split(".")) if match[4] else ()
    if any(part.isdigit() and len(part) > 1 and part.startswith("0") for part in pre):
        raise ValueError("Invalid prerelease version")
    return tuple(int(match[index]) for index in (1, 2, 3)), pre


def compare_versions(left, right):
    """SemVer precedence, including prereleases; build metadata is ignored."""
    a_core, a_pre = parse_semver(left)
    b_core, b_pre = parse_semver(right)
    if a_core != b_core:
        return (a_core > b_core) - (a_core < b_core)
    if not a_pre or not b_pre:
        return (not a_pre) - (not b_pre)
    for a, b in zip(a_pre, b_pre):
        if a == b:
            continue
        if a.isdigit() and b.isdigit():
            return (int(a) > int(b)) - (int(a) < int(b))
        if a.isdigit() != b.isdigit():
            return -1 if a.isdigit() else 1
        return (a > b) - (a < b)
    return (len(a_pre) > len(b_pre)) - (len(a_pre) < len(b_pre))


def is_release_url(url, tag=None):
    if not isinstance(url, str) or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        return False
    try:
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc != "github.com" or parts.query
                or parts.fragment or not parts.path.startswith(RELEASE_PATH)):
            return False
        release_tag = unquote(parts.path[len(RELEASE_PATH):])
        if "/" in release_tag or "\\" in release_tag or (tag is not None and release_tag != tag):
            return False
        _, pre = parse_semver(release_tag)
        return not pre
    except ValueError:
        return False


@dataclass(frozen=True)
class UpdateResult:
    status: str
    current: str = VERSION
    latest: str | None = None
    update_needed: bool | None = None
    release_url: str | None = None
    message: str = "업데이트를 확인하지 못했습니다. 모드는 계속 사용할 수 있습니다."


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, newurl):
        return None


def _fetch_latest():
    # Only this fixed public endpoint is requested. Redirects cannot expand it.
    request = Request(API_URL, headers={"Accept": "application/vnd.github+json",
                                       "User-Agent": f"{GITHUB_REPO}/{VERSION}"})
    with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT_SECONDS) as response:
        if response.geturl() != API_URL:
            raise ValueError("Unexpected response URL")
        data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Release metadata is too large")
    return json.loads(data)


def check_update(fetcher=None, current=VERSION):
    """Return a result even when no release/network is available."""
    try:
        parse_semver(current)
        release = (fetcher or _fetch_latest)()
        if not isinstance(release, dict):
            raise ValueError("Expected a release object")
        if release.get("draft") is not False or release.get("prerelease") is not False:
            return UpdateResult("not_stable", current, message="확인할 수 있는 정식 배포가 없습니다.")
        tag = release.get("tag_name")
        _, pre = parse_semver(tag)
        if pre:
            return UpdateResult("not_stable", current, message="확인할 수 있는 정식 배포가 없습니다.")
        if (type(release.get("id")) is not int or release["id"] <= 0
                or not isinstance(release.get("published_at"), str) or not release["published_at"]
                or not is_release_url(release.get("html_url"), tag)):
            raise ValueError("Invalid public release metadata")
        needed = compare_versions(tag, current) > 0
        return UpdateResult("update_available" if needed else "up_to_date", current,
                            tag[1:] if tag.startswith("v") else tag, needed,
                            release["html_url"], "새 버전이 있습니다." if needed else "업데이트가 필요하지 않습니다.")
    except HTTPError as error:
        if error.code in (403, 429):
            return UpdateResult("rate_limited", current, message="지금은 확인할 수 없습니다. 잠시 후 다시 확인하세요.")
        if error.code == 404:
            return UpdateResult("unavailable", current, message="아직 정식 배포 정보를 확인할 수 없습니다.")
        return UpdateResult("unavailable", current)
    except TimeoutError:
        return UpdateResult("timeout", current, message="연결이 지연되어 확인하지 못했습니다. 모드는 계속 사용할 수 있습니다.")
    except URLError as error:
        return UpdateResult("timeout" if isinstance(error.reason, TimeoutError) else "offline", current)
    except OSError:
        return UpdateResult("offline", current)
    except (ValueError, TypeError, KeyError):
        return UpdateResult("invalid", current)
