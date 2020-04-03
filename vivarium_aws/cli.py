import subprocess
import os
import signal
from pathlib import Path

import click
from loguru import logger

from vivarium_aws.configuration import ami
from vivarium_aws.utilities import ensure_command_exists


@click.group()
def vaws():
    """A toolbox for running Vivarium simulations on AWS."""
    pass


@vaws.group('configure')
def configure():
    """Generate configuration files necessary to provision a grid engine cluster
    on AWS. 
    
    The required components are a Packer configuration for building an Amazon
    Machine Image (AMI) and an aws-parallelcluster configuration for
    bootstrapping a grid engine cluster using that AMI.
    """
    pass

@vaws.group('make')
def make():
    pass


@configure.command('ami')
@click.argument("ami_name", type=click.STRING)
@click.argument("code_root", type=click.Path(file_okay=False, exists=True))
@click.option("-o", "--output-path", type=click.Path(file_okay=False, exists=False),
              help="The output directory to place the AMI configuration in. The default "
              "is the current directory.")
@click.option("-a", "--artifact-path", multiple=True, type=click.Path(dir_okay=False, exists=True),
              help="Specifies an artifact file to upload. This can be passed multiple times. The "
                   "default behavior pulls all artifacts from the model specifications found in "
                   "the root code directory.")
@click.option("-r", "--region", type=click.STRING, help="The AWS region to construct the AMI in.")
def configure_ami(ami_name, code_root, output_path, artifact_path, region):
    """Generate the Packer configuration for an Amazon Machine Image (AMI) named
    AMI_NAME that contains the Vivarium code and data necessary to run the model
    defined at CODE_ROOT.
    """

    code_root = Path(code_root).resolve()
    output_path = Path(output_path) if output_path else Path(".").resolve()
    ami.make_configuration(ami_name, code_root, output_path, artifact_path, region)


@make.command('ami')
@click.argument('ami_config', type=click.Path(dir_okay=False, exists=True))
def make_ami(ami_config: str):
    """Build an Amazon Machine Image (AMI) using Packer from the configuration
    `ami_config`.
    
    This command provisions an EC2 instance in AWS uses it to build a machine
    image. It is a very thin wrapper around packer build. You can use packer
    yourself if you want more control.
    """
    ensure_command_exists('packer')
    
    ami_config = Path(ami_config).resolve()
    os.chdir(ami_config.parent)
    try:    
        proc = subprocess.Popen(['packer', 'build', str(ami_config.name)])
        ret = proc.wait()
    except KeyboardInterrupt:
        logger.info("Interrupting the packer process.")
        ret = 0
        proc.send_signal(signal.SIGINT)

    if ret:
        logger.error(f"Failed to build AMI. The packer process exited with {ret}.")
