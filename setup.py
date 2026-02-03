#!/usr/bin/env python3
"""Moltbunker Python SDK - Permissionless P2P Container Runtime for AI Agents"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="moltbunker",
    version="0.1.0",
    author="Moltbunker Team",
    author_email="team@moltbunker.com",
    description="Python SDK for Moltbunker - Permissionless P2P Container Runtime for AI Agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/moltbunker/moltbunker-sdk",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: System :: Distributed Computing",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.8",
    install_requires=[
        "httpx>=0.24.0",
        "pydantic>=2.0.0",
    ],
    extras_require={
        # Wallet authentication for AI agents
        "wallet": [
            "web3>=6.0.0",
            "eth-account>=0.9.0",
        ],
        # SKILL.md parsing
        "skill": [
            "PyYAML>=6.0",
        ],
        # Full installation with all features
        "full": [
            "web3>=6.0.0",
            "eth-account>=0.9.0",
            "PyYAML>=6.0",
        ],
        # Development dependencies
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
            "web3>=6.0.0",
            "eth-account>=0.9.0",
            "PyYAML>=6.0",
        ],
    },
)
