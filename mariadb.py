# coding: utf-8

import re
import socket
from fabkit import filer, env, sudo, api
from fablib.base import SimpleBase


class Mariadb(SimpleBase):
    def __init__(self):
        self.data_key = 'mariadb'
        self.data = {
            'port': 3306,
            'user_map': {},
            'phpmyadmin': {
                'enable': False
            }
        }

        self.services = {
            'CentOS .*': [
                'mariadb',
            ],
            'Ubuntu .*': [
                'mariadb'
            ]
        }

        self.packages = {
            'CentOS .*': [
                'MariaDB-server',
                'rsync',
            ],
            'Ubuntu .*': [
                'mariadb',
            ],
        }

    def init_after(self):
        for cluster in self.data.get('cluster_map', {}).values():
            if env.host in cluster['hosts']:
                self.data.update(cluster)
                break

        self.data['server_id'] = self.data['hosts'].index(env.host)
        self.data['auto_increment_offset'] = self.data['server_id'] + 1

        self.data['wsrep_node_address'] = socket.gethostbyname_ex(env.host)[2][0]
        wsrep_cluster_address = 'gcomm://' + ','.join(
            map(lambda host: socket.gethostbyname_ex(host)[2][0], self.data['hosts']))
        self.data['wsrep_cluster_address'] = wsrep_cluster_address

    def setup_prepare(self):
        if self.is_tag('package'):
            if env.node['package_manager'] == 'yum':
                filer.template('/etc/yum.repos.d/mariadb.repo')
            self.init_package_manager()
            self.install_packages()
        sudo('setenforce 0')

    def setup(self):
        data = self.init()

        if self.is_tag('conf'):
            if env.node['package_manager'] == 'yum':
                if filer.template('/etc/my.cnf.d/server.cnf', data=data):
                    self.handlers['restart_mariadb'] = True
            elif env.node['package_manager'] == 'apt':
                pass

        if self.is_tag('service'):
            if self.data['hosts'][0] == env.host:
                with api.warn_only():
                    result = sudo('systemctl status mariadb')
                    if result.return_code != 0:
                        sudo('galera_new_cluster')
                    else:
                        self.exec_handlers()
                self.enable_services().start_services()
            else:
                self.enable_services().start_services()
                self.exec_handlers()

        if self.is_tag('data'):
            # init root_password
            if not filer.exists('/root/.my.cnf'):
                root_password = data['root_password']
                if data['hosts'][0] == env.host:
                    if self.is_ubuntu():
                        sudo('mysqladmin password {0} -uroot -ptmppass'.format(root_password))
                    else:
                        sudo('mysqladmin password {0} -uroot'.format(root_password))
                filer.template('/root/.my.cnf', data={'root_password': root_password})

            if data['hosts'][0] == env.host:
                self.create_users()
                self.delete_default_users()
                self.create_databases()

    def sql(self, query):
        self.init()
        if self.is_ubuntu():
            return sudo('mysql -uroot '
                        '-p`grep ^password /root/.my.cnf | head -1 | awk \'{{print $3}}\'` '
                        '-e"{0}"'.format(query))
        else:
            return sudo('mysql -uroot '
                        '-e"{0}"'.format(query))

    def create_users(self):
        data = self.init()
        for user in data['user_map'].values():
            for db in user.get('dbs', ['*']):
                # if data['server_id'] == 0 and db != '*':
                #     self.sql('CREATE DATABASE IF NOT EXISTS {0};'.format(db))

                for src_host in user.get('src_hosts', ['localhost']):
                    query = 'GRANT {privileges} ON {table} TO \'{user}\'@\'{host}\' IDENTIFIED BY \'{password}\''.format(  # noqa
                        privileges=user.get('privileges', 'ALL PRIVILEGES'),
                        table='{0}.*'.format(db),
                        user=user['user'],
                        password=user['password'],
                        host=src_host,
                    )

                    self.sql(query)

    def delete_default_users(self):
        self.init()
        self.sql("delete from mysql.user where user='root' and host!='localhost'")
        self.sql("delete from mysql.user where user=''")

    def is_ubuntu(self):
        if re.match('Ubuntu.*', env.node['os']):
            return True
        return False

    def create_databases(self):
        data = self.init()
        for db in data['dbs']:
            self.sql('CREATE DATABASE IF NOT EXISTS {0} DEFAULT CHARACTER SET utf8;'.format(db))
