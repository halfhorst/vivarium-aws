import subprocess
import os
import signal
from pathlib import Path

import click
from loguru import logger

from vivarium_aws.configuration import ami, cluster
from vivarium_aws import utilities


@click.group()
def vaws():
    """Tools for setting up and running vivarium simulations on Amazon Web
    Services (AWS).

    Start by configuring and making an AMI that contains simulation code and
    data. Then, using this AMI, configure and make an SGE cluster with which
    you can run simulations.
    """
    pass


@vaws.group('configure')
def configure():
    """Generate configuration files describing an Amazon Maching Image (AMI) or
    grid engine cluster on AWS.

    An AMI configuration depends on a Packer configuration file, gzipped source
    code, and any artifacts specified. A grid engine cluster is solely an
    aws-parallelcluster ini configuration file.
    """
    pass


@vaws.group('make')
def make():
    """Provision cloud resources from configuration files.

    Use `make` to create the AMI or cluster that was configured with
    `vaws configure`.
    """
    pass


# ########################
#
# Configure Commands
#
# ########################


@configure.command('ami')
@click.argument("ami_name", type=click.STRING)
@click.argument("code_root", type=click.Path(file_okay=False, exists=True))
@click.option("-o", "--output-path", type=click.Path(file_okay=False, exists=False),
              help="The output directory to place the AMI configuration folder in. The default "
                   "is the current directory.")
@click.option("-a", "--artifact-path", multiple=True, type=click.Path(dir_okay=False, exists=True),
              help="Specifies a different location to upload an artifact from. The name of the artifact "
                   "file must match the name of an artifact used in an existing model_specification or "
                   "the correct artifact will not be located for a simulation. This can be specified multiple "
                   "times. The default behavior pulls all artifact locations from the model specifications "
                   "found in code_root.")
@click.option("-r", "--region", type=click.STRING, help="The AWS region to construct the AMI in.")
def configure_ami(ami_name, code_root, output_path, artifact_path, region):
    """Generate a Packer configuration and accompanying data describing an
    Amazon Machine Image (AMI) named AMI_NAME that contains the Vivarium code
    and data necessary to run the model defined at CODE_ROOT.

    The accompanying data is the gzipped source code and a provisioning shell
    script. Access to the data artifacts is also required at the time the AMI is
    made.
    """
    utilities.ensure_aws_credentials_exist()

    code_root = Path(code_root).resolve()
    output_path = Path(output_path) if output_path else Path(".").resolve()
    region = utilities.get_default_region() if region is None else region
    ami.make_configuration(ami_name, code_root, output_path, artifact_path, region)


@configure.command('cluster')
@click.argument("cluster_name", type=click.STRING)
@click.argument("ami_id", type=click.STRING)
@click.argument("s3_bucket", type=click.STRING)
@click.option("-o", "--output-root", type=click.Path(file_okay=False, exists=False),
              help=("The output directory to place the cluster confgiration in. "
                    "Defaults to the current directory."))
@click.option("--region", default=None,
              help=("The region to run the cluster in. Note that there are instance "
                    "restrictions by region. Defaults to the default region specified "
                    "with your credentials."))
@click.option("--vpc-id", default=None, type=click.STRING,
              help=("The Virtual Private Cloud (VPC) in which to launch the cluster. "
                   "Defaults to the default VPC in the region."))
@click.option("--master-subnet-id", default=None, type=click.STRING,
              help=("The Virtual Private Cloud (VPC) subnet into which to launch the "
                    "master node. Defaults to an arbitrary subnet in your VPC. "
                    "Note that subnets are availability zone specific and instance "
                    "availability varies by availability zone."))
@click.option("--ec2-keypair", default=None, type=click.STRING,
              help=("The name of an EC2 keypair to enable SSH into the cluster. "
                    "prompted with the available keypairs in your region."))
@click.option("--master-instance", default="t2.large", type=click.STRING,
              help=("The desired instance type of the master node. Since Vivarium "
                    "simulations are single-threaded, the relevant parameter is RAM."))
@click.option("--compute-instance", default="t2.medium", type=click.STRING,
              help=("The desired instance type of the compute nodes. Since Vivarium "
                    "simulations are single-threaded, the relevant parameter is RAM. "
                    "It is unlikely more than 4GB will be needed to execute a "
                    "simulation."))
