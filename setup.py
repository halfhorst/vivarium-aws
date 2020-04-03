from setuptools import setup, find_packages

setup(
    name='vivarium_aws',
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'click',
        'boto3',
        'loguru'
    ],

    entry_points="""
        [console_scripts]
        vaws=vivarium_aws.cli:vaws
    """,
)
