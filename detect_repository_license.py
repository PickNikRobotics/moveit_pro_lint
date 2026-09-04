#!/usr/bin/env python3

import json
import os
import sys
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


def query_repository_license(
    api_url: str,
    repository: str,
    token: str,
    ref: Optional[str] = None,
) -> dict:
    url = f"{api_url.rstrip('/')}/repos/{quote(repository, safe='/')}/license"
    if ref is not None:
        url += f"?ref={quote(ref, safe='')}"
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    location = f" at {ref}" if ref is not None else " on its default branch"
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            raise RuntimeError(
                f"GitHub does not detect a root license for {repository}{location}"
            ) from error
        raise RuntimeError(
            f"GitHub license API returned HTTP {error.code} for {repository}{location}"
        ) from error
    except (URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Unable to query the GitHub license API for {repository}{location}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"GitHub license API returned an invalid response for {repository}{location}"
        )
    return payload


def detected_spdx(payload: dict) -> Optional[str]:
    license_info = payload.get("license")
    spdx_id = license_info.get("spdx_id") if isinstance(license_info, dict) else None
    if not isinstance(spdx_id, str) or not spdx_id or spdx_id == "NOASSERTION":
        return None
    return spdx_id


def detect_repository_license(
    api_url: str, repository: str, ref: str, token: str
) -> str:
    ref_payload = query_repository_license(api_url, repository, token, ref)
    ref_spdx = detected_spdx(ref_payload)
    if ref_spdx is not None:
        return ref_spdx

    # GitHub's Licensee integration can return NOASSERTION on a non-default ref
    # even when that ref contains the exact root-license blob detected on the
    # default branch. Reuse default-branch metadata only after proving that the
    # API returned the same immutable blob for both refs.
    default_payload = query_repository_license(api_url, repository, token)
    default_spdx = detected_spdx(default_payload)
    ref_sha = ref_payload.get("sha")
    default_sha = default_payload.get("sha")
    if (
        default_spdx is not None
        and isinstance(ref_sha, str)
        and ref_sha
        and ref_sha == default_sha
    ):
        return default_spdx

    raise RuntimeError(
        f"GitHub does not detect a recognized root license for {repository} at {ref}"
    )


def main() -> int:
    required = ("GITHUB_API_URL", "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_TOKEN")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2

    try:
        spdx_id = detect_repository_license(
            os.environ["GITHUB_API_URL"],
            os.environ["GITHUB_REPOSITORY"],
            os.environ["GITHUB_SHA"],
            os.environ["GITHUB_TOKEN"],
        )
    except (json.JSONDecodeError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    print(spdx_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
