from setuptools import setup, find_packages

setup(
    name='vivarium_aws',
    version="0.1",
    packages=find_packages(),
    install_requires=[
        'click',
        'boto3',
        'loguru',
        'aws-parallelcluster==2.6.0',  # AMI Filtering relies on this version, see _ami_builder
    ],

    entry_points="""
        [console_scripts]
        vaws=vivarium_aws.cli:vaws
    """,
)
