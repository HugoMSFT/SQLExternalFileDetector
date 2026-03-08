from setuptools import setup, find_packages

setup(
    name="external-file-detection",
    version="1.0.0",
    description="External File Detector for SQL - detects file types and generates SQL DDL",
    author="HugoMSFT",
    packages=find_packages(),
    install_requires=[
        "pandas>=1.5.0",
        "pyarrow>=10.0.0",
        "click>=8.1.0",
        "flask>=2.3.0",
        "chardet>=4.0.0",
        "openpyxl>=3.0.0",
    ],
    extras_require={
        "s3": ["boto3>=1.26.0"],
        "azure": [
            "azure-storage-blob>=12.14.0",
            "azure-identity>=1.12.0",
        ],
        "spark": [
            "delta-spark>=2.2.0",
            "pyspark>=3.3.0",
        ],
        "all": [
            "boto3>=1.26.0",
            "azure-storage-blob>=12.14.0",
            "azure-identity>=1.12.0",
            "delta-spark>=2.2.0",
            "pyspark>=3.3.0",
            "deltalake>=0.10.0",
        ],
    },
    include_package_data=True,
    package_data={
        "external_file_detection": ["templates/*.html", "static/*.css", "static/*.js"],
    },
    entry_points={
        "console_scripts": [
            "external-file-detector=external_file_detection.cli:main",
        ],
    },
    python_requires=">=3.8",
)