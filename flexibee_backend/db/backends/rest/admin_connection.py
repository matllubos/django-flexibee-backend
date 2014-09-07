import requests
import json
import logging
import datetime
import string
import random

from django.conf import settings
from django.db.models.fields import FieldDoesNotExist
from django.template.defaultfilters import slugify

from flexibee_backend.db.backends.rest.exceptions import SyncException
from flexibee_backend import config
from flexibee_backend.db.backends.rest.compiler import SQLDataCompiler
from flexibee_backend.db.backends.rest.connection import decimal_default
from django.utils.http import urlquote


class FlexibeeAdminConnector(object):
    LIST_URL = 'https://%(hostname)s/c.json'
    CREATE_URL = 'https://%(hostname)s/admin/zalozeni-firmy.json'
    UPDATE_URL = 'https://%(hostname)s/c/%(db_name)s/nastaveni/1'
    logger = logging.getLogger('flexibee-backend')

    def __init__(self):
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
        if config.TESTING:
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
                raise SyncException(r.json().get('winstrom').get('message'), r, url)

    def update_company(self, company):
        if not config.TESTING:
            url = self.UPDATE_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
            data = {}
            for from_name, to_name in company._flexibee_meta.update_mapping.items():
                data[to_name] = self._get_field_value(company, from_name)
            data = {'winstrom': {'nastaveni': data}}
            headers = {'Accept': 'application/json'}

            self.logger.info('Send PUT to %s' % url)
            r = requests.put(url, data=json.dumps(data, default=decimal_default), headers=headers, auth=(self.username, self.password))
            if r.status_code != 201:
                raise SyncException(r.json().get('winstrom').get('message'), r, url)

admin_connector = FlexibeeAdminConnector()
