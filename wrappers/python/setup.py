"""
ISO 4217 Currency Registry — Python package setup.

Distributes three things as a single installable package:

    iso4217.py       — the wrapper (Currency, CurrencyRegistry)
    iso4217_cli.py   — the command-line interface (installed as `iso4217`)
    iso4217.json     — the canonical registry data, shipped next to the module

Layout requirement: iso4217.json must sit next to iso4217.py in the source
tree. The wrapper resolves it via Path(__file__).parent / "iso4217.json" at
runtime, so the JSON has to end up in the same directory as the installed
module — not in a separate data directory. include_package_data=True plus a
MANIFEST.in entry is the mechanism that copies it into the wheel.
package_data is deliberately NOT used here: it only applies to directories
that are Python packages (with an __init__.py), and this distribution uses
flat py_modules. MANIFEST.in is the correct tool.

Entry points:
    iso4217  — the CLI. `iso4217 lookup USD`, `iso4217 list --pegged-to USD`,
               `iso4217 info`, and six other subcommands. See the CLI module
               docstring for the full surface.
"""

from pathlib import Path

from setuptools import setup



# ---------------------------------------------------------------------------
# Custom build_py — copy data files into the wheel
# ---------------------------------------------------------------------------
# setuptools does not ship non-Python files in a wheel for a py_modules
# distribution. MANIFEST.in affects the sdist, not the wheel. This override
# copies iso4217.json and schema.json next to the modules after the normal
# build_py step, so a pip install from a wheel resolves them at runtime.

from pathlib import Path as _Path
from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
    """Copy data files next to the modules in the wheel's build/lib."""

    DATA_FILES = ("iso4217.json", "schema.json")

    def run(self):
        super().run()
        src_dir = _Path(__file__).parent
        dest_dir = _Path(self.build_lib)
        for name in self.DATA_FILES:
            src = src_dir / name
            if not src.exists():
                # A missing data file is a hard error — the wheel would be
                # broken at runtime. Fail loudly.
                raise RuntimeError(
                    f"{name} not found at {src}; the wheel would be broken"
                )
            dest = dest_dir / name
            self.copy_file(str(src), str(dest))

HERE = Path(__file__).parent

# The Python package version. This is independent of the registry data
# version inside iso4217.json (meta.version). 1.1.0 is the release that
# adds the CLI; 1.0.0 shipped only the wrapper.
VERSION = "1.1.0"

README_PATH = HERE / "README.md"
LONG_DESCRIPTION = README_PATH.read_text(encoding="utf-8") if README_PATH.exists() else ""


setup(
    cmdclass={"build_py": build_py},
    # -- Identity ----------------------------------------------------------
    name="iso4217-registry",
    version=VERSION,
    description=(
        "Canonical ISO 4217 currency registry — machine-readable, versioned, "
        "language-agnostic, with a Python wrapper and a command-line interface."
    ),
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",

    # -- Author ------------------------------------------------------------
    author="Le P'tit",
    author_email="",  # optional; omitted rather than left as a placeholder
    url="https://github.com/slimissa/iso4217",
    project_urls={
        "Source": "https://github.com/slimissa/iso4217",
        "Tracker": "https://github.com/slimissa/iso4217/issues",
        "Registry": "https://github.com/slimissa/iso4217/blob/main/iso4217.json",
        "Changelog": "https://github.com/slimissa/iso4217/blob/main/CHANGELOG.md",
        "Tempus": "https://github.com/slimissa/Tempus",
        "LAS_Shell": "https://github.com/slimissa/Las_shell",
    },

    # -- Packages and modules ----------------------------------------------
    # Both files are flat modules at the top of the source tree, not a
    # package directory. py_modules is the correct declaration for that
    # layout, and it means the JSON must be shipped via MANIFEST.in rather
    # than package_data.
    py_modules=["iso4217", "iso4217_cli"],
    python_requires=">=3.8",

    # -- Dependencies ------------------------------------------------------
    # Zero runtime dependencies. The wrapper and the CLI use only stdlib.
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0,<9",
            "pytest-cov>=4.0,<6",
            "mypy>=1.0,<2",
            "jsonschema>=4.0,<5",
            "pyyaml>=6.0,<7",
        ],
    },

    # -- Data files --------------------------------------------------------
    # The JSON and the schema ship next to the module. See the module
    # docstring for why this is MANIFEST.in-driven, not package_data.
    include_package_data=True,
    zip_safe=False,  # the wrapper reads iso4217.json via Path(__file__); a zip
                     # import would break that resolution

    # -- Entry points ------------------------------------------------------
    # Single command. The previous setup.py declared
    # "iso4217-validate=iso4217:main_validate", but main_validate was never
    # written — the entry point was dead. This replaces it with a real one.
    entry_points={
        "console_scripts": [
            "iso4217=iso4217_cli:main",
        ],
    },

    # -- Classifiers -------------------------------------------------------
    classifiers=[
        # Development status
        "Development Status :: 5 - Production/Stable",

        # Intended audience
        "Intended Audience :: Developers",
        "Intended Audience :: Financial and Insurance Industry",
        "Intended Audience :: Science/Research",

        # License
        "License :: OSI Approved :: Apache Software License",

        # Operating systems
        "Operating System :: OS Independent",

        # Python versions
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",

        # Typing
        "Typing :: Typed",

        # Topics
        "Topic :: Office/Business :: Financial",
        "Topic :: Office/Business :: Financial :: Accounting",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Localization",
        "Topic :: Utilities",
    ],

    # -- Keywords ----------------------------------------------------------
    keywords=[
        "currency",
        "iso4217",
        "finance",
        "trading",
        "forex",
        "foreign-exchange",
        "cryptocurrency",
        "stablecoin",
        "central-bank",
        "monetary",
        "exchange-rate",
        "peg",
        "minor-units",
        "decimal-places",
        "data",
        "registry",
        "canonical",
        "machine-readable",
        "json",
        "cli",
        "command-line",
        "tempus",
        "quant",
        "quantitative-finance",
    ],

    # -- License -----------------------------------------------------------
    license="Apache-2.0",
)