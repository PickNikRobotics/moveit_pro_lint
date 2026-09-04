# MoveIt Pro lint action

This composite GitHub Action validates MoveIt Pro Objective XML and ROS package license declarations.

## Usage

```yaml
- uses: PickNikRobotics/moveit_pro_lint@main
```

The license check recursively scans `package.xml` files. Every `<license>` value must be a valid SPDX expression and match the root license detected by GitHub for the exact commit under test. When GitHub reports `NOASSERTION` only for a non-default ref, the action reuses the default branch's detected SPDX identifier solely if both API responses name the same immutable root-license blob.

The action requires Python 3.9 or newer, `pip`, outbound access to PyPI for hash-pinned dependencies, and the standard GitHub Actions environment and token. It does not require the GitHub CLI or Python's `venv` module.

A custom non-SPDX license is allowed only when the element has a `file` attribute and that file exists within the package directory, for example:

```xml
<license file="models/LICENSE">SAM License</license>
```

A package with intentionally different licensing can declare a narrow exception in `.moveit_pro_lint.json`:

```json
{
  "license_mismatch_exceptions": [
    {
      "path": "abb_irb1200_5_90_moveit_config/package.xml",
      "license": "BSD-3-Clause",
      "reason": "ROS-Industrial configuration preserved under its upstream license"
    }
  ]
}
```

Each exception must match the package path and license exactly, include a reason, and remain necessary. Repeat the path with a different license when one package has multiple intentional mismatches. Duplicate and stale exceptions fail validation.

The action installs hash-pinned Python dependencies into an isolated runner-temporary directory before running either validator.
