class couchdb::install {

  if versioncmp($couchdb::foldername, 'apache-couchdb-1.5.0') >= 0 {
    $version = '1.5'
  }

  Exec {
    unless => '/usr/bin/test -f /usr/local/bin/couchdb',
  }

  package { $couchdb::package::dependencies:
    ensure => 'installed',
  }

  user { 'couchdb':
    ensure      => present,
    home        => '/usr/local/var/lib/couchdb',
    managehome  => false,
    comment     => 'CouchDB Administrator',
    shell       => '/bin/bash'
  }

  user { 'newrelic':
    ensure      => present,
    home        => '/usr/loca/var/lib/newrelic',
    managehome  => false,
    comment     => 'Newrelic daemon',
    shell       => '/bin/bash',
  }

  exec { 'download':
    cwd     => $couchdb::cwd,
    command => "/usr/bin/wget -q ${couchdb::download} -O ${couchdb::filename}",
    timeout => '120',
  }

  exec { 'extract':
    cwd     => $couchdb::cwd,
    command => "/bin/tar -xzvf ${couchdb::filename}",
    timeout => '120',
    require => Exec['download'],
  }

  exec { 'configure':
    cwd         => "${couchdb::cwd}/${couchdb::foldername}",
    environment => 'HOME=/root',
    command     => "${couchdb::cwd}/${couchdb::foldername}/configure ${couchdb::package::buildoptions}",
    timeout     => '600',
    require     => [
      Exec['extract'],
      Package[$couchdb::package::dependencies]
    ],
  }

  exec { 'make-install':
    cwd         => "${couchdb::cwd}/${couchdb::foldername}",
    environment => 'HOME=/root',
    command     => '/usr/bin/make && /usr/bin/make install',
    timeout     => '600',
    require     => Exec['configure'],
  }

  File {
    owner   => 'couchdb',
    group   => 'couchdb',
    mode    => '0700',
    require => [
      Exec['make-install'],
      User['couchdb']
    ],
  }

  file {
    [$couchdb::database_dir, '/usr/local/etc/couchdb',
    '/usr/local/var/log/couchdb', '/usr/local/var/run/couchdb']:
    ensure  => directory,
  }

  file { '/usr/local/etc/couchdb/local.ini':
    ensure  => file,
    mode    => '0600',
    content => template('couchdb/usr/local/etc/couchdb/local.ini.erb'),
    notify  => Service['couchdb'];
  }

  file { '/etc/init.d/couchdb':
    ensure  => link,
    target  => '/usr/local/etc/init.d/couchdb',
  }

  file { ['/usr/local/etc/logrotate.d/couchdb', '/etc/logrotate.d/couchdb']:
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0600',
    content => template('couchdb/usr/local/etc/logrotate.d/couchdb.erb'),
  }

  file { '/etc/security/limits.d/100-couchdb.conf':
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0600',
    content => template('couchdb/etc/security/limits.d/100-couchdb.conf.erb'),
  }

  unless $couchdb::couchdb_master_ip == undef{
    host { $couchdb::couchdb_master_hostname:
      ip => $couchdb::couchdb_master_ip
    }
  }
    
  file { '/usr/local/sbin/couchdb_setup.py':
    ensure  => file,
    owner   => 'root',
    group   => 'root',
    mode    => '0755',
    content => template('couchdb/tmp/couchdb_setup.py.erb'),
  }

  file { '/usr/local/sbin/database_replication.py':
    ensure => file,
    owner => 'root',
    group => 'root',
    mode  => '0755',
    content => template('couchdb/tmp/database_replication.py.erb'),
  }

  file { "/etc/newrelic":
    ensure => "directory",
    owner  => "newrelic",
    group  => "newrelic",
    mode   => '0750',
    before  => File['/etc/newrelic/newrelic_plugin_agent.cfg'],
  }

  file { "/var/log/newrelic":
    ensure => "directory",
    owner  => "newrelic",
    group  => "newrelic",
    mode   => '0750',
  }

  file { "/var/run/newrelic":
    ensure => "directory",
    owner  => "newrelic",
    group  => "newrelic",
    mode   => '0750',
  }

  file { '/etc/newrelic/newrelic_plugin_agent.cfg':
    ensure => file,
    owner => 'newrelic',
    group => 'newrelic',
    mode  => '0755',
    content => template('couchdb/etc/newrelic/newrelic_plugin_agent.cfg.erb'),
  }

  file {'/tmp/rc.local':
    ensure => file,
    owner => 'root',
    group => 'root',
    mode => '0755',
    content => template('couchdb/tmp/rc.local.erb'),
  }



  # remove build folder
  case $couchdb::rm_build_folder {
    true: {
      notice('remove build folder')
      exec { 'remove-build-folder':
        cwd     => $couchdb::cwd,
        command => "/usr/bin/rm -rf ${couchdb::cwd}/${couchdb::foldername}",
        require => Exec['make-install'],
      }
    }
    default: {}
  }
}