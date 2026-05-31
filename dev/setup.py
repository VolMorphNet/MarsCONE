"""Setup configuration for MarsCONE package."""

from setuptools import find_packages, setup

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="marscone",
    version="0.1.0",
    author="Jakub Śledziowski, Bartosz Pieterek, Thomas Jones",
    author_email="jakub.sledziowski@usz.edu.pl",
    description="Morphometric analysis tool for cone-like landforms",
    long_description="MarsCONE is a command-line tool for automatic morphometric analysis of cone-like landforms (e.g. volcanic cones, impact-related features) using digital elevation models (DEMs)",
    long_description_content_type="text/markdown",
    url="https://github.com/VolMorphNet/MarsCONE",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: GIS",
    ],
    python_requires=">=3.8",
    install_requires=[
        "geopandas>=0.10",
        "pandas>=1.3",
        "numpy>=1.20",
        "shapely>=1.8",
        "rasterio>=1.3",
        "tqdm>=4.60",
        "scikit-image>=0.19",
        "scipy>=1.7",
        "osgeo>=3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.12",
            "black>=22.0",
            "isort>=5.10",
            "pylint>=2.10",
            "flake8>=4.0",
            "ruff>=0.1",
        ],
    },
    entry_points={
        "console_scripts": [
            "marscone-download-demo=download_demo_data:main",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
