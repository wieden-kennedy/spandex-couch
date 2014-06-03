#!/usr/bin/python
from fabric.api import *
from fabric.contrib.files import exists
from fabric.colors import red as _red, green as _green, yellow as _yellow, white as _white
from fabric.utils import abort

import json

from time import sleep

from os.path import join
import os

from binascii import b2a_hex

from re import match

import boto.ec2
from boto.ec2.connection import EC2Connection
from boto.ec2.elb import ELBConnection

'''
ENVS
'''
def user(user):
    env.user=user
    print(env.user)

def config():
    ENVIRONMENT = os.environ.get("COUCHENV","development")
    if ENVIRONMENT in ['prod', 'production']:
        config_file_path = './config/production.json'
    elif ENVIRONMENT in ['test','staging']:
        config_file_path = './config/staging.json'
    elif ENVIRONMENT in ['dev','development']:
        config_file_path = './config/dev.json'
    elif ENVIORNMENT in ['local']:
        config_file_path = './config/local.json'
    else:
        abort(_red('No COUCHENV or config file defined. Either define COUCHENV=[prod|test|dev] or call fab config:/path/to/config/file spinup:[ID]'))

    opts = {}
    with open(config_file_path) as data_file:
        '''
        load in template data from data file
        '''
        opts = json.load(data_file)

    opts['environment'] = ENVIRONMENT.upper()

    '''
    ensure required properties are present in config file
    '''
    if all (k in opts for k in ('user','ssh_keyfile','project_name','aws_access_key_id','aws_secret_access_key','aws_ami','aws_keypair_name','aws_ec2_region','aws_instance_type','aws_security_group')):
        return opts
    else:
        print(_red('One or more required fields are missing. Ensure that the following properties are included in your config file:\n'))
        print(_white('%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s' % ('user','ssh_keyfile','project_name','aws_access_key_id','aws_secret_access_key','aws_ami','aws_keypair_name','aws_ec2_region','aws_instance_type','aws_security_group')))
        abort('Aborting.')

'''
PUPPET TASKS
'''
'''
install puppet on remote host
'''
def install_puppet():
    if not exists('/usr/bin/puppet'):
        sudo('wget https://apt.puppetlabs.com/puppetlabs-release-precise.deb -O /tmp/puppet-labs-release-precise.deb')
        sudo('dpkg -i /tmp/puppet-labs-release-precise.deb')
        sudo('apt-get -y update')
        sudo('apt-get -y install puppet')

'''
use the properties defined in deploy to construct a puppet apply statement to install the module
'''
def apply_couch_module(properties_map):
    properties_string = str(properties_map).replace("{'","{").replace(", '",", ").replace("':",":").replace(':',' =>').replace("'True'","'true'").replace('True',"'true'")[1:-1]
    couchdb_class="class {'couchdb': %s}" % properties_string    
    sudo('puppet apply -e "%s"' % couchdb_class)

'''
git clone puppet module repo to remote host
'''  
def clone_puppet_repo(retry_count=0):
    with cd('/etc/puppet/modules'):
        if not exists('couchdb'):
            try:
                sudo('git clone https://github.com/wieden-kennedy/spandex-couch /etc/puppet/modules/couchdb')
            except SystemExit as e:
                if retry_count < 1:
                    print(retry_count)
                    retry_count+=1
                    print(_red("\nError with github authentication. Reattempting one more time.\n"))
                    clone_puppet_repo(retry_count)
                else:
                    print(_red("\nGithub authentication failed. Please run the command again with the proper credentials."))
        else:
            print(_green("Puppet module already exists. Attempting to update module from git."))
            update_puppet_repo()

'''
git pull to update puppet repo on remote host
'''
def update_puppet_repo():
    with cd('/etc/puppet/modules/'):
        if not exists('couchdb'):
            clone_puppet_repo()
    with cd('/etc/puppet/modules/couchdb'):
        status=sudo('git status | awk \'NR==2\'')
        if not match('nothing to commit',status):
            sudo('git pull')
        else:
            print(_green('Puppet module already up-to-date.'))


