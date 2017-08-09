# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, you can obtain one at http://mozilla.org/MPL/2.0/.
import os

import boto3
import constance
import requests
from django.conf import settings
from django.utils import timezone


class Provisioner:
    """
    A base provisioner to be used by specific cases of calling out to AWS EMR.
    This is currently storing some common code and simplifies testing.

    Subclasses need to override there class attributes:

    - :attr:`log_dir`
    - :attr:`name_component`
    """
    #: The name of the log directory, e.g. 'jobs'.
    log_dir = None
    #: The name to be used in the identifier, e.g. 'job'.
    name_component = None

    def __init__(self):
        self.config = settings.AWS_CONFIG
        self.spark_emr_configuration_url = (
            'https://s3-%s.amazonaws.com/%s/configuration/configuration.json' %
            (self.config['AWS_REGION'], constance.config.AWS_SPARK_EMR_BUCKET)
        )
        # The S3 script URI of the bootstrap script.
        self.script_uri = (
            's3://%s/bootstrap/telemetry.sh' % constance.config.AWS_SPARK_EMR_BUCKET
        )
        # A Boto3 EMR client instance.
        self.emr = boto3.client(
            'emr',
            region_name=self.config['AWS_REGION'],
        )
        # A Boto3 S3 client instance.
        self.s3 = boto3.client(
            's3',
            region_name=self.config['AWS_REGION'],
        )
        # A requests session instance.
        self.session = requests.session()

        # The S3 URI of the script-runner jar file.
        self.jar_uri = (
            's3://%s.elasticmapreduce/libs/script-runner/script-runner.jar' %
            self.config['AWS_REGION']
        )

        # The currently running environment, e.g. "stage" or "prod".
        self.environment = (
            getattr(settings, 'CONFIGURATION', None) or
            os.environ.get('DJANGO_CONFIGURATION', 'unknown')
        ).rsplit('.', 1)[-1].lower()

    def spark_emr_configuration(self):
        """
        Fetch the Spark EMR configuration data to be passed as the
        Configurations parameter to EMR API endpoints.

        We store this in S3 to be able to share it between various
        Telemetry services.
        """
        response = self.session.get(self.spark_emr_configuration_url)
        response.raise_for_status()
        return response.json()

    def job_flow_params(self, user_username, user_email, identifier, emr_release, size):
        """
        Given the parameters returns the basic parameters for EMR job flows,
        and handles for example the decision whether to use spot instances
        or not.
        """
        # setup instance groups using spot market for slaves
        instance_groups = [
            {
                'Name': 'Master',
                'Market': 'ON_DEMAND',
                'InstanceRole': 'MASTER',
                'InstanceType': self.config['MASTER_INSTANCE_TYPE'],
                'InstanceCount': 1
            }
        ]

        if size > 1:
            core_group = {
                'Name': 'Worker Instances',
                'InstanceRole': 'CORE',
                'InstanceType': self.config['WORKER_INSTANCE_TYPE'],
                'InstanceCount': size,
            }
            if constance.config.AWS_USE_SPOT_INSTANCES:
                core_group.update({
                    'Market': 'SPOT',
                    'BidPrice': str(constance.config.AWS_SPOT_BID_CORE),
                })
            else:
                core_group['Market'] = 'ON_DEMAND'

            instance_groups.append(core_group)

        now = timezone.now().isoformat()

        log_uri = (
            's3://%s/%s/%s/%s' %
            (self.config['LOG_BUCKET'], self.log_dir, identifier, now)
        )

        # atmo-<environment>-<component>-<username>-<identifier>
        # e.g. atmo-stage-job-jleidel-unruffled-nightingale-9993
        name = '-'.join([
            'atmo',
            self.environment,
            self.name_component,
            user_username,
            identifier,
        ])
        return {
            'Name': name,
            'LogUri': log_uri,
            'ReleaseLabel': 'emr-%s' % emr_release,
            'Configurations': self.spark_emr_configuration(),
            'Instances': {
                'InstanceGroups': instance_groups,
                'Ec2KeyName': self.config['EC2_KEY_NAME'],
                'KeepJobFlowAliveWhenNoSteps': False,
            },
            'JobFlowRole': constance.config.AWS_SPARK_INSTANCE_PROFILE,
            'ServiceRole': 'EMR_DefaultRole',
            'Applications': [
                {'Name': 'Spark'},
                {'Name': 'Hive'},
                {'Name': 'Zeppelin'}
            ],
            'Tags': [
                {'Key': 'Owner', 'Value': user_email},
                {'Key': 'Name', 'Value': identifier},
                {'Key': 'Environment', 'Value': self.environment},
                {'Key': 'Application', 'Value': self.config['INSTANCE_APP_TAG']},
                {'Key': 'App', 'Value': self.config['ACCOUNTING_APP_TAG']},
                {'Key': 'Type', 'Value': self.config['ACCOUNTING_TYPE_TAG']},
            ],
            'VisibleToAllUsers': True,
        }
