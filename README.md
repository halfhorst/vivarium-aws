# vivarium-aws

A Python package that makes it easy to provision resources and run Vivarium simulations on Amazon Web Services (AWS). This was made to further the goal of reproducible model results by eliminating the requirement of access to IHME infrastructure.

# Overview

This library is intended to provide the shortest path to propping up a dynamic SGE (Son of Grid Engine) cluster in the cloud configured to run Vivarium simulations. A cluster made with this library is disposable and can be re-made very easily, scales up to the amount of work submitted (with a limit) and back down when there is no work to be done, and is created with the code and data necessary to run a specific Vivarium simulation, though it can be used to run whatever you want if you push the right data up to it. It weaves together several utilities, providing sane defaults and provisioning for the Vivarium ecosystem. Familiarity with AWS would be helpful but should not be required. An AWS account is mandatory, however, and we will not stay within the bounds of the free tier.

Setting up a cluster containing on artifact and simulation code is fast and inexpensive. I takes roughly ten minutes, excluding one-time setup like creating an IAM role and an S3 bucket, and most of this time is spent building the machine image and waiting for EC2 instances to come online. The steps to get there go like this:

##### AWS Setup

This setup will be performed infrequently, or potentially just once.

1. Create an IAM role and give it the permission to manipulate EC2 and S3 resources. Set up its credentials on your machine.

2. Create an S3 bucket to hold your simulation results.

3. Create an EC2 keypair.

##### Provisioning the Cluster

1. Make a configuration describing an Amazon Machine Image (AMI) configured for a specific Vivarium simulation.

2. Build the machine image.

3. Make a configuration for an SGE cluster composed of machines running the AMI made in the previous step.

4. Create the cluster

5. Connect via SSH/mosh and run simulations

The AWS setup can be performed with any of the tools Amazon provides for interacting with AWS resources (the AWS cli, a client library like boto3 for python, the management console) but the management console is the most beginner-friendly, albeit still confusing at times.

vivarium-aws itself provides command line tools under `vaws` for performing the cluster provisioning tasks. These commands are generally thin wrappers on top of `packer` and `pcluster` (from aws-parallelcluster), with Vivarium-specific help where necessary. The native configuration formats for each of these tools is preserved, and they can be used with the outputs from `vaws` as desired. In fact, once a cluster is running, `pcluster` is the right way to deal with it.

# Requirements