'''
prompt operator for key properties during deploy. These properties will affect the couchdb module setup.
pressing Enter at prompt will assume default value
'''
def get_puppet_properties():
    properties = {}

    print(_white('Enter setup information. Defaults in %s. ' % _green('green')))
    prompt(_white('To keep default, simply press enter when prompted. \nAll optional unless noted. Press enter to continue.'))
    properties['bind'] = prompt(_white('CouchDB bind address %s ' % _green('[0.0.0.0]:'))) or '0.0.0.0'

    properties['database_dir'] = prompt(_white('CouchDB database dir %s ' % _green('[/usr/local/var/lib/couchdb]:'))) or None
    
    '''
    admin user info 
    '''
    properties['admin_user'] = prompt(_white('CouchDB admin user %s ' % _green('[None]:'))) or None
    if properties['admin_user']:
        properties['admin_password'] = None
        while not properties['admin_password']:
            properties['admin_password'] = prompt(_white('CouchDb admin password %s ' % _green('[None] :'))) or None

    '''
    masterless/slave setup
    '''
    properties['couchdb_masterless_mode'] = bool(prompt(_yellow('Run as part of a masterless cluster %s ' % _green('[y/N]:')))) or False
    if not properties['couchdb_masterless_mode']:
        properties['slave_mode'] = bool(prompt(_yellow('Run as a slave to another master %s ' % _green('[y/N]:')))) or False
    else:
        properties['slave_mode'] = False
    if properties['couchdb_masterless_mode'] or properties['slave_mode']:
        properties['couchdb_master_hostname'] = None
        properties['couchdb_master_ip'] = None
        while not properties['couchdb_master_hostname']:
            properties['couchdb_master_hostname'] = prompt(_white('Hostname of CouchDB master server -- required: ')) or None
        while not properties['couchdb_master_ip']:
            properties['couchdb_master_ip'] = prompt(_white('IP Address of CouchDB master server -- required: ')) or None

    return properties


'''
COUCHDB SETUP
'''
'''
drop and recreate couchdb databases defined by puppet module
'''
def couchdb_flush(setup_database=True, flush_database=True):
    args = ''
    if setup_database:
        args += '-setup-database '
    if flush_database:
        args += '-flush'

    run('/usr/bin/python /usr/local/sbin/couchdb_setup.py %s' % args)

'''
replicate masterless or slave server to master
'''
def couchdb_replicate(masterless=False,slave=False):
    if masterless or slave:
        run('/usr/bin/python /usr/local/sbin/database_replication.py')


'''
SYSTEM TASKS
'''
'''
update hosts file from puppet manifest
'''
def update_hosts():
    sudo('cat /etc/hosts > /etc/hosts.bak')
    sudo('echo "127.0.0.1    `cat /etc/hostname`" > /etc/hosts')
    sudo('cat /etc/hosts.bak >> /etc/hosts')

'''
amend /etc/rc.local with boot TASKS
'''
def amend_rc_local(masterless):
    # back up and ensure current rc.local contents are in the new rc.local
    sudo('cat /etc/rc.local > /etc/rc.local.bak')
    sudo('mv /tmp/rc.local /etc/rc.local')
    sudo("cat /etc/rc.local.bak | grep -v '#' | grep -v 'exit 0' >> /etc/rc.local")
    sudo('echo "\ncd /etc/puppet/modules/couchdb" >> /etc/rc.local')
    sudo('echo "sleep 10" >> /etc/rc.local')
    if masterless:
        sudo('echo "/usr/local/bin/fab replicate_database_to_master" >> /etc/rc.local') 
    sudo('echo "/usr/local/bin/fab newrelic_couchdb_monitor" >> /etc/rc.local')
    sudo('echo "\nexit 0" >> /etc/rc.local')
    sudo('rm /etc/rc.local.bak')


'''
NEW RELIC TASKS
'''
def newrelic_setup(newrelic,newrelic_key):
    if newrelic:
        newrelic_sysmond(newrelic_key)
        newrelic_couchdb_monitor()

