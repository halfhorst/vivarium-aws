from configparser import ConfigParser

import boto3
import s3fs


def get_default_configuration(cluster_name: str) -> ConfigParser:
    """A factory for producing a ConfigParser object containing a baseline
    aws-parallelcluster configuration."""

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
        'initial_queue_size': 0,
        'max_queue_size': 10,
        'maintain_initial_size': 'false',
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
    """Generate an aws-parallelcluster configuration file for provisioning a
    grid engine cluster on AWS suitable for running Vivarium simulations.

    The cluster nodes are booted from the Amazon Machine Image (AMI) defined
    by ami_id.  If this immage was made with `vaws`, it contains everything
    necessary to run a simulation.
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
    # upload_to_s3(post_install_path, _post_install_script)
    # configuration[f'cluster {cluster_name}']['post_install'] = 's3://' + post_install_path

    configuration[f'vpc {cluster_name}']['vpc_id'] = vpc_id
    configuration[f'vpc {cluster_name}']['master_subnet_id'] = master_subnet_id
    configuration[f'vpc {cluster_name}']['additional_sg'] = make_mosh_security_group(region, vpc_id)

    output_root = output_root / f"{cluster_name}_cluster_configuration"
    output_root.mkdir(exist_ok=True)

    f = open (output_root / f'{cluster_name}_cluster.ini', 'w')
    configuration.write(f)
    f.close()


def make_mosh_security_group(region: str, vpc_id: str) -> str:
    """Make an AWS security group that allows UDP access on port 60001 and
    return its ID.

    UDP/60001 is the protocol/port that is used by mosh, a disconnect-resistent
    remote terminal application.
    """

    client = boto3.client('ec2', region_name=region)

    response = client.describe_security_groups(Filters=[
        {'Name': 'group-name', 'Values': ['vaws-mosh']}
    ])

    if len(response['SecurityGroups']) > 0:
        return response['SecurityGroups'][0]['GroupId']

    ec2 = boto3.resource('ec2')
    vpc = ec2.Vpc(vpc_id)

    security_group = vpc.create_security_group(
        Description='Enable mosh connections over UDP',
        GroupName='vaws-mosh',
        VpcId=vpc_id,
        DryRun=False
    )

    response = security_group.authorize_ingress(
        CidrIp='0.0.0.0/0',
        FromPort=60001,
        ToPort=60001,
        IpProtocol='udp'
    )

    return security_group.group_id


# # TODO: Move to boto3 for this
# def upload_to_s3(path: str, file_contents: str):
#     fs = s3fs.S3FileSystem()
#     bootstrap_file = fs.open(path, mode='w')
#     bootstrap_file.write(file_contents)
#     bootstrap_file.close()