In addition to its python dependencies, vivarium-aws requires [Packer](https://www.packer.io/) to help build machine images.

# AWS setup

## IAM and Credentials

Identity and access management (IAM) is an important security aspect of AWS. An AWS account defaults to a root user with complete control over resources. You can control this unfettered access, though it is not necessary, by creating an IAM user with programmatic access and permissions limited to the scope of work and use that to administer services. The aws-parallelcluster docs have more information on what specific permissions you would need to provide [here](https://docs.aws.amazon.com/parallelcluster/latest/ug/iam.html).


You will use your new IAM user or root user's access key to run vaws commands. By default, vaws (and most AWS tools) will look for credentials in several locations, inlcuding hidden locations on disk and environment variables. The simplest thing to do is to place your user credentials in the file `~/.aws/credentials` where they will be automatically picked up. This is also where you should specify your default AWS region, where your resources will be provisioned.

```
[default]
aws_access_key_id=<your access key id>
aws_secret_access_key=<your access key>
region=<your region>
```

See [here](https://boto3.amazonaws.com/v1/documentation/api/latest/guide/configuration.html) for more information on credentials. Since vivarium-aws uses boto3, any of these methods should work.

## S3 Buckets

S3 (Simple Storage Service) is basic cloud storage. It's used by vivarim-aws to stash a cluster provisioning script and it is also a logical long-term home for simulation results your cluster produces. S3 is organized around buckets that contain block data in named keys. There is no actual filesystem or hierarchy but the notion is respected in keys with a pathlike name by convention in the UI. You need to create a bucket to stash your results in the S3 console. It doesn't matter if the bucket is private or public.

## EC2 keypairs

An EC2 keypair is a named public key that is used to connect to EC2 instances. You will provide this key's name when configuring the cluster and use it to connect to your cluster. You can create one in the console, or create one on your local machine and import it by copying the public key into the console.

# Running a simulation

## Making a Cluster

Before making the cluster, a machine image containing the code and data needs to be created. Use `vaws configure ami`, giving it a path to the root of a Vivarium simulation package, and then create an image from the resulting configuration using `vaws make ami`. You will need access to the data artifacts specified in each model specification's artifact_path key or at the locations specified as command line options.

Once the AMI is made you can create a cluster configuration using `vaws configure cluster` and then provision it with `vaws make cluster`. When you configure your cluster, you will provide the S3 bucket you want access to as well as the ID of the AMI you just created with the code and data (you can retrieve your AMI ID using the EC2 management console). At configuration time you can optionally specifiy a few other important aspects of the cluster.

* The instance type of the master and compute nodes. Your master node should be big enough to hold a batch of results, and the compute nodes should be able to run a simulation. Since Vivarium simulations are single-threaded, so multiple jobs will run on an instance with multiple vCPUs.

* The max queue size. This is the upper bound on the number of compute instances that will be spawned. Since work is deterministic and not spawned in response to external events, there isn't risk of unbounded workers. You likely want to just set this to the number of simulations dictated by your branches file.

* The master subnet id. A subnet is a chunk of your Virtual Private Cloud (VPC), your own personal block of IP addresses to use amongst your resources. The subnet id is relevant because it is specific to an availability zone, which sits underneat a region. EC2 instance type availability is availability zone-specific. One thing vivarium-aws can't handle intelligently is picking a subnet id for you based on your instance choices. If you don't specify a subnet it will pick one of yours, but it may not work. This should be the first place you look.

## Connecting and Running a Simulation

Once the cluster comes online you can SSH into it directly using the username `ubuntu` and it's public IP, or using `pcluster ssh`:

```
$> ssh ubuntu@<public IP>
```

The cluster is also configured to allow connections via [`mosh`](https://mosh.org/), which is a remote shell that enables roaming. It is very useful and will allow you to reconnect to your running simulation if you get disconnected.

Inside the cluster, the simulation code lives in `ubuntu`'s home directory. A conda environment named `simulation` has been created with all the necessary packages installed, so activate it and start a simulation with `psimulate`. Not all model specifications are valid, though -- only the ones for which you uploaded data artifacts. The data artifacts are located at `/usr/local/share/vivarium/artifacts`.

## Retrieving Results

Once your simulation is finished, you can send it to the S3 bucket you configured your cluster to have access to using the aws cli. You can move all of the simulation related data, including logs, by syncing a local directory with your s3 bucket:

```
$> aws s3 sync /path/to/simulation/output s3://<bucket_name>/desired_key_name
```

The model results will then be persisted in S3 and can be downloaded from the console or any other AWS interfaces.

## Administering the cluster

Since clusters made with `vaws` are made using aws-parallelcluster, you can use `pcluster` to administer them. `list` will show clusters still present in the cloud, and `status` will give you more information about a cluster, including its public IP.

Other useful commands are `stop` to take down your instances and cease paying for compute time, and `delete` to safely remove all of your cloud resources. You can also alter the cluster configuration and push this up to a running cluster with `update`.You can stop your cluster to cease paying for compute time, and you can and should delete the cluster using `pcluster delete`. Doing so will ensure that your cloud resources are cleaned up nicely.

# Cost Considerations

The majority of the cost of running a simulation will come directly from EC2 compute time and, to a smaller degree, data transfer costs sending the machine images to the nodes. There is little extra cost due to data storage because simulation output sizes are small on S3's scale, as are AMI sizes. Nonetheless, run a small simulation first and use the cost explorer to see the effects.

There are a few important things to keep in mind, though. Transfering data between regions gets expensive fast, so be sure that you are building your AMI and your cluster in the same region. Paying for a single, moderately sized t2 instance is not expensive on a monthly basis, but if you leave a large cluster running things will add up, so stop your cluster if you aren't using it. Finally, running a network address translation (NAT) gateway continuously can get expensive as well. A NAT gateway shouldn't be used if the cluster configuration specifies to use public IPs. The address translation is required when translating public to private. Using public is the default, but be aware if you change it.

# TODO:

* Add a Docker builder
* Consider a way to eliminate AMI building using NFS

# Links

* [aws-parallelcluster](https://github.com/aws/aws-parallelcluster)
* [boto3](https://github.com/boto/boto3)
* [aws-cli](https://github.com/aws/aws-cli)
* [Packer](https://www.packer.io/)

