# Spandex Couch

Module for configuring, deploying, and load-balancing EC2 [CouchDB](http://couchdb.apache.org/) instances with fabric.  
Puppet module based on [puppet-module-couchdb](https://forge.puppetlabs.com/benjamin/couchdb) by [Benjamin Dos Santos](https://github.com/bdossantos) 

## Table of Contents
- [License Info](#license-info)
- [Features](#features)
- [Run Environment](#built-for)
- [Prerequisites](#prerequisites)  
- [Setting up databases](#setting-up-databases)  
- [Installation with Fabric](#running-with-fabric)  
	- [Config](#config-files)
	- [Environment variable](#environment)
	- [Spinning up a new EC2 instance](#spinning-up-a-new-ec2-instance)
	- [Load balancing](#adding-the-ec2-instance-to-a-load-balancer) 
	- [Deployment](#deploying-to-the-new-instance)
	- [Deployment, cont.](#deploying-to-an-existing-instance)
	- [Additional fabfile commands](#additional-fabfile-commands)  
		-[install_puppet](#install_puppet)  
		-[couchdb_flush](#couchdb_flush)  
		-[couchdb_replicate](#couchdb_replicate)  
		-[newrelic_setup](#newrelic_setup)  
		-[newrelic_sysmond](#newrelic_sysmond)  
		-[newrelic_couchdb_plugin](#newrelic_couchdb_plugin)  
- [Running with Puppet masterless](#running-with-puppet-masterless)  
	- [Key parameters](#key-parameters-for-using-puppet-masterless)  
- [Bugs/Issues](#bugs-and-issues)

##License info
This repository is licensed under the BSD 3-Clause license. You can view the license [here](https://github.com/wieden-kennedy/spandex-couch/blob/master/LICENSE)

##Features
+ Spin up new EC2 instances and add them to an existing load balancer
+ One-step EC2 instance launch, load balancing and couchdb deployment
+ Follow-up on running instances with tools like ability to flush CouchDB databases, replicate databases
+ Installs puppet on target host if not present
+ Basically, you just define the environment for your CouchDB server, and pull the trigger.


##Built for  
+ Ubuntu Precise 64 Bit with Puppet 3.4.2


## Prerequisites  
+ git
+ pip (Used for fabric and newrelic montioring installs)
+ fabric (and deps: gcc, python-dev, python-pip)
+ boto

##Setting up databases 
To set up your databases prior to running, you will need to take a few steps: 
 
**1. Edit /manifests/init.pp.**  
Edit the name of your database, and add additional databases if needed. The database property to be edited is ```$couchdb_database_1```. Simliarly, if you want to add more databases, you can add ```$couchdb_database_2, $couchdb_database_3, etc```  

**2. Edit /templates/tmp/couchdb_setup.py.erb**  
Add your database's needed views in JSON format. If you have added more databases to your CouchDB instance, clone the single database schema entry and replace the database name as necessary.  

**3. IF YOU HAVE ADDED DATABASES, edit /templates/tmp/database_replication.py.erb**  
Add your new database(s) to the global vars list, and to add the new db variable to the DBS array.


## Installation
## Running with Fabric   
### Config files
In the root of the module repo, find the ```config``` directory. There you can define the values for development, staging, and production. The values have been marked as **required** or **optional** in the template files, and examples have been provided where applicable.  

###Environment
The fabric runner is based on an Environment variable, COUCHENV. This will determine which config file is pulled:  

+ 'dev' or 'development' --> config/dev.json  
+ 'test' or 'staging' --> config/staging.json  
+ 'prod' or 'production' --> config/production.json  

If you want to add more environments, you can. Just add the config file, then edit the config() method in ```fabfile.py```


###Spinning up a new EC2 instance
Spinning up a new EC2 CouchDB instance is easy:  

```COUCHENV=dev fab spinup```  

```COUCHENV=dev``` sets the environment to 'dev', making the fab runner select config/dev.json  
```spinup``` causes the fab runner to spin up a new EC2 instance, using a random hex string as a suffix.  

Using the above command would generate an EC2 box called: ```DEV-CouchDB-[random_hex_string]``` in whatever zone is defined in the dev.json config file 

If you would prefer to name the suffix for the new instance, run:  

```COUCHENV=dev fab spinup:MY_SUFFIX```  

###Adding the EC2 instance to a load balancer
You may choose to define an existing load balancer in your config files that will allow you to immediately stick the new CouchDB instance behind that load balancer.  Alternately, if you do not specify one in your config files, you may enter it when prompted.  

After the EC2 instance is deployed, you will be prompted as to whether you want to put the new instance behind a load balancer:  

```Add new EC2 instance to an ELB [y/N]: ```  

To add the new instance to a load balancer, type **y**. To skip this part, simply press **Enter**.  
If you choose **y**, and haven't defined a load balancer, you will be prompted to enter the name of your load balancer before adding the instance.  

###Deploying to the new instance
After the optional load balancer addition, the ```spinup``` runner will move into deploy mode.  
In deploy mode, you will be prompted to enter a number of settings.  

Pressing **Enter** when prompted will retain the default values:  

+ **bind address** (optional, defaults to 0.0.0.0)  
+ **database direcotry** (optional, defaults to /var/lib/couchdb)
+ **admin user** (optional)
+ **admin password** (required if admin user present)
+ **masterless mode** (optional - if **yes** then this instance will be mirrored in a masterless cluster with another CouchDB instance)
+ **slave mode** (optional - if **yes** then this instance will act as a slave to another CouchDB instance)
+ **master hostname** (required if masterless or slave mode - the dns name for the CouchDB master instance)
+ **master ip address** (required if masterless or slave mode - the IP address of the CouchDB master instance)
+ **new relic monitoring** (optional - whether to monitor this instance with New Relic)
+ **new relic license key** (required if new relic monitoring - your license key for New Relic)

After entering these values, the puppet module will be cloned to your instance, and deployed.

###Deploying to an existing instance
To update settings on an existing instance, just run:  
```
fab -H [hostname] user:my_user deploy
```  
This will run the deploy portion of the fab runner, where you will be prompted to enter the same property choices as described above. This command can be used to deploy the CouchDB module to an existing instance, or to update properties on an instance that has already had the module deployed to it.

### Additional fabfile commands
There are a few other fab commands in the project's fabfile worth noting, as they can shortcut some of your updating work.

####install_puppet
running ```fab -H [host] user:my.user install_puppet``` will install puppet on the target host.

####couchdb_flush
running ```fab -H [host] user:my.user couchdb_flush``` will drop and recreate the tables defined by the script in /templates/tmp/couchdb_setup.py.erb

####couchdb_replicate
running ```fab -H [host] user:my.user couchdb_replicate``` will replicate a masterless instance to the master, or a slave to its master based on the database tables you define in the puppet manifest.  
**NOTE: ** by default only one table is defined in the puppet manifest - additional tables will need to be added both to the manifest as well as have placeholder vars defined in /templates/tmp/database_replication.py.erb

####newrelic_setup
running ```fab -H [host] user:my.user newrelic_setup:True,new-relic-license-key``` will run both the New Relic sysmond process to monitor the server, as well as trigger the New Relic couchdb plugin to monitor database performance. 

####newrelic_sysmond
running ```fab -H [host] user:my.user newrelic_setup:new-relic-license-key``` will run the New Relic sysmond process to monitor the server

####newrelic_couchdb_monitor
running ```fab -H [host] user:my.user newrelic_couchdb_monitor``` will trigger the New Relic couchdb plugin to monitor database performance.


## Running using puppet masterless
If you've cloned this repo to the puppet modules directory on a server, the module can be installed using standard puppet apply syntax:
```bash
puppet apply -e "class{'couchdb': param_1 => 'value', param_2 => 'value2', param_n => 'value_n'}"
```  

**NOTE:** you will not be able to set up New Relic Monitoring if using standard Puppet apply commands.

### Key Parameters for using puppet masterless
The following parameters can be passed to the puppet apply command to change the install properties:  
+ **bind** - the IP address to which the couchdb server should be bound  
+ **couchdb_master_hostname** - the FQDN of the host that will serve as the master couchdb server  
+ **couchdb_master_ip** - the IP address of the host that will serve as the master couchdb server  
+ **couchdb_hostname** - the hostname for the couchdb instance, to be used with new relic monitoring  
+ **first_run** - whether to initiate first-run setup which includes templating helper scripts to do an initial setup  
+ **flush_dbs** - whether to flush the existing databases when applying the module  
+ **slave_mode** - whether to install the module as a slave server to a master couchdb database  
+ **couchdb_masterless_mode** - whether to set up bi-directional replication between this couchdb instance and another master  
+ **admin_user** - an admin user to use for authentication (requires admin_password)  
+ **admin_password** - the password for the db admin user (requires admin_user)  
 
## Bugs and Issues
Bugs, issues and patch requests can be submitted in the [Issues section of this repo](https://github.com/wieden-kennedy/puppet-couchdb/issues).