'''
set up new relic sysmond
'''
def newrelic_sysmond(newrelic_key):
    if not exists('/usr/sbin/nrsysmond'):
        sudo('echo deb http://apt.newrelic.com/debian/ newrelic non-free >> /etc/apt/sources.list.d/newrelic.list')
        sudo('wget -O- https://download.newrelic.com/548C16BF.gpg | sudo apt-key add -')
        sudo('apt-get update')
        sudo('apt-get install newrelic-sysmond')

    '''
    kill running processes for nrsysmond
    '''
    with warn_only():
        count=2
        while count > 0:
            count -= 1
            pid=None
            pid=run('ps -u newrelic | grep nrsysmond | head -1 | awk \'{print $1}\'')
            if pid:
                sudo('kill -9 %s' % pid)    

        sudo('/usr/sbin/nrsysmond-config --set license_key=%s' % newrelic_key)
        sudo('/etc/init.d/newrelic-sysmond start')

'''
set up new relic couchdb monitor plugin
'''
def newrelic_couchdb_monitor():
    pip=run('which pip')
    if not pip: 
        sudo('apt-get -y install gcc python-dev python-pip')

    plugin=run('which newrelic_plugin_agent')
    if not plugin:
        sudo('pip install newrelic-plugin-agent')

    '''
    kill running newrelic_plugin_agent process, if it exists
    '''
    with warn_only():
        pid=run('ps -u newrelic | grep newrelic_plugin | head -1 | awk \'{print $1}\'')
        if pid:
            sudo('kill -9 %s' % pid)
        sudo('/usr/local/bin/newrelic_plugin_agent -c /etc/newrelic/newrelic_plugin_agent.cfg',pty=False)


'''
DEPLOY
'''
def deploy():
    if not exists('/home/%s' % env.user):
        sudo('mkdir /home/%s' % env.user)
        sudo('chown %s:%s /home/%s' % (env.user,env.user,env.user))
    puppet_properties = {}
    properties = get_puppet_properties()
    puppet_properties.update((k,v) for k,v in properties.iteritems() if v) 
    puppet_properties['couchdb_hostname'] = env.host

    '''
    if the desired couchdb database path DNE, create it
    '''
    if 'database_dir' in puppet_properties:
        if not exists(puppet_properties['database_dir']):
            sudo('mkdir -p %s' % puppet_properties['database_dir'])

    '''
    ensure puppet is installed before running module
    '''
    install_puppet()
    
    '''
    ensure puppet repo is up-to-date on host then apply couch module
    '''
    update_puppet_repo()
    apply_couch_module(puppet_properties)
    # update_hosts()

    '''
    adding a small sleep to ensure couchdb is running before setting up dbs and replicating
    '''
    run('sleep 10')
    couchdb_flush()
    couchdb_replicate(properties['couchdb_masterless_mode'],properties['slave_mode'])
    
    '''
    new relic setup - ask operator if s/he wants to set up new relic monitoring
    '''
    newrelic = bool(prompt(_white('Set up New Relic monitoring %s ' % _green('[y/N]:')))) or False
    if newrelic:
        newrelic_key = None
        while not newrelic_key:
            newrelic_key = prompt(_white('Enter your New Relic license key -- required: ')) or None
    
    if newrelic and newrelic_key:
        newrelic_setup(newrelic,newrelic_key)

    '''
    if this is the first time it has run, amend rc.local with appropriate commands
    '''
    if not exists('/etc/puppet/.couchdb.deployed'):
        amend_rc_local(properties['couchdb_masterless_mode'])
    '''
    add a blank hidden file to let us know this deploy has already run
    '''
    sudo('touch /etc/puppet/.couchdb.deployed')


'''
EC2
'''
class EC2:
    def __init__(self,EC2_REGION,ACCESS,SECRET):
        #self.conn = EC2Connection(ACCESS, SECRET)
        self.conn = boto.ec2.connect_to_region(EC2_REGION, aws_access_key_id=ACCESS,
                                          aws_secret_access_key=SECRET)
        self.elb_conn = boto.ec2.elb.connect_to_region(EC2_REGION,aws_access_key_id=ACCESS,aws_secret_access_key=SECRET)

