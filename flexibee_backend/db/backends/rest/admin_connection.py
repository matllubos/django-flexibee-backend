import os
import datetime
import string
import random
import mimetypes

from dateutil.parser import parse

from django.conf import settings
from django.db.models.fields import FieldDoesNotExist
from django.template.defaultfilters import slugify
from django.utils.http import urlquote
from django.core.exceptions import ImproperlyConfigured
from django.utils.timezone import utc
from django.utils.encoding import force_text

from bs4 import BeautifulSoup

from flexibee_backend.db.backends.rest.exceptions import FlexibeeResponseError
from flexibee_backend import config
from flexibee_backend.db.backends.rest.compiler import SQLDataCompiler
from flexibee_backend.db.backends.rest.connection import BaseConnector
from flexibee_backend.ssl import sslrequests


class FlexibeeAdminConnector(BaseConnector):
    COMPANY_URL = 'https://%(hostname)s/c/%(db_name)s'
    LIST_URL = 'https://%(hostname)s/c.json'
    CREATE_URL = 'https://%(hostname)s/admin/zalozeni-firmy.json'
    UPDATE_URL = 'https://%(hostname)s/c/%(db_name)s/nastaveni/1'
    DELETE_URL = 'https://%(hostname)s:7000/admin/batch'
    BACKUP_URL = 'https://%(hostname)s/c/%(db_name)s/backup'
    RESTORE_URL = 'https://%(hostname)s/c/%(db_name)s/restore'

    def __init__(self, testing=None):
        db_settings = settings.DATABASES.get(config.FLEXIBEE_BACKEND_NAME)
        super(FlexibeeAdminConnector, self).__init__(
            db_settings.get('USER'), db_settings.get('PASSWORD'), db_settings.get('HOSTNAME')
        )
        self.testing = testing if testing is not None else config.TESTING
        self._exists_company_cache = {}

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

    def _get_file_last_update(self, url):
        url = url + '.json?detail=custom:lastUpdate'
        r = self.http_get(url)
        files = self._deserialize(url, r, 'priloha')
        if len(files) != 1 or 'lastUpdate' not in files[0]:
            raise FlexibeeResponseError(
                r.url, r, 'Is not possible upload new company file, because returned data from flexibee are wrong'
            )
        return parse(files[0].get('lastUpdate')).replace(tzinfo=utc)

    def _delete_old_file(self, url):
        r = self.http_delete(url)
        if r.status_code not in (200, 404):
            raise FlexibeeResponseError(url, r, 'Is not possible remove old company file')

    def _upload_file(self, company, flexibee_filename, file):
        url = (self.UPDATE_URL + '/%(filename)s.json') % {
            'hostname': self.hostname, 'db_name': company.flexibee_db_name, 'filename': flexibee_filename
        }
        r = self.http_get(url)
        if r.status_code not in [200, 404]:
            raise FlexibeeResponseError(url, r, 'Is not possible upload new company file')

        flexibee_file_exists = r.status_code == 200
        if flexibee_file_exists:
            flexibee_file_last_update = self._get_file_last_update(r.url)
        else:
            flexibee_file_last_update = datetime.datetime.min.replace(tzinfo=utc)
        file_last_update = datetime.datetime.fromtimestamp(os.stat(file.path).st_mtime).replace(tzinfo=utc)
        if file_last_update > flexibee_file_last_update:
            if flexibee_file_exists:
                self._delete_old_file(url)
            content_type, _ = mimetypes.guess_type(force_text(file), strict=True)
            r = self.http_put(url, file.file, {'Content-Type': content_type}, False)
            if r.status_code != 201:
                raise FlexibeeResponseError(url, r, 'Is not possible upload new company file')

    def _upload_files(self, company):
        for field_name, flexibee_file_name in zip(
                (company._flexibee_meta.logo_field, company._flexibee_meta.signature_field),
                ('logo', 'podpis-razitko')):
            if field_name and getattr(company, field_name):
                self._upload_file(company, flexibee_file_name, getattr(company, field_name))

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
            r = self.http_put(url)
            if r.status_code == 201:
                company.flexibee_db_name = r.headers['location'].split('/')[-1]
            else:
                raise FlexibeeResponseError(url, r, 'Company creation error')

    def update_company(self, company):
        if not self.testing:
            url = self.UPDATE_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
            data = {}
            for from_name, to_name in company._flexibee_meta.update_mapping.items():
                data[to_name] = self._get_field_value(company, from_name)
            data = {'nastaveni': data}
            self.logger.info('Send PUT to %s' % url)
            r = self.http_put(url, data, self.JSON_HEADER)
            if r.status_code != 201:
                raise FlexibeeResponseError(url, r, 'Company synchronization error')
            self._upload_files(company)

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
            raise FlexibeeResponseError(url, r, 'Company deletion error')

    def backup_company(self, company, file_handler):
        url = self.BACKUP_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
        r = self.http_get(url)
        if r.status_code != 200:
            raise FlexibeeResponseError(url, r, 'Company backup error')

        size = 0
        for chunk in r.iter_content(chunk_size=1024):
            if chunk:
                file_handler.receive_data_chunk(chunk, size)
                size += len(chunk)

        return file_handler.file_complete(size)

    def restore_company(self, company, backup_file):
        url = self.RESTORE_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
        r = self.http_put(url, backup_file, serialize=False)
        if r.status_code != 200:
            raise FlexibeeResponseError(url, r, 'Company restore error')

    def exists_company(self, company):
        if not company.flexibee_db_name:
            return False

        if self.testing:
            return True

        if company.flexibee_db_name not in self._exists_company_cache:
            url = self.COMPANY_URL % {'hostname': self.hostname, 'db_name': company.flexibee_db_name}
            r = self.http_get(url)
            self._exists_company_cache[company.flexibee_db_name] = r.status_code == 200

        return self._exists_company_cache[company.flexibee_db_name]

    def reset(self):
        self._exists_company_cache = {}

admin_connector = FlexibeeAdminConnector()
