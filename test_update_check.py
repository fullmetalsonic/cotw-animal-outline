import json
import socket
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from app_version import VERSION
import update_check as updates


def release(tag="v0.1.0", **changes):
    result = {"id": 1, "tag_name": tag, "draft": False, "prerelease": False,
              "published_at": "2026-10-29T00:00:00Z",
              "html_url": "https://github.com/fullmetalsonic/cotw-animal-outline/releases/tag/" + tag}
    result.update(changes)
    return result


class VersionTests(unittest.TestCase):
    def test_same_and_build_metadata(self):
        self.assertEqual(updates.compare_versions("v1.2.3+one", "1.2.3+two"), 0)

    def test_numeric_precedence(self):
        self.assertGreater(updates.compare_versions("1.10.0", "1.9.9"), 0)
        self.assertLess(updates.compare_versions("0.9.9", "1.0.0"), 0)

    def test_prerelease_precedence(self):
        ordered = ["1.0.0-alpha", "1.0.0-alpha.1", "1.0.0-alpha.beta", "1.0.0-beta",
                   "1.0.0-beta.2", "1.0.0-beta.11", "1.0.0-rc.1", "1.0.0"]
        for left, right in zip(ordered, ordered[1:]):
            with self.subTest(left=left):
                self.assertLess(updates.compare_versions(left, right), 0)

    def test_invalid_versions(self):
        for value in (None, "", "abc1234", "1.2", "01.2.3", "1.2.3-01", "1.2.3-", "1.2.3+", "1.2.3\n"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                updates.parse_semver(value)


class ReleaseTests(unittest.TestCase):
    def check(self, data):
        return updates.check_update(lambda: data, current="0.1.0")

    def test_same(self):
        result = self.check(release("v0.1.0"))
        self.assertEqual(result.status, "up_to_date")
        self.assertFalse(result.update_needed)

    def test_newer_and_older(self):
        self.assertTrue(self.check(release("v0.2.0")).update_needed)
        self.assertFalse(self.check(release("v0.0.9")).update_needed)

    def test_metadata_is_not_an_update(self):
        self.assertFalse(self.check(release("v0.1.0+build.2")).update_needed)

    def test_excludes_draft_and_prerelease(self):
        for data in (release("v9.0.0", draft=True), release("v9.0.0", prerelease=True), release("v9.0.0-rc.1")):
            with self.subTest(data=data):
                result = self.check(data)
                self.assertEqual(result.status, "not_stable")
                self.assertIsNone(result.release_url)
                self.assertIsNone(result.update_needed)

    def test_no_commit_or_malformed_metadata(self):
        for data in ({"sha": "abc1234"}, release("abc1234"), release(id=0), release(id=True),
                     release(published_at=None), release(html_url="https://example.com/"), []):
            with self.subTest(data=data):
                self.assertIn(self.check(data).status, ("invalid", "not_stable"))
                self.assertIsNone(self.check(data).update_needed)

    def test_release_url_allowlist(self):
        base = "https://github.com/fullmetalsonic/cotw-animal-outline/releases/tag/"
        self.assertTrue(updates.is_release_url(base + "v0.2.0", "v0.2.0"))
        for url in (base + "v0.2.0?next=evil", base + "v0.2.0#x", base + "v0.2.0/extra",
                    base + "%2f..%2fother", base + "v0.2.0-rc.1", base.replace("https:", "http:") + "v0.2.0",
                    base.replace("github.com", "github.com.evil") + "v0.2.0",
                    base.replace("fullmetalsonic", "other") + "v0.2.0", "javascript:alert(1)"):
            with self.subTest(url=url):
                self.assertFalse(updates.is_release_url(url))
        self.assertFalse(updates.is_release_url(base + "v0.2.0", "v0.3.0"))

    def test_network_failures_are_results(self):
        cases = [(socket.timeout(), "timeout"), (URLError("offline"), "offline"),
                 (URLError(socket.timeout()), "timeout"), (OSError("offline"), "offline")]
        for code, expected in ((404, "unavailable"), (403, "rate_limited"), (429, "rate_limited"), (500, "unavailable")):
            cases.append((HTTPError(updates.API_URL, code, "error", {}, None), expected))
        for error, expected in cases:
            with self.subTest(error=error):
                result = updates.check_update(Mock(side_effect=error))
                self.assertEqual(result.status, expected)
                self.assertIsNone(result.update_needed)
                self.assertIsNone(result.release_url)

    def test_fetch_uses_only_fixed_endpoint_without_token(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.geturl.return_value = updates.API_URL
        response.read.return_value = json.dumps(release()).encode()
        opener = Mock()
        opener.open.return_value = response
        with patch.object(updates, "build_opener", return_value=opener):
            self.assertEqual(updates.check_update().status, "up_to_date")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, updates.API_URL)
        self.assertNotIn("authorization", {key.lower() for key in request.headers})
        self.assertEqual(opener.open.call_args.kwargs["timeout"], updates.TIMEOUT_SECONDS)
        self.assertIsNone(updates._NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com/"))

    def test_fetch_rejects_redirected_response_and_oversize(self):
        for url, data in (("https://example.com/", b"{}"), (updates.API_URL, b"x" * (updates.MAX_RESPONSE_BYTES + 1)),
                          (updates.API_URL, b"not json")):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.geturl.return_value = url
            response.read.return_value = data
            opener = Mock()
            opener.open.return_value = response
            with self.subTest(url=url), patch.object(updates, "build_opener", return_value=opener):
                self.assertEqual(updates.check_update().status, "invalid")


if __name__ == "__main__":
    unittest.main()
