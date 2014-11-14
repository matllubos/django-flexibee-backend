import requests
import json
import logging
import datetime
import string
import random

from django.conf import settings
from django.db.models.fields import FieldDoesNotExist
from django.template.defaultfilters import slugify
from django.utils.http import urlquote
from django.core.exceptions import ImproperlyConfigured

from bs4 import BeautifulSoup

from flexibee_backend.db.backends.rest.exceptions import SyncException
from flexibee_backend import config
from flexibee_backend.db.backends.rest.compiler import SQLDataCompiler
from flexibee_backend.db.backends.rest.connection import decimal_default
from flexibee_backend.ssl import sslrequests


class FlexibeeAdminConnector(object):
    COMPANY_URL = 'https://%(hostname)s/c/%(db_name)s'
    LIST_URL = 'https://%(hostname)s/c.json'
    CREATE_URL = 'https://%(hostname)s/admin/zalozeni-firmy.json'
    UPDATE_URL = 'https://%(hostname)s/c/%(db_name)s/nastaveni/1'
    DELETE_URL = 'https://%(hostname)s:7000/admin/batch'
    BACKUP_URL = 'https://%(hostname)s/c/%(db_name)s/backup'
    RESTORE_URL = 'https://%(hostname)s/c/%(db_name)s/restore'

    logger = logging.getLogger('flexibee-backend')

    def __init__(self, testing=None):
        self.testing = testing if testing is not None else config.TESTING
        db_settings = settings.DATABASES.get(config.FLEXIBEE_BACKEND_NAME)
        self.hostname = db_settings.get('HOSTNAME')
        self.username = db_settings.get('USER')
        self.password = db_settings.get('PASSWORD')

    def _get_value_internal_type(self, instance, field_name, value):
        try:
            return instance._meta.get_field(field_name).get_internal_type()
        except FieldDoesNotExist:
            if isinstance(value, bool):
                return 'BooleanField'
            elif isinstance(value, datetime.date):
                return 'DateField'
            else:
                return 'CharField'

    def _get_field_value(self, instance, field_name):
        if '__' in field_name:
            current_field_name, next_field_name = field_name.split('__', 1)
            return self._get_field_value(getattr(instance, current_field_name), next_field_name)
        else:
            data_compiler = SQLDataCompiler()
            value = getattr(instance, field_name)

            if hasattr(value, '__call__'):
                value = value()

            return data_compiler.convert_value_for_db(self._get_value_internal_type(instance, field_name, value),
                                                      value)

    def create_company(self, company):
        if self.testing:
            return slugify(''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(10)))
        else:
            url = self.CREATE_URL % {'hostname': self.hostname}
            data = {'country': 'CZ'}
            for from_name, to_name in company._flexibee_meta.create_mapping.items():
                data[to_name] = self._get_field_value(company, from_name)

            query_string = '&'.join(['%s=%s' % (key, urlquote(val)) for key, val in data.items()])

            url += '?%s' % query_string
            r = requests.put(url, auth=(self.username, self.password))
            if r.status_code == 201:
                company.flexibee_db_name = r.headers['location'].split('/')[-1]
            else:
                raise SyncException(r, url, r.json().get('winstrom').get('message'))

    def update_company(self, company):
        if not self.testing:
            url = self.UPDATE_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
            data = {}
            for from_name, to_name in company._flexibee_meta.update_mapping.items():
                data[to_name] = self._get_field_value(company, from_name)
            data = {'winstrom': {'nastaveni': data}}
            headers = {'Accept': 'application/json'}

            self.logger.info('Send PUT to %s' % url)
            r = requests.put(url, data=json.dumps(data, default=decimal_default), headers=headers, auth=(self.username, self.password))
            if r.status_code != 201:
                raise SyncException(r, url, r.json().get('winstrom').get('message'))

    def delete_company(self, company):
        if not config.FLEXIBEE_ADMIN_CERTIFICATE:
            raise ImproperlyConfigured('FLEXIBEE_ADMIN_CERTIFICATE must be set for support of deleting company')

        batch = '''<flexibee-batch id="abc-123">
                       <company action="delete">
                            <id>%s</id>
                       </company>
                   </flexibee-batch>''' % company.flexibee_db_name

        url = self.DELETE_URL % {'hostname': self.hostname}
        r = sslrequests.put(url, data=batch, cert=config.FLEXIBEE_ADMIN_CERTIFICATE)
        soup = BeautifulSoup(r.content)
        if r.status_code != 200 or not soup.status or soup.status.string == 'FAILED':
            raise SyncException(r, url)

    def backup_company(self, company, file_handler):
        url = self.BACKUP_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
        r = requests.get(url, auth=(self.username, self.password))
        if r.status_code != 200:
            raise SyncException(r, url, msg='Failed Backup')

        size = 0
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                file_handler.receive_data_chunk(chunk, size)
                size += len(chunk)

        return file_handler.file_complete(size)

    def restore_company(self, company, backup_file):
        url = self.RESTORE_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
        r = requests.put(url, data=backup_file, auth=(self.username, self.password))
        if r.status_code != 200:
            raise SyncException(r, url, msg='Failed Backup')

    def exists_company(self, company):
        url = self.COMPANY_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
        r = requests.get(url, auth=(self.username, self.password))
        return r.status_code == 200

admin_connector = FlexibeeAdminConnector()
