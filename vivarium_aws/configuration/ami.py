import warnings
import json
import tarfile
import yaml
import shutil
import os.path
import tempfile
from pathlib import Path

import boto3


_general_purpose_instance_types = ["t2.nano", "t2.micro", "t2.small",
                                   "t2.medium", "t2.large", "t2.xlarge",
                                   "t2.2xlarge"]

_base_configuration = {
    "variables": {
        "aws_access_key": "",
        "aws_secret_key": "",
    },
    "builders": [],
    "provisioners": []
}

_ami_builder = {
    "type": "amazon-ebs",
    "access_key": "{{user `aws_access_key`}}",
    "secret_key": "{{user `aws_secret_key`}}",
    "region": None,
    "source_ami_filter": {
      "filters": {
        "virtualization-type": "hvm",
        #  aws-parallelcluster version must match setup.py
        "name": "aws-parallelcluster-2.6.1-ubuntu-1804-*",
        "root-device-type": "ebs"
      },
      "owners": ["amazon"],
      "most_recent": True
    },
    "instance_type": None,
    "ssh_username": "ubuntu",
    "ami_name": None
}

_docker_builder = {
    "type": "docker",
    "image": "ubuntu:18.04",
    "commit": True
}

_code_provisioner = {
    "type": "file",
    "source": "code.tar.gz",
    "destination": "/tmp/code.tar.gz"
}

_environment_provisioner = {
    "type": "shell",
    "script": "provision_environment.sh"
}

_environment_provisioner_script = """
#!/bin/bash -e -x

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y tar mosh

wget -q -O install_miniconda.sh https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
sudo chmod +x install_miniconda.sh
sudo -u ubuntu ./install_miniconda.sh -b -q

echo "export PATH=\$HOME/miniconda3/bin:\$PATH" >> $HOME/.bashrc

$HOME/miniconda3/bin/conda create -y --name simulation python=3.6
$HOME/miniconda3/condabin/conda install redis
$HOME/miniconda3/condabin/conda install hdf5

sudo mkdir -p /usr/local/share/vivarium/artifacts
sudo mv {tmp_artifact_locations} /usr/local/share/vivarium/artifacts || true

sudo tar -xvzf /tmp/code.tar.gz --directory $HOME
cd $HOME/simulation_code
sudo -u ubuntu $HOME/miniconda3/envs/simulation/bin/pip install -e .

"""

def make_configuration(ami_name: str, code_root: Path, output_root: Path,
                       artifact_paths: list, region: str):
    """Generate a Packer configuration file for provisioning an AMI that
    contains the data artifacts and simulation code defined in code_root.

    The configuration includes secondary files so the entire result is placed
    in a directory named after ami_name.

    The artifact file locations are scraped from the model specifications found
    in `code_root` unless paths are explicitly passed by `artifact_paths`.
    Provisioners are created to load each artifact into the image.

    The artifact paths in the model specification files are modified to
    point to the pre-determined location inside the image where artifacts are
    placed.
    """

    output_path = output_root / f"{ami_name}_ami_configuration"
    output_path.mkdir(exist_ok=True)

    #  This process overwrites configuration in the code root so we operate on a copy
    tempdir = tempfile.TemporaryDirectory()
    tempdir_path = Path(tempdir.name) / 'vaws_configuration'
    shutil.copytree(code_root, tempdir_path, ignore=shutil.ignore_patterns('*.hdf'))
    code_root = tempdir_path

    if not artifact_paths:
        artifact_paths = get_artifact_paths(code_root)
    else:
        artifact_paths = [Path(p) for p in artifact_paths]
    update_model_specification_artifact_paths(code_root)

    ami_size_estimate = get_ami_size_estimate_mib(artifact_paths)

    configuration = _base_configuration

    ami_builder = _ami_builder
    ami_builder['region'] = region
    ami_builder['instance_type'] = determine_correct_instance(ami_size_estimate)
    ami_builder['ami_name'] = f"{ami_name} {{{{timestamp}}}}"  # AMI names must be unique

    configuration['builders'].append(ami_builder)

    configuration['provisioners'].append(_code_provisioner)
    configuration['provisioners'].extend(make_artifact_provisioners(artifact_paths))
    configuration['provisioners'].append(_environment_provisioner)

    tar_vivarium_package(code_root, output_path)

    with open(output_path / f"provision_environment.sh", "w") as f:
        tmp_artifact_locations = ' '.join([f'/tmp/{art.name}' for art in artifact_paths])
        f.write(_environment_provisioner_script.format(tmp_artifact_locations=tmp_artifact_locations))

    with open(output_path / f"{ami_name}_ami.json", "w") as f:
        f.write(json.dumps(configuration, indent=2))

    tempdir.cleanup()


