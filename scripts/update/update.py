"""
Deployment for Mozillians in production.

Requires commander (https://github.com/oremj/commander) which is installed on
the systems that need it.
"""

import os
import sys
import urllib
import urllib2

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from commander.deploy import task, hostgroups

import commander_settings as settings


NEW_RELIC_URL = 'https://rpm.newrelic.com/deployments.xml'


@task
def update_code(ctx, tag):
    with ctx.lcd(settings.SRC_DIR):
        ctx.local("git fetch")
        ctx.local("git checkout -f %s" % tag)
        ctx.local("git submodule sync")
        ctx.local("git submodule update --init --recursive")
        ctx.local("find . -type f -name '.gitignore' -or -name '*.pyc' -delete")
        ctx.local('git clean -xdff "vendor-local/"')


@task
def update_locales(ctx):
    with ctx.lcd(os.path.join(settings.SRC_DIR, 'locale')):
        ctx.local('find . -name "*.mo" -delete')
        ctx.local("svn up")
        ctx.local("./compile.sh .")


@task
def update_assets(ctx):
    with ctx.lcd(settings.SRC_DIR):
        ctx.local("LANG=en_US.UTF-8 python2.6 manage.py collectstatic --noinput")
        ctx.local("LANG=en_US.UTF-8 python2.6 manage.py compress_jingo")
        ctx.local("LANG=en_US.UTF-8 python2.6 manage.py update_product_details")


@task
def database(ctx):
    with ctx.lcd(settings.SRC_DIR):
        ctx.local("python2.6 manage.py syncdb")                             # South (new)
        ctx.local("python2.6 manage.py migrate")                            # South (new)

@task
def update_es_indexes(ctx):
    with ctx.lcd(settings.SRC_DIR):
        ctx.local("python2.6 manage.py cron index_all_profiles &")

@task
def validate_fun_facts(ctx):
    with ctx.lcd(settings.SRC_DIR):
        ctx.local("python2.6 manage.py cron validate_fun_facts")


#@task
#def install_cron(ctx):
#    with ctx.lcd(settings.SRC_DIR):
#        ctx.local("python2.6 ./scripts/crontab/gen-crons.py -k %s -u apache > /etc/cron.d/.%s" %
#                  (settings.WWW_DIR, settings.CRON_NAME))
#        ctx.local("mv /etc/cron.d/.%s /etc/cron.d/%s" % (settings.CRON_NAME, settings.CRON_NAME))


@task
def checkin_changes(ctx):
    ctx.local(settings.DEPLOY_SCRIPT)


@hostgroups(settings.WEB_HOSTGROUP, remote_kwargs={'ssh_key': settings.SSH_KEY})
def deploy_app(ctx):
    ctx.remote(settings.REMOTE_UPDATE_SCRIPT)
    ctx.remote("/bin/touch %s" % settings.REMOTE_WSGI)

@hostgroups(settings.WEB_HOSTGROUP, remote_kwargs={'ssh_key': settings.SSH_KEY})
def prime_app(ctx):
    for http_port in range(80, 82):
        ctx.remote("for i in {1..10}; do curl -so /dev/null -H 'Host: %s' -I http://localhost:%s/ & sleep 1; done" % (settings.REMOTE_HOSTNAME, http_port))

@hostgroups(settings.CELERY_HOSTGROUP, remote_kwargs={'ssh_key': settings.SSH_KEY})
def update_celery(ctx):
    ctx.remote(settings.REMOTE_UPDATE_SCRIPT)
    ctx.remote('/sbin/service %s restart' % settings.CELERY_SERVICE)


@task
def update_info(ctx, tag):
    with ctx.lcd(settings.SRC_DIR):
        ctx.local("date")
        ctx.local("git branch")
        ctx.local("git log -3")
        ctx.local("git status")
        ctx.local("git submodule status")
        ctx.local("python ./manage.py migrate --list")
        with ctx.lcd("locale"):
            ctx.local("svn info")
            ctx.local("svn status")

        ctx.local("git rev-parse HEAD > media/revision.txt")

        if settings.NEW_RELIC_API_KEY and settings.NEW_RELIC_APP_ID:
            print 'Post deploy event to NewRelic'
            data = urllib.urlencode(
                {'deployment[revision]': tag,
                 'deployment[app_id]': settings.NEW_RELIC_APP_ID})
            headers = {'x-api-key': settings.NEW_RELIC_API_KEY}
            try:
                request = urllib2.Request(NEW_RELIC_URL, data, headers)
                urllib2.urlopen(request)
            except urllib.URLError as exp:
                print 'Error notifing NewRelic: {0}'.format(exp)


@task
def pre_update(ctx, ref=settings.UPDATE_REF):
    update_code(ref)
    update_info(ref)


@task
def update(ctx):
    update_assets()
    update_locales()
    database()


@task
def deploy(ctx):
#    install_cron()
    checkin_changes()
    deploy_app()
    prime_app()
    update_celery()
    update_es_indexes()
    validate_fun_facts()


@task
def update_mozillians(ctx, tag):
    """Do typical mozillians update"""
    pre_update(tag)
    update()
