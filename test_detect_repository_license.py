import io
import json
from email.message import Message
from unittest.mock import patch
import unittest
from urllib.error import HTTPError

from detect_repository_license import detect_repository_license


class Response:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def __enter__(self) -> io.BytesIO:
        return io.BytesIO(json.dumps(self.payload).encode("utf-8"))

    def __exit__(self, *args: object) -> None:
        return None


class DetectRepositoryLicenseTest(unittest.TestCase):
    @patch("detect_repository_license.urlopen")
    def test_detects_license_at_tested_commit(self, mock_urlopen: object) -> None:
        mock_urlopen.return_value = Response(  # type: ignore[attr-defined]
            {"sha": "license-blob", "license": {"spdx_id": "BSD-3-Clause"}}
        )
        result = detect_repository_license(
            "https://api.github.com", "PickNikRobotics/example", "abc123", "token"
        )
        self.assertEqual(result, "BSD-3-Clause")
        request = mock_urlopen.call_args.args[0]  # type: ignore[attr-defined]
        self.assertEqual(
            request.full_url,
            "https://api.github.com/repos/PickNikRobotics/example/license?ref=abc123",
        )
        self.assertEqual(request.get_header("Authorization"), "Bearer token")

    @patch("detect_repository_license.urlopen")
    def test_uses_default_detection_for_identical_license_blob(
        self, mock_urlopen: object
    ) -> None:
        mock_urlopen.side_effect = [  # type: ignore[attr-defined]
            Response({"sha": "same-blob", "license": {"spdx_id": "NOASSERTION"}}),
            Response({"sha": "same-blob", "license": {"spdx_id": "Apache-2.0"}}),
        ]
        result = detect_repository_license(
            "https://api.github.com", "PickNikRobotics/example", "abc123", "token"
        )
        self.assertEqual(result, "Apache-2.0")
        requests = mock_urlopen.call_args_list  # type: ignore[attr-defined]
        self.assertEqual(len(requests), 2)
        self.assertEqual(
            requests[1].args[0].full_url,
            "https://api.github.com/repos/PickNikRobotics/example/license",
        )

    @patch("detect_repository_license.urlopen")
    def test_rejects_unrecognized_changed_license_blob(
        self, mock_urlopen: object
    ) -> None:
        mock_urlopen.side_effect = [  # type: ignore[attr-defined]
            Response({"sha": "changed", "license": {"spdx_id": "NOASSERTION"}}),
            Response({"sha": "default", "license": {"spdx_id": "BSD-3-Clause"}}),
        ]
        with self.assertRaisesRegex(RuntimeError, "recognized root license"):
            detect_repository_license(
                "https://api.github.com", "PickNikRobotics/example", "abc123", "token"
            )

    @patch("detect_repository_license.urlopen")
    def test_rejects_default_branch_without_recognized_license(
        self, mock_urlopen: object
    ) -> None:
        mock_urlopen.side_effect = [  # type: ignore[attr-defined]
            Response({"sha": "same", "license": {"spdx_id": "NOASSERTION"}}),
            Response({"sha": "same", "license": {"spdx_id": "NOASSERTION"}}),
        ]
        with self.assertRaisesRegex(RuntimeError, "recognized root license"):
            detect_repository_license(
                "https://api.github.com", "PickNikRobotics/example", "abc123", "token"
            )

    @patch("detect_repository_license.urlopen")
    def test_rejects_missing_license(self, mock_urlopen: object) -> None:
        mock_urlopen.side_effect = HTTPError(  # type: ignore[attr-defined]
            "https://api.github.com/example", 404, "Not Found", Message(), None
        )
        with self.assertRaisesRegex(RuntimeError, "does not detect a root license"):
            detect_repository_license(
                "https://api.github.com", "PickNikRobotics/example", "abc123", "token"
            )


if __name__ == "__main__":
    unittest.main()
