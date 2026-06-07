from setuptools import setup, find_packages

# Single-source version from package __init__.py
import re
_version_re = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')
with open("forkmark/__init__.py") as f:
    for line in f:
        m = _version_re.match(line)
        if m:
            version = m.group(1)
            break
    else:
        raise RuntimeError("Unable to find __version__ in forkmark/__init__.py")

setup(
    name="forkmark",
    version=version,
    description="The QA layer for AI workflows — eval-first A/B comparison for LLM pipelines",
    long_description=open("../README.md").read() if __import__("os").path.exists("../README.md") else "",
    long_description_content_type="text/markdown",
    author="Forkmark",
    author_email="eng@forkmark.dev",
    url="https://github.com/forkmark/forkmark",
    project_urls={
        "Documentation": "https://docs.forkmark.dev",
        "Changelog": "https://github.com/forkmark/forkmark/blob/main/CHANGELOG.md",
        "Issues": "https://github.com/forkmark/forkmark/issues",
    },
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=["httpx>=0.27.0"],
    entry_points={
        "console_scripts": [
            "forkmark=forkmark.cli:main",
        ],
    },
    extras_require={
        "openai":    ["openai>=1.0.0"],
        "anthropic": ["anthropic>=0.28.0"],
        "langchain": ["langchain>=0.2.0"],
        "all":       ["openai>=1.0.0", "anthropic>=0.28.0", "langchain>=0.2.0"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: MIT License",
    ],
    keywords="llm eval comparison dpo preference ai workflow",
)
