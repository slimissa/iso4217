"""
ISO 4217 Currency Registry — Python Package Setup

A canonical, versioned, machine-readable registry of ISO 4217 currency codes
with a zero-dependency Python wrapper. Provides Currency and CurrencyRegistry
classes with full type hints, minor/major unit conversion, peg information
access, and country relationship lookup.
"""

from pathlib import Path
from setuptools import setup, find_packages

# ---------------------------------------------------------------------------
# Read the README
# ---------------------------------------------------------------------------

readme_path = Path(__file__).parent / "README.md"
long_description = ""
if readme_path.exists():
    long_description = readme_path.read_text(encoding="utf-8")

# ---------------------------------------------------------------------------
# Package metadata
# ---------------------------------------------------------------------------

setup(
    # -- Identity -----------------------------------------------------------
    name="iso4217-registry",
    version="1.0.0",
    description="Canonical ISO 4217 currency registry — machine-readable, versioned, language-agnostic",
    long_description=long_description,
    long_description_content_type="text/markdown",

    # -- Author -------------------------------------------------------------
    author="Le P’tit",
    url="https://github.com/slimissa/iso4217",
    project_urls={
        "Source": "https://github.com/slimissa/iso4217",
        "Tracker": "https://github.com/slimissa/iso4217/issues",
        "Registry": "https://github.com/slimissa/iso4217/blob/main/iso4217.json",
        "Tempus": "https://github.com/slimissa/Tempus",
    },

    # -- Package ------------------------------------------------------------
    packages=find_packages(where="."),
    package_dir={"": "."},
    py_modules=["iso4217"],
    python_requires=">=3.8",

    # -- Dependencies -------------------------------------------------------
    install_requires=[],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "mypy>=1.0",
            "jsonschema>=4.0",
        ],
    },

    # -- Package data -------------------------------------------------------
    include_package_data=True,
    package_data={
        "": ["iso4217.json", "schema.json"],
    },
    data_files=[
        ("", ["iso4217.json"]),
    ],

    # -- Entry points -------------------------------------------------------
    entry_points={
        "console_scripts": [
            "iso4217-validate=iso4217:main_validate",
        ],
    },

    # -- Classifiers --------------------------------------------------------
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

        # Topics
        "Topic :: Office/Business :: Financial",
        "Topic :: Office/Business :: Financial :: Accounting",
        "Topic :: Office/Business :: Financial :: Investment",
        "Topic :: Scientific/Engineering :: Information Analysis",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Localization",

        # Typing
        "Typing :: Typed",
    ],

    # -- Keywords -----------------------------------------------------------
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
        "tempus",
        "quant",
        "quantitative-finance",
    ],

    # -- License ------------------------------------------------------------
    license="Apache-2.0",
)