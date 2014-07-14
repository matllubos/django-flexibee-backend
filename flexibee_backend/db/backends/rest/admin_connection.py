import requests
import json
import logging

from django.conf import settings

from flexibee_backend.db.backends.rest.exceptions import SyncException
from flexibee_backend import config
from flexibee_backend.db.backends.rest.compiler import SQLDataCompiler
from flexibee_backend.db.backends.rest.connection import decimal_default


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

    def create_company(self, company):
        url = self.CREATE_URL % {'hostname': self.hostname}
        data = {}
        data_compiler = SQLDataCompiler()

        for from_name, to_name in company.FlexibeeMeta.create_mapping.items():
            data[to_name] = data_compiler.convert_value_for_db(company._meta.get_field(from_name).get_internal_type(),
                                                               getattr(company, from_name))

        query_string = '&'.join(['%s=%s' % (key, val) for key, val in data.items()])

        url += '?%s' % query_string
        r = requests.post(url, auth=(self.username, self.password))
        if r.status_code == 201:
            company.flexibee_db_name = r.headers['location'].split('/')[-1]
        else:
            raise SyncException(r.json().get('winstrom').get('message'), r)

    def update_company(self, company):
        url = self.UPDATE_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
        data = {}
        data_compiler = SQLDataCompiler()

        for from_name, to_name in company.FlexibeeMeta.update_mapping.items():
            data[to_name] = data_compiler.convert_value_for_db(company._meta.get_field(from_name).get_internal_type(),
                                                               getattr(company, from_name))
        data = {'winstrom': {'nastaveni': data}}
        headers = {'Accept': 'application/json'}

        self.logger.info('Send PUT to %s' % url)
        r = requests.put(url, data=json.dumps(data, default=decimal_default), headers=headers, auth=(self.username, self.password))


admin_connector = FlexibeeAdminConnector()
