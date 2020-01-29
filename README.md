# vivarium-aws

Tools for running vivarium simulations on Amazon Web Services (AWS)>

# Overview

This library helps with configuring an SGE (son of grid engine) cluster on AWS specifically intended to run Vivarium simulations, as well as running the simulations themselves and managing the results. The steps required to get up and running are broadly as follows:

1. Setting up credentials and configuring an IAM role with the permissions it needs to manage the resources used running the cluster.
3. Setting up an S3 bucket to hold your simulation data and results.
2. Copying the model's Vivarium data artifact to the S3 bucket.
3. Copying the cluster's bootstrap script to the S3 bucket
3. Initiating the cluster from a configuration file using Amazon's tooling.

At this point, simulations can be run. This library additionally provides tools for starting simulations, monitoring their progress, and manipulating and exploring results stored in S3. Keep in mind that the command line tools provided here all have `--help` flags, and your cluster and AWS services can also be manipulated through `pcluster` (aws-parallelcluster) and `aws <service-name>` (aws-cli).

# Credentials

Initial bootstrapping consists of: 

1. Making an IAM role
2. Configuring your local machine with the role's access key id and secret
3. Giving that role permission over the services the cluster needs
4. Setting up SSH keys specifically for connecting to ec2

## IAM Roles

Current best practice is to create an IAM user that will be responsible for running Vivarium simulations, and give that role permissions for s3, ec2 and cloudformation only. This means not creating root credentials for the owner of the AWS account and handing those out to everything, including vivarium-aws.

## S3

s3fs uses boto3's credential methods for authentication, which is widely applicable to the AWS ecosystem. The two easiest methods are either environment variables or a global config. The environment variables should be `aws_access_key_id` and `aws_secret_access_key`. The config file follows .ini conventions and should be placed in ~/.aws/credentials. For example:

```
[default]
aws_access_key_id=foo
aws_secret_access_key=bar
region_name=us-west-2
```

Here "default" is the default profile name. boto3 supports profiles, but s3fs does not appear to. It is also a good idea to be mindful of where resources are located on AWS, especially because data transfer can be very expensive. You can set your preferred region via environment by setting the variable `AWS_DEFAULT_REGION`. From experience, this default is not respected by s3fs. If you are playing around with s3fs, you will find you need to pass your desired region in using the region_name kwarg.

*note* that `awscli s3 <cmd>` gives you a filesystem-like command line interface to s3 just like s3fs gives from within python, and understands the same credentials above.

*note* s3 bucket names can be used in public urls to facilitate access to the data. Thus, they must be unique by region (that is a huge user pool). It behooves you to come up with a naming scheme that guides you away from trivially common words and phrases.

## EC2 Credentials

ec2 will rely on the same credentials setup for s3, thanks to aws tooling generally using the same mechanisms for authentication: environment variables or configuration files. However, the parallel cluster layered on top of ec2 instances requires an additional piece of security: an ec2 SSH keypair.

ensure you create or upload the keypair in the correct region.

# Copying Data to S3

Keep in mind that S3 is flat storage, and all likeness to a filesystem scheme is just naming conventions.

*NOTE: think long and hard about how to get code out to the nodes. git clone? what do we do about local installs? is the clone done by a pre-install bootstrap script or is it a pre-task of the simulation running? How do I send environments out to the jobs?
Maybe the code needs to live on S3. Maybe you can clone or copy up a tar (local installs).*

## bootstrap script

Certain software is required to run Vivarium simulations, foremost is Python 3. To configure the cluster, we provide a shell script that installs the necessary software, and denote this as a bootstrap script in the cluster configuration. However, the expected location is on S3, so the script must be copied there. Importantly, this script will be used to setup the conda environment with the code to run the simulation, so it is model-specific. To do this, run `cmd`.

## Data Artifact

S3 is used for persistent storage on the cluster that is visible to all cluster nodes. This is where the data artifact for the simulation should be stored, and it's where simulation outputs are stored. Vivarium aws provides tools to help copy data between your local machine and s3 as well as parse simulation results.

To run a simulation on AWS, you must copy your data artifact to S3 and ensure that the model configurations point to the artifact's location. These are model-specific tasks and must be repeated for each different model you wish to run.

To copy, peruse, etc artifacts on S3, do the following, use the following commands.

# Configuring the Cluster

We can now initiate your SGE cluster from the configuration provided by this repository. To do this, we will rely on aws-parallelcluster.

`pcluster configure`

create a cluster that you will use to run the simulations
important aspects -- min and max cluster size, instance type

cluster type must be sge, this is what Vivarium is configured for.

`pcluster create` -- note that this will create a running instance of a master node for the cluster which will consume resources -- and thus cost money -- until the cluster is deleted.

Take a look at the configuration file, the key parameters are annotated. AWS also provides an exhaustive documentation.

## Connecting to your cluster

pcluster ssh cluster-name [-i ~/path/to/sshkey]

# Running a Simulation

## Initiation

## Monitoring

# Looking Simulation Results

# Architecture

Vivarium AWS is built upon aws-parallelcluster, which itself relies upon boto3 and aws-clit. All of these provide interfaces to AWS' many services. parallelcluster provides quick and easy configuration of an SGE cluster on top of AWS resources, which is the same sort of cluster IHME uses in house.

Amazon ec2 instances are used for the master node and compute node. S3 is used for artifact and results storage, and the cluster configuration provides access to S3 from each ec2 instance. Additionally,cloudformation is used for configuration, and some queueing services and a NoSQL database are used in the administration of the cluster.

The most important aspect for a user wishing to run simulations is the ec2 instance, specifically its size. You can find this declared in the cluster configuration, and it dictates the amoutn of RAM available for a simulation. A research repository should document the resources necessary to run the simulation.

## Cost considerations

min and max cluster size
ec2 node size
master node running indefinitely
    stop your cluster to avoid costs
    use the aws cost explorer to examine your costs
S3 versus other storage backends
data locality -- stay within region
spot instances

# Helpful Things

s3fs docs -- https://s3fs.readthedocs.io/en/latest/index.html
bucket naming docs -- https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-s3-bucket-naming-requirements.html

boto3 docs -- https://boto3.amazonaws.com/v1/documentation/api/latest/index.html
aws-parallelcluster docs -- https://github.com/aws/aws-parallelcluster
aws-cli docs -- https://github.com/aws/aws-cli
    helpful credential info


# TODO:

Copy local configuration, annotate and set it up
Write S3 manipulation tools. Copy artifact up
run a test job to see if everything can see the artifact
write the bootstrap script and try it
decide how best to trigger a simulation - paramiko? gRPC?
figure out how to pull out pathing and abstract awa S3. S3 config key?
