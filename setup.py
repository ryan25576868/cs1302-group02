from pathlib import Path

from setuptools import find_packages, setup


setup(
    name="function-pov",
    version="0.1.0",
    description="Static Python function analysis and call graph data",
    long_description=Path("README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    license="MIT",
    packages=find_packages("src"),
    package_dir={"": "src"},
    package_data={"function_pov": ["web/*.html", "web/static/*.css", "web/static/*.js"]},
    extras_require={"test": ["playwright>=1.40"]},
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "console_scripts": [
            "function-pov=function_pov.cli:main",
        ],
    },
)
