#!/usr/bin/env python3

import argparse
import json
from pathlib import Path
import sys
from typing import Optional
import xml.etree.ElementTree as ET

from license_expression import get_spdx_licensing


SPDX_LICENSING = get_spdx_licensing()
CONFIG_FILENAME = ".moveit_pro_lint.json"


def normalized_spdx(expression: str) -> Optional[str]:
    validation = SPDX_LICENSING.validate(expression)
    return None if validation.errors else validation.normalized_expression


def load_mismatch_exceptions(repository: Path) -> dict[str, set[str]]:
    config_path = repository / CONFIG_FILENAME
    if not config_path.is_file():
        return {}

    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{config_path}: top level must be a JSON object")
    configured_exceptions = config.get("license_mismatch_exceptions", [])
    if not isinstance(configured_exceptions, list):
        raise ValueError(
            f"{config_path}: license_mismatch_exceptions must be a JSON array"
        )

    exceptions: dict[str, set[str]] = {}
    for exception in configured_exceptions:
        if not isinstance(exception, dict):
            raise ValueError(
                f"{config_path}: each license mismatch exception must be a JSON object"
            )
        path = exception.get("path")
        license_name = exception.get("license")
        reason = exception.get("reason")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(license_name, str)
            or not license_name
            or not isinstance(reason, str)
            or not reason
        ):
            raise ValueError(
                f"{config_path}: each license mismatch exception needs a path, license, and reason"
            )
        path_exceptions = exceptions.setdefault(path, set())
        if license_name in path_exceptions:
            raise ValueError(
                f"{config_path}: duplicate exception for {path} and {license_name}"
            )
        path_exceptions.add(license_name)
    return exceptions


def validate_package(
    package_path: Path,
    repository: Path,
    root_license: Optional[str],
    mismatch_exceptions: dict[str, set[str]],
) -> tuple[list[str], set[tuple[str, str]]]:
    try:
        package = ET.parse(package_path).getroot()
    except ET.ParseError as error:
        return [f"{package_path}: invalid XML: {error}"], set()

    licenses = package.findall("license")
    if not licenses:
        return [f"{package_path}: package.xml has no <license> element"], set()

    relative_path = package_path.relative_to(repository).as_posix()
    expected_exceptions = mismatch_exceptions.get(relative_path, set())
    used_exceptions: set[tuple[str, str]] = set()
    errors: list[str] = []
    for license_element in licenses:
        license_name = (license_element.text or "").strip()
        if not license_name:
            errors.append(f"{package_path}: <license> value must not be empty")
            continue

        normalized_license = normalized_spdx(license_name)
        license_file = license_element.get("file")
        if license_file is not None:
            license_path = (package_path.parent / license_file).resolve()
            package_directory = package_path.parent.resolve()
            if not license_file or not license_path.is_relative_to(package_directory):
                errors.append(
                    f"{package_path}: license file '{license_file}' must stay within the package directory"
                )
                continue
            if not license_path.is_file():
                errors.append(
                    f"{package_path}: license file '{license_file}' does not exist at {license_path}"
                )
                continue
            if normalized_license is None:
                # REP-149 permits custom non-SPDX licenses when the complete
                # terms are supplied by a package-local file.
                continue

        if normalized_license is None:
            errors.append(
                f"{package_path}: license '{license_name}' is not a valid SPDX expression"
            )
            continue

        if root_license is None or normalized_license == root_license:
            continue
        if license_name in expected_exceptions:
            used_exceptions.add((relative_path, license_name))
            continue
        errors.append(
            f"{package_path}: license '{license_name}' does not match root license '{root_license}'"
        )

    return errors, used_exceptions


def validate_repository(
    repository: Path, root_license: Optional[str] = None
) -> list[str]:
    repository = repository.resolve()
    mismatch_exceptions = load_mismatch_exceptions(repository)
    if root_license is not None:
        normalized_root_license = normalized_spdx(root_license)
        if normalized_root_license is None:
            return [f"root license '{root_license}' is not a valid SPDX expression"]
        root_license = normalized_root_license

    errors: list[str] = []
    used_exceptions: set[tuple[str, str]] = set()
    for package_path in sorted(repository.rglob("package.xml")):
        package_errors, package_used_exceptions = validate_package(
            package_path, repository, root_license, mismatch_exceptions
        )
        errors.extend(package_errors)
        used_exceptions.update(package_used_exceptions)

    configured_exceptions = {
        (path, license_name)
        for path, licenses in mismatch_exceptions.items()
        for license_name in licenses
    }
    for path, license_name in sorted(configured_exceptions - used_exceptions):
        errors.append(
            f"{repository / CONFIG_FILENAME}: unused license mismatch exception "
            f"for {path} and {license_name}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate SPDX license declarations in ROS package.xml files."
    )
    parser.add_argument(
        "repository",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="repository to scan (default: current directory)",
    )
    parser.add_argument(
        "--root-license",
        help="SPDX expression detected for the repository's root license",
    )
    args = parser.parse_args()

    package_count = sum(1 for _ in args.repository.rglob("package.xml"))
    try:
        errors = validate_repository(args.repository, args.root_license)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        errors = [str(error)]
    for error in errors:
        print(f"Error: {error}", file=sys.stderr)
    print(f"Validated license declarations in {package_count} package.xml files.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