'''
add the created instance to an existing load balancer.
if the load balancer doesn't cover the placement zone of the created instance, operator will be prompted as such.
continuing at that point is optional, but the instance won't be covered by the load balancer.
'''
def add_to_load_balancer(ec2,load_balancer_name,instance,instance_availability_zone):

    load_balancer = ec2.elb_conn.get_all_load_balancers(['%s' % load_balancer_name])[0]
    
    try:
        '''
        check to make sure instance availability zone is covered by load balancer.
        '''
        if instance_availability_zone:
            if not load_balancer.is_cross_zone_load_balancing():
                load_balancer.enable_cross_zone_load_balancing()
            load_balancer.enable_zones(['%s' % instance_availability_zone])
        '''
        register new instance with load balancer
        '''
        load_balancer.register_instances(['%s' % instance])
        print(_yellow("EC2 Instance added to load balancer."))
    except Exception as e:
        print(_red("Failed to add EC2 Instance to load balancer. Please add instance manually."))

'''
spin up new EC2 instance, optionally add to load balancer, and deploy couchdb module
'''
@runs_once
def spinup(suffix):

    '''
    if no suffix was defined for the new instance, generate one at random
    '''
    if not suffix:
        suffix = b2a_hex(os.urandom(4))

    '''
    get environment options and create an ec2 connection
    '''
    opts = config()
    env.user = opts['user']
    host_name = '%s-CouchDB-%s' % (opts['environment'], suffix)
    ec2 = EC2(opts['aws_ec2_region'],opts['aws_access_key_id'],opts['aws_secret_access_key'])

    print(_green("Started..."))
    print(_yellow("...Creating EC2 instance..."))

    '''
    check if user has defined specific placement zone
    '''
    desired_availability_zone = None
    if 'aws_ec2_availability_zone' in opts:
        desired_availability_zone = opts['aws_ec2_availability_zone']

    '''
    clone the defined ami to a new instance
    '''
    reservation = ec2.conn.run_instances(opts['aws_ami'], placement=desired_availability_zone ,key_name=opts['aws_keypair_name'], instance_type=opts['aws_instance_type'], security_groups=opts['aws_security_group'])
    instance = reservation.instances[0]

    '''
    update progress
    '''
    while instance.state != 'running':
        print(_yellow("Instance state: %s" % instance.state))
        sleep(1)
        instance.update()

    '''
    tag the new instance
    '''
    ec2.conn.create_tags([instance.id], {'Name': '%s' % host_name })
    if opts['project_name']:
        ec2.conn.create_tags([instance.id], {'Project': opts['project_name']})

    '''
    update progress
    '''
    print(_yellow("Launched: %s, %s" % (instance.dns_name, host_name)))
    print(_green("Instance state: %s" % instance.state))
    print(_green("Public dns: %s" % instance.public_dns_name))

    '''
    if you want to add the new instance to a load balancer, you can do that.
    '''
    add_to_lb = prompt(_white("Add new EC2 instance to an ELB %s" % _green('[y/N]: '))) or None
    if add_to_lb:
        add_to_lb = prompt(_white("Adding this to the ELB will automatically enable the availability zone for your EC2 instance if not already enabled for this ELB. Proceed %s " % _green('[y/N]: ')))
        if add_to_lb:
            load_balancer_name = None

            if 'aws_elb_load_balancer' not in opts:
                while not load_balancer_name:
                    load_balancer_name = prompt(_white('Load Balancer Name --required: ')) or None
            else:
                load_balancer_name = opts['aws_elb_load_balancer']            

            '''
            if no desired_availability_zone was defined in the config, set it now to the instance's placement group
            '''
            if not desired_availability_zone:
                desired_availability_zone = instance.placement
            
            add_to_load_balancer(ec2,load_balancer_name,instance.id,desired_availability_zone)

    '''
    update local ssh config so new instance is ssh-ready
    '''
    local('echo "\nHost %s" >> ~/.ssh/config' % host_name)
    local('echo "HostName %s" >> ~/.ssh/config' % instance.dns_name)
    local('echo "User %s" >> ~/.ssh/config' % env.user)
    
    '''
    run couchdb deploy
    '''
    print(_yellow("Deploying CouchDB Puppet Module..."))
    env.host_string = instance.dns_name
    deploy()
