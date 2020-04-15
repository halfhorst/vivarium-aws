import shutil
import random

import boto3
from botocore.exceptions import ClientError
from loguru import logger


def ensure_system_command_exists(command: str):
    """Raise a RuntimeError if `command` is not executable on this system."""
    if shutil.which(command) is None:
        raise RuntimeError(f"The command `{command}` must be installed on your "
                          "machine. Please consult the vaws requirements.")


def ensure_aws_credentials_exist():
    """Raise a RuntimeError if AWS credentials and default region are not
    configured on this system.

    For more information, see the boto3 or aws cli documentation sections on
    credentials. There are several ways to specify credentials, the easies
    being a credentials file in `~/.aws`.
    """
    session = boto3.session.Session()
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError("No AWS credentials found. ")
    if session.region_name is None:
        raise RuntimeError("No default region set.")
    logger.info(f"AWS credentials found! ({credentials.method})")


def ensure_ami_exists(region: str, ami_id: str):
    """Raise a runtime error if the ami_id does not exist."""
    client = boto3.client('ec2', region_name=region)
    try:
        response = client.describe_images(Filters=[{'Name': 'image-id', 'Values': [ami_id]}])
    except ClientError as e:
        logger.error(e)
        raise

    if len(response['Images']) == 0:
        raise RuntimeError("AMI with id {ami_id} not found. Please check "
                           "your EC2 console and look for typos.")


def get_default_region() -> str:
    """Get the default region specified in the user's credentials."""
    session = boto3.session.Session()
    return session.region_name


def get_default_vpc(region: str) -> str:
    """Get the default VPC in the region else raise a RuntimeError if none
    exists.

    Default VPCs are created automatically. They would only fail to exist if
    the user specifically deleted theirs.
    """
    try:
        client = boto3.client('ec2', region_name=region)
    except ClientError as e:
        logger.error(e)
        raise

    response = client.describe_vpcs(Filters=[{'Name': 'isDefault', 'Values': ['true'],
                                              'Name': 'state', 'Values': ['available']}])

    if len(response['Vpcs']) == 0:
        raise RuntimeError("No available default VPC found. Please create one or specify "
                           "one at runtime.")

    # there can only be one default VPC by region
    return response['Vpcs'][0]['VpcId']


def get_default_subnet_id(region: str, vpc_id: str) -> str:
    """Get a subnet from the VPC else raise a RuntimeError if none exist.

    Irritatingly, EC2 instance availability varies by availability zone in
    a way that doesn't appear to be programmatically accessible. In fact, it is
    totally opaque as far as I can tell. So, there is no good way to pick an
    AZ and it may be the case that users encounter issues and need to manually
    adjust their subnet."""
    client = boto3.client('ec2', region_name=region)
    try:
        response = client.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id],
                                                 'Name': 'state', 'Values': ['available']}])
    except ClientError as e:
        logger.error(e)
        raise

    num_subnets = len(response['Subnets'])
    if num_subnets == 0:
        raise RuntimeError(f"No subnets exist for VPC {vpc_id}.")

    return response['Subnets'][0]['SubnetId']


def prompt_for_ec2_keypair(region: str) -> str:
    """Prompt the user with existing EC2 keypairs and return the selection.
    If none exist, raise a RuntimeError."""
    client = boto3.client('ec2', region_name=region)
    try:
        response = client.describe_key_pairs()
    except ClientError as e:
        logger.error(e)
        raise

    num_key_pairs = len(response['KeyPairs'])

    if num_key_pairs == 0:
        raise RuntimeError("An EC2 Keypair is required to setup a cluster. "
                           "Please create one.")

    selected_pair_idx = None
    key_names = [kp['KeyName'] for kp in response['KeyPairs']]
    while selected_pair_idx is None:
        prompt = "Please select an EC2 key pairs to use"
        for i, name in enumerate(key_names):
            prompt += f"\n\t{i + 1}. {name}"
        prompt += "\n>>> "
        try:
            selection = int(input(prompt)) - 1
            if selection in range(num_key_pairs):
                selected_pair_idx = selection
                break
        except ValueError:
            pass
        print(f"Please type a number between 1 and {num_key_pairs}.\n")

    return response['KeyPairs'][selected_pair_idx]['KeyName']
