#!/usr/bin/env python
import os
import sys
import urlparse
import requests
import subprocess

AUTH_USERNAME = 'getsentry-bot'
AUTH_TOKEN = os.environ['GITHUB_AUTH_TOKEN']
AUTH = (AUTH_USERNAME, AUTH_TOKEN)
TAG = os.environ.get('TRAVIS_TAG') or os.environ.get('BUILD_TAG')
TARGET = os.environ.get('TARGET')
BIN_TYPE = os.environ.get('BIN_TYPE', 'release')
REPO = 'getsentry/sentry-cli'


def format_tag(tag):
    if tag[-2:] == '.0':
        return tag[:-2]
    return tag


def log(message, *args):
    if args:
        message = message % args
    print >> sys.stderr, message


def api_request(method, path, **kwargs):
    url = urlparse.urljoin('https://api.github.com/', path.lstrip('/'))
    # default travis python does not have SNI
    return requests.request(method, url, auth=AUTH, verify=False, **kwargs)


def find_executable():
    if TARGET:
        path = os.path.join('target', TARGET, BIN_TYPE, 'sentry-cli')
        if os.path.isfile(path):
            return path
    path = os.path.join('target', BIN_TYPE, 'sentry-cli')
    if os.path.isfile(path):
        return path


def get_target_executable_name():
    p = subprocess.Popen(['uname', '-sm'], stdout=subprocess.PIPE)
    platform, arch = p.communicate()[0].strip().split(' ', 1)
    return 'sentry-cli-%s-%s' % (platform, arch)


def ensure_release():
    resp = api_request('POST', 'repos/%s/releases' % REPO, json={
        'tag_name': TAG,
        'name': 'sentry-cli %s' % format_tag(TAG),
    })
    if resp.status_code != 422:
        resp.raise_for_status()
        release = resp.json()
        log('Created new release %s' % release['id'])
        return release
    resp = api_request('GET', 'repos/%s/releases' % REPO)
    resp.raise_for_status()
    for release in resp.json():
        if release['tag_name'] == TAG:
            log('Found already existing release %s' % release['id'])
            return release
    raise RuntimeError('Could not find release %s. Too old?' % TAG)


def upload_asset(release, executable, target_name):
    resp = api_request('GET', release['assets_url'])
    resp.raise_for_status()
    for asset in resp.json():
        if asset['name'] == target_name:
            log('Already have release asset %s. Skipping' % target_name)
            return

    upload_url = release['upload_url'].split('{')[0]
    with open(executable, 'rb') as f:
        log('Creating new release asset %s.' % target_name)
        resp = api_request('POST', upload_url,
                           params={'name': target_name},
                           headers={'Content-Type': 'application/octet-stream'},
                           data=f)
        resp.raise_for_status()


def main():
    if not TAG:
        return log('No tag specified.  Doing nothing.')
    executable = find_executable()
    if executable is None:
        return log('Could not locate executable.  Doing nothing.')

    target_executable_name = get_target_executable_name()
    release = ensure_release()
    upload_asset(release, executable, target_executable_name)


if __name__ == '__main__':
    main()
