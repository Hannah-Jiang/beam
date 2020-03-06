#
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""A script to pull licenses for Python.
"""
import json
import os
import shutil
import subprocess
import sys
import wget
import yaml

from tenacity import retry
from tenacity import stop_after_attempt


def run_bash_command(command):
  process = subprocess.Popen(
      command.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  result, error = process.communicate()
  if error:
    raise RuntimeError(
        'Error occurred when running a bash command.',
        'command: {command}, error: {error}'.format(
            command=command, error=error.decode('utf-8')),
    )
  return result.decode('utf-8')


def run_pip_licenses():
  command = 'pip-licenses --with-license-file --format=json'
  dependencies = run_bash_command(command)
  return json.loads(dependencies)


@retry(stop=stop_after_attempt(3))
def copy_license_files(dep):
  source_license_file = dep['LicenseFile']
  if source_license_file.lower() == 'unknown':
    return False
  name = dep['Name'].lower()
  dest_dir = '/'.join([license_dir, name])
  try:
    os.mkdir(dest_dir)
    shutil.copy(source_license_file, dest_dir + '/LICENSE')
    print(
        'Successfully pulled license for {dep} with pip-licenses.'.format(
            dep=name))
    return True
  except Exception as e:
    print(e)
    return False


@retry(stop=stop_after_attempt(3))
def pull_from_url(dep, configs):
  '''
  :param dep: name of a dependency
  :param configs: a dict from dep_urls_py.yaml
  :return: boolean

  It downloads files form urls to a temp directory first in order to avoid
  to deal with any temp files. It helps keep clean final directory.
  '''
  if dep in configs.keys():
    config = configs[dep]
    dest_dir = '/'.join([license_dir, dep])
    cur_temp_dir = 'temp_license_' + dep
    os.mkdir(cur_temp_dir)

    try:
      if config['license'] == 'skip':
        print('Skip pulling license for ', dep)
      elif config['license'] == 'manual':
        shutil.copyfile(
            '/tmp/manual_licenses/{dep}/LICENSE'.format(dep=dep),
            cur_temp_dir + '/LICENSE')
        print(
            'Successfully copied license for {dep} from manual_licenses/{dep}/'
            'LICENSE.'.format(dep=dep))
      else:  # pull from url
        wget.download(config['license'], cur_temp_dir + '/LICENSE')
        print(
            'Successfully pulled license for {dep} from internet.'.format(
                dep=dep))

      # notice is optional.
      if 'notice' in config:
        wget.download(config['notice'], cur_temp_dir + '/NOTICE')
      # copy from temp dir to final dir only when either file is available.
      if os.listdir(cur_temp_dir):
        shutil.copytree(cur_temp_dir, dest_dir)
      result = True
    except Exception as e:
      print(
          'Error occurred when pull license for {dep} from {url}. \n'
          'Error: {error}'.format(dep=dep, url=config, error=e.decode('utf-8')))
      result = False
    finally:
      shutil.rmtree(cur_temp_dir)
      return result
  else:
    return False


if __name__ == "__main__":
  # the script is executed within DockerFile.
  license_dir = '/opt/apache/beam/third_party_licenses'
  os.makedirs(license_dir)
  no_licenses = []

  with open('/tmp/dep_urls_py.yaml') as file:
    dep_config = yaml.full_load(file)

  dependencies = run_pip_licenses()
  # add licenses for pip installed packages.
  # try to pull licenses with pip-licenses tool first, if no license pulled,
  # then pull from URLs.
  for dep in dependencies:
    if not (copy_license_files(dep) or
            pull_from_url(dep['Name'].lower(), dep_config['pip_dependencies'])):
      no_licenses.append(dep['Name'].lower())

  if no_licenses:
    py_ver = '%d.%d' % (sys.version_info[0], sys.version_info[1])
    how_to = 'These licenses were not able to be pulled automatically. ' \
             'Please search code source of the dependencies on the internet ' \
             'and add urls to RAW license file at sdks/python/container/' \
             'license_scripts/dep_urls_py.yaml for each missing license ' \
             'and rerun the test. If no such urls can be found, you need ' \
             'to manually add LICENSE and NOTICE (if possible) files at ' \
             'sdks/python/container/license_scripts/manual_licenses/{dep}/ ' \
             'and add entries to sdks/python/container/license_scripts/' \
             'dep_urls_py.yaml.'
    raise RuntimeError(
        'Some dependencies are missing licenses at python{py_ver} environment. '
        '{license_list} \n {how_to}'.format(
            py_ver=py_ver, license_list=no_licenses, how_to=how_to))
