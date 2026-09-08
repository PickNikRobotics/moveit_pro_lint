from pathlib import Path
import tempfile
import unittest

from validate_package_licenses import validate_repository


class ValidatePackageLicensesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.repository = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_package(self, relative_path: str, license_element: str) -> Path:
        package_path = self.repository / relative_path / "package.xml"
        package_path.parent.mkdir(parents=True, exist_ok=True)
        package_path.write_text(
            "<?xml version=\"1.0\"?>\n"
            "<package format=\"3\">\n"
            "  <name>example</name>\n"
            "  <version>0.0.0</version>\n"
            f"  {license_element}\n"
            "</package>\n",
            encoding="utf-8",
        )
        return package_path

    def test_accepts_spdx_identifier(self) -> None:
        self.write_package("valid", "<license>BSD-3-Clause</license>")
        self.assertEqual(validate_repository(self.repository), [])

    def test_accepts_spdx_expression(self) -> None:
        self.write_package("expression", "<license>MIT OR Apache-2.0</license>")
        self.assertEqual(validate_repository(self.repository), [])

    def test_rejects_non_spdx_license(self) -> None:
        package_path = self.write_package("invalid", "<license>BSD</license>")
        self.assertEqual(
            validate_repository(self.repository),
            [f"{package_path}: license 'BSD' is not a valid SPDX expression"],
        )

    def test_rejects_license_that_does_not_match_root(self) -> None:
        package_path = self.write_package("mixed", "<license>BSD-3-Clause</license>")
        self.assertEqual(
            validate_repository(self.repository, "Apache-2.0"),
            [
                f"{package_path}: license 'BSD-3-Clause' does not match root license 'Apache-2.0'"
            ],
        )

    def test_allows_documented_license_mismatch(self) -> None:
        self.write_package("mixed", "<license>BSD-3-Clause</license>")
        (self.repository / ".moveit_pro_lint.json").write_text(
            '{"license_mismatch_exceptions": [{"path": "mixed/package.xml", '
            '"license": "BSD-3-Clause", "reason": "Third-party package"}]}\n',
            encoding="utf-8",
        )
        self.assertEqual(validate_repository(self.repository, "Apache-2.0"), [])

    def test_allows_multiple_documented_mismatches_for_one_package(self) -> None:
        self.write_package(
            "mixed",
            "<license>MIT</license>\n  <license>BSD-3-Clause</license>",
        )
        (self.repository / ".moveit_pro_lint.json").write_text(
            '{"license_mismatch_exceptions": ['
            '{"path": "mixed/package.xml", "license": "MIT", '
            '"reason": "First upstream license"}, '
            '{"path": "mixed/package.xml", "license": "BSD-3-Clause", '
            '"reason": "Second upstream license"}]}\n',
            encoding="utf-8",
        )
        self.assertEqual(validate_repository(self.repository, "Apache-2.0"), [])

    def test_rejects_stale_license_mismatch_exception(self) -> None:
        self.write_package("mixed", "<license>Apache-2.0</license>")
        config_path = self.repository / ".moveit_pro_lint.json"
        config_path.write_text(
            '{"license_mismatch_exceptions": [{"path": "mixed/package.xml", '
            '"license": "BSD-3-Clause", "reason": "Third-party package"}]}\n',
            encoding="utf-8",
        )
        self.assertEqual(
            validate_repository(self.repository, "Apache-2.0"),
            [
                f"{config_path}: unused license mismatch exception "
                "for mixed/package.xml and BSD-3-Clause"
            ],
        )

    def test_rejects_non_object_configuration(self) -> None:
        config_path = self.repository / ".moveit_pro_lint.json"
        config_path.write_text("[]\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "top level must be a JSON object"):
            validate_repository(self.repository)

    def test_allows_custom_license_with_existing_file(self) -> None:
        package_path = self.write_package(
            "custom", '<license file="models/LICENSE">SAM License</license>'
        )
        license_path = package_path.parent / "models" / "LICENSE"
        license_path.parent.mkdir()
        license_path.write_text("Custom license terms\n", encoding="utf-8")
        self.assertEqual(validate_repository(self.repository), [])

    def test_spdx_license_with_file_still_must_match_root(self) -> None:
        package_path = self.write_package(
            "spdx-file", '<license file="LICENSE">GPL-3.0-only</license>'
        )
        (package_path.parent / "LICENSE").write_text(
            "GNU General Public License\n", encoding="utf-8"
        )
        self.assertEqual(
            validate_repository(self.repository, "Apache-2.0"),
            [
                f"{package_path}: license 'GPL-3.0-only' does not match root license 'Apache-2.0'"
            ],
        )

    def test_rejects_empty_custom_license_name(self) -> None:
        package_path = self.write_package("empty", '<license file="LICENSE"></license>')
        (package_path.parent / "LICENSE").write_text(
            "Custom license terms\n", encoding="utf-8"
        )
        self.assertEqual(
            validate_repository(self.repository),
            [f"{package_path}: <license> value must not be empty"],
        )

    def test_rejects_missing_custom_license_file(self) -> None:
        package_path = self.write_package(
            "custom", '<license file="models/LICENSE">SAM License</license>'
        )
        self.assertEqual(
            validate_repository(self.repository),
            [
                f"{package_path}: license file 'models/LICENSE' does not exist "
                f"at {(package_path.parent / 'models' / 'LICENSE').resolve()}"
            ],
        )

    def test_rejects_custom_license_path_outside_package(self) -> None:
        package_path = self.write_package(
            "custom", '<license file="../LICENSE">Custom License</license>'
        )
        (self.repository / "LICENSE").write_text("Custom terms\n", encoding="utf-8")
        self.assertEqual(
            validate_repository(self.repository),
            [
                f"{package_path}: license file '../LICENSE' must stay within the package directory"
            ],
        )

    def test_rejects_missing_license_element(self) -> None:
        package_path = self.write_package("missing", "<description>No license</description>")
        self.assertEqual(
            validate_repository(self.repository),
            [f"{package_path}: package.xml has no <license> element"],
        )

    def test_reports_malformed_xml(self) -> None:
        package_path = self.repository / "broken" / "package.xml"
        package_path.parent.mkdir()
        package_path.write_text("<package>", encoding="utf-8")
        errors = validate_repository(self.repository)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith(f"{package_path}: invalid XML:"))


if __name__ == "__main__":
    unittest.main()