def make_artifact_provisioners(artifact_paths: list) -> list:
    """Construct a list of Packer provisioners that load artifacts into the
    image.
    """

    provisioners = []
    for path in artifact_paths:
        provisioners.append({
            "type": "file",
            "source": str(path),
            "destination": f"/tmp/{path.name}"
        })
    return provisioners


def get_artifact_paths(code_root: Path) -> list:
    """Parse a Vivarium package directory tree for model specifications and
    extract the artifact paths.
    """

    paths = []
    for config_path in code_root.glob("**/model_specifications/*.yaml"):
        with open(config_path, "r+") as f:
            config = yaml.load(f.read(), Loader=yaml.FullLoader)
            artifact_path = Path(config["configuration"]["input_data"]["artifact_path"])
            paths.append(artifact_path)
    return paths


def update_model_specification_artifact_paths(code_root: Path) -> list:
    """Parse a Vivarium package directory tree and upate the model specifications
    to point artifact paths to the correct location in the image.

    Until component ordering is inconsequential, e.g. we have dependency
    ordering, yaml manipulation must preserve order.
    """

    for config_path in code_root.glob("**/model_specifications/*.yaml"):
        with open(config_path, "r+") as f:
            config = f.read().split(sep='\n')
            for i, line in enumerate(config):
                if line.strip().startswith('artifact_path'):
                    key, path = line.split(":")
                    artifact_path = Path(path)
                    config[i] = ': '.join([key, f"/usr/local/share/vivarium/artifacts/{artifact_path.name}"])
            f.seek(0)
            f.write('\n'.join(config))


def get_ami_size_estimate_mib(artifacts: list) -> int:
    """Return the size in MB of the artifacts in the list"""

    if len(artifacts) == 0:
        return 0
    size = 0
    for artifact in artifacts:
        size += os.path.getsize(artifact)  # in bytes
    return size / 1.e6


def determine_correct_instance(ami_size_estimate_mb: int) -> str:
    """Determine the smallest instance type that can safely hold the estiamted
    artifact data size, with affordance for overhead.
    """

    ami_size_estimate_mb += 4096  # overhead for the aws-parallelcluster base AMI

    client = boto3.client('ec2')
    instance_options = client.describe_instance_types(InstanceTypes=_general_purpose_instance_types)["InstanceTypes"]
    correct_instance = None

    for instance in sorted(instance_options, key=lambda instance: instance['MemoryInfo']['SizeInMiB']):
        if instance['MemoryInfo']['SizeInMiB'] > ami_size_estimate_mb:
            correct_instance = instance['InstanceType']
            break
    if correct_instance is None:
        warnings.warn(f"vaws only supports building AMIs on relatively inexpensive, general-purpose t2 instances. "
                      "The image y  ou are trying to pack is {ami_size_estimate_mb}mb, most likely due to artifacts, "
                      "and this is larger than the largest general-purpose t2 instance available. Please review ec2 "
                      "instance options and manually select and insert one into the machine configuration file.")
    return correct_instance



def tar_exclude_hdf(fname: str) -> bool:
    """An hdf file exclusion function for use with tarball.add().
    """

    if fname.endswith('.hdf') or fname.endswith('.h5'):
        return True
    if '.git' in fname:
        return True
    return False


def tar_vivarium_package(source: Path, target: Path) -> str:
    """Create a tarball at `target` containing the Vivarium package located at
    `source`, excluding its artifact data.
    """

    tar_path = target / "code.tar.gz"
    with tarfile.open(tar_path, 'w:gz') as tarball:
        tarball.add(str(source), arcname="simulation_code", exclude=tar_exclude_hdf)
    return tar_path
