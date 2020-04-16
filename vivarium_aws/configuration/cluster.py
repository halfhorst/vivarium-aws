from configparser import ConfigParser
from tempfile import TemporaryFile

import boto3
from botocore.exceptions import ClientError
from loguru import logger


_post_install_script = """
#!/bin/bash

# Configuration for vivarium_cluster_tools
echo "export SGE_CLUSTER_NAME=aws-cluster" >> /home/ubuntu/.bashrc
echo "export HOSTNAME=aws-ec2-instance" >> /home/ubuntu/.bashrc

"""


def get_default_configuration(cluster_name: str) -> ConfigParser:
    """A factory for producing a ConfigParser object containing a baseline
    aws-parallelcluster configuration.
    """
    config = ConfigParser()

    config['aws'] = {}

    config['global'] = {
        'cluster_template': cluster_name,
        'update_check': 'true',
        'sanity_check': 'true'
    }

    config['aliases'] = {'ssh': 'ssh ubuntu@{MASTER_IP} {ARGS}'}

    config[f'cluster {cluster_name}'] = {
        'base_os': 'ubuntu1804',
        'initial_queue_size': 1,
        'max_queue_size': 50,
        'maintain_initial_size': 'true',
        'vpc_settings': cluster_name,
    }

    config['scaling'] = {'scaledown_idletime': 5}

    config[f'vpc {cluster_name}'] = {
        'use_public_ips': 'true'
    }

    return config


def make_configuration(cluster_name: str,
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
    """Generate an aws-parallelcluster ini configuration file.

    The configuration process has a few implications for cloud resources. A
    security group is created to enable UDP access on ports 60001-60020 for
    `mosh` access and a shell script is uploaded to the S3 bucket to be used
    as a post-install script on each cluster node.
    """

    configuration = get_default_configuration(cluster_name)

    configuration['aws']['aws_region_name'] = region

    configuration[f'cluster {cluster_name}']['custom_ami'] = ami_id
    configuration[f'cluster {cluster_name}']['key_name'] = ec2_keypair
    configuration[f'cluster {cluster_name}']['master_instance_type'] = master_instance
    configuration[f'cluster {cluster_name}']['compute_instance_type'] = compute_instance
    configuration[f'cluster {cluster_name}']['max_queue_size'] = max_queue_size
    configuration[f'cluster {cluster_name}']['s3_read_write_resource'] = f"arn:aws:s3:::{s3_bucket}*"

    # post_install_path = s3_bucket + "/vaws/post_install.sh"
    post_install_key = "vaws/post_install.sh"
    upload_to_s3(s3_bucket, post_install_key, _post_install_script)
    configuration[f'cluster {cluster_name}']['post_install'] = 's3://' + s3_bucket + '/' + post_install_key

    configuration[f'vpc {cluster_name}']['vpc_id'] = vpc_id
    configuration[f'vpc {cluster_name}']['master_subnet_id'] = master_subnet_id
    configuration[f'vpc {cluster_name}']['additional_sg'] = make_mosh_security_group(region, vpc_id)

    output_root = output_root / f"{cluster_name}_cluster_configuration"
    output_root.mkdir(exist_ok=True)

    f = open (output_root / f'{cluster_name}_cluster.ini', 'w')
    configuration.write(f)
    f.close()


def make_mosh_security_group(region: str, vpc_id: str) -> str:
    """Make an AWS security group that allows UDP access on ports 60001-60020
     and return its ID.

    UDP/60001~60100 is the protocol/port range that is used by mosh, a
    disconnect-resistent remote terminal application.
    """
    client = boto3.client('ec2', region_name=region)

    try:
        response = client.describe_security_groups(Filters=[
            {'Name': 'group-name', 'Values': ['vaws-mosh']}
        ])
    except ClientError as e:
        logger.error(e)
        raise

    if len(response['SecurityGroups']) > 0:
        return response['SecurityGroups'][0]['GroupId']

    ec2 = boto3.resource('ec2')
    vpc = ec2.Vpc(vpc_id)

    try:
        security_group = vpc.create_security_group(
            Description='Enable mosh connections over UDP',
            GroupName='vaws-mosh',
            VpcId=vpc_id,
            DryRun=False
        )
        response = security_group.authorize_ingress(
            CidrIp='0.0.0.0/0',
            FromPort=60001,
            ToPort=60020,
            IpProtocol='udp'
        )
    except ClientError as e:
        logger.error(e)
        raise

    return security_group.group_id


def upload_to_s3(bucket: str, key: str, contents: str):
    """Write a string `contents` to an S3 bucket under the name `key`."""

    s3_client = boto3.client('s3')
    with TemporaryFile() as f:
        f.write(bytes(contents, encoding='UTF-8'))
        f.seek(0)
        try:
            response = s3_client.upload_fileobj(f, bucket, key)
        except ClientError as e:
            logger.error(e)
            raise