@click.option("--max-queue-size", default='10', type=click.STRING,
              help="The maximum number of concurrent compute instances. Consider "
                   "setting this equal to the total number of simulations your "
                   "branches file describes - Your compute hours are the same "
                   "no matter the degree of parallelism.")
def configure_cluster(cluster_name: str,
                      ami_id: str,
                      s3_bucket: str,
                      output_root: str,
                      region: str,
                      vpc_id: str,
                      master_subnet_id: str,
                      ec2_keypair: str,
                      master_instance: str,
                      compute_instance: int,
                      max_queue_size: str):
    """Generate an aws-parallelcluster configuration describing a cluster ready
    to run Vivarium simulations.

    CLUSTER_NAME will be used to identify resources associated with the cluster.
    AMI_ID should be an Amazon Machine Image (AMI) created using `vaws configure
    ami` and `vaws make ami` to ensure it is correctly configured for Vivarium.
    This machine is used to create each node in the cluster.

    S3_BUCKET is the name of an existing S3 bucket that will be made read/write
    accessible by the cluster in order to store results. It is also used to
    stash a bootstrapping script for the cluster.

    This configuration command is intended to provide the lowest possible
    barrier of entry forvsetting up a cluster to run Vivarium simulations on
    cloud resources. It sets sane defaults wherever possible but retains full
    customizability -- The output is a valid aws-parallelcluster configuration
    file that can be used with `pcluster` and can be modified at will if
    desired. Also, note that `pcluster` provides a convenient configuration
    command that can help setup a cluster configuration not specific to
    Vivarium, which could then be modified.
    """
    utilities.ensure_aws_credentials_exist()

    region = utilities.get_default_region() if region is None else region
    utilities.ensure_ami_exists(region, ami_id)
    vpc_id = utilities.get_default_vpc(region) if vpc_id is None else vpc_id
    master_subnet_id = utilities.get_default_subnet_id(region, vpc_id) if master_subnet_id is None else master_subnet_id
    ec2_keypair = utilities.prompt_for_ec2_keypair(region) if ec2_keypair is None else ec2_keypair

    output_root = Path(output_root) if output_root else Path(".").resolve()

    cluster.make_configuration(cluster_name, ami_id, s3_bucket, output_root,
                               region, vpc_id, master_subnet_id, ec2_keypair,
                               master_instance, compute_instance, max_queue_size)


# ########################
#
# Make Commands
#
# ########################


@make.command('ami')
@click.argument('ami_config', type=click.Path(dir_okay=False, exists=True))
def make_ami(ami_config: str):
    """Build an Amazon Machine Image (AMI) with Packer using the configuration
    file AMI_CONFIG.

    Access to the data artifacts specified at configuration time is required.
    This command provisions an EC2 instance and uses it to build a machine
    image. It is a very thin wrapper around `packer build`, you can use packer
    directly if you want more control.
    """
    utilities.ensure_aws_credentials_exist()
    utilities.ensure_system_command_exists('packer')

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


@make.command('cluster')
@click.argument('cluster_config', type=click.Path(dir_okay=False, exists=True))
@click.option('-n', '--cluster-name', type=click.STRING,
              help="The name of the clsuter. Defaults to the name parsed from "
                   "the configuration file.")
def make_cluster(cluster_config: str, cluster_name: str):
    """Startup an SGE cluster on AWS using the configuration CLUSTER_CONFIG.

    This command provisions several cloud resources culminating in an EC2
    instance that serves as the qmaster. You can then connect to the qmaster
    using `ssh` or `mosh` and run simulations using the `psimulate` group of
    commands.

    `make_cluster` is a very thin wrapper around `pcluster create` included
    for completeness. You can use `pcluster` to directly create your cluster,
    and you will administer yout cluster using it as well.
    """
    utilities.ensure_aws_credentials_exist()
    utilities.ensure_system_command_exists('pcluster')

    cluster_config = Path(cluster_config).resolve()

    if cluster_name is None:
        cluster_name = cluster_config.stem.split("_cluster")[0]

    try:
        proc = subprocess.Popen(['pcluster', 'create', '-c', cluster_config, cluster_name])
        ret = proc.wait()
    except KeyboardInterrupt:
        logger.info("Interrupting cluster building process.")
        ret = 0
        proc.send_signal(signal.SIGINT)
    if ret:
        logger.error(f"Failed to bootstrap the cluster. The process exited with {ret}.")
