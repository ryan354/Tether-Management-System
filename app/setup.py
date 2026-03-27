from setuptools import setup, find_packages

setup(
    name="motor-control-extension",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "fastapi-versioning>=1.0.0",
        "loguru>=0.7.0",
        "pydantic>=2.0.0",
        "appdirs>=1.4.0",
    ],
)
