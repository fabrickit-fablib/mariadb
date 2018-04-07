# coding: utf-8

from fabkit import task, parallel
from fablib.mariadb import Mariadb


@task
@parallel
def setup0_prepare():
    mariadb = Mariadb()
    mariadb.setup_prepare()


@task
def setup1():
    mariadb = Mariadb()
    mariadb.setup()
