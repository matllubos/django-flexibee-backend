import requests
import json
import re

from django.db.utils import DatabaseError
from django.utils.encoding import force_text

class Connector(object):

    def __init__(self, username, password, hostname, port, company):
        self.username = username
        self.password = password
        self.hostname = hostname
        self.company = company
        self.port = port


class Filter(object):

    def __init__(self, field, op, value, negated):
        self.field = field
        self.op = op
        self.value = value
        self.negated = negated

    def __unicode__(self):
        filter_list = []
        if self.negated:
            filter_list.append('not')

        filter_list += [self.field, self.op, unicode(self.value)]
        return ' '.join(filter_list)


class RestQuery(object):

    URL = 'https://%(hostname)s/c/%(company)s/%(table_name)s%(extra)s.json?%(query_string)s'

    def __init__(self, connector, table_name, fields=[]):
        self.table_name = table_name
        self.connector = connector
        self.fields = fields
        self.query_strings = {'detail': 'custom:%s' % ','.join(self.fields)}
        self.order_fields = []
        self.filters = []

    def _is_request_for_one_object(self):
        return len(self.filters) == 1 and self.filters[0].field == 'id' and self.filters[0].op == '=' \
            and not self.filters[0].negated

    def _extra_filter(self):
        extra = ''
        if self._is_request_for_one_object():
            extra = '/%s' % self.filters[0].value
        else:
            filter_string = ' and '.join(['(%s)' % force_text(filter) for filter in self.filters])
            if filter_string:
                extra = '/(%s)' % filter_string
        return extra

    def get(self, extra_query_strings={}):
        query_strings = self.query_strings.copy()
        query_strings.update(extra_query_strings)

        query_strings_list = query_strings.items()

        for order_field in self.order_fields:
            query_strings_list.append(('order', order_field))

        query_strings = ['%s=%s' % (key, val) for key, val in query_strings_list]

        extra = self._extra_filter()

        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '&'.join(query_strings), 'extra': extra}

        print url
        r = requests.get(url, auth=(self.connector.username, self.connector.password))
        return r.json().get('winstrom')

    def count(self):
        query_strings = {'add-row-count':'true', 'detail':'custom:id'}
        return self.get(query_strings).get('@rowCount')

    def fetch(self, offset, base):
        query_strings = {'start':offset, 'limit': base or 0}
        return self.get(query_strings).get(self.table_name)

    def add_ordering(self, field_name, is_asc):
        self.order_fields.append('%s@%s' % (field_name, is_asc and 'A' or 'D'))

    def add_filter(self, field_name, op, db_value, negated):
        self.filters.append(Filter(field_name, op, db_value, negated))

    def insert(self, data):
        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '', 'extra': ''}

        data = {'winstrom': {self.table_name: data}}
        headers = {'Accept': 'application/json'}

        r = requests.put(url, data=json.dumps(data), headers=headers, auth=(self.connector.username, self.connector.password))

        if r.status_code == 200:
            return r.json().get('winstrom').get('results')[0].get('id')

        else:
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors')[0].get('message'))

    def update(self, data):

        if not self._is_request_for_one_object():
            changes_data = data
            data = []
            query_strings = {'detail':'custom:id'}
            for entity in self.get(query_strings).get(self.table_name):
                entity_value = changes_data.copy()
                entity_value['id'] = entity.get('id')
                data.append(entity_value)
            extra = ''
        else:
            extra = self._extra_filter()

        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '', 'extra': extra}
        data = {'winstrom': {self.table_name: data}}
        headers = {'Accept': 'application/json'}
        r = requests.put(url, data=json.dumps(data), headers=headers, auth=(self.connector.username,
                                                                            self.connector.password))
        if r.status_code == 201:
            return int(r.json().get('winstrom').get('stats').get('updated'))
        else:
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors'))

    def delete(self):
        data = []
        if not self._is_request_for_one_object():
            query_strings = {'detail':'custom:id'}
            for entity in self.get(query_strings).get(self.table_name):
                data.append({'id': entity.get('id')})
            extra = ''
        else:
            extra = self._extra_filter()

        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '', 'extra': extra}
        data = {'winstrom': {self.table_name: data}}
        headers = {'Accept': 'application/json'}
        r = requests.delete(url, data=json.dumps(data), headers=headers, auth=(self.connector.username,
                                                                            self.connector.password))

        if r.status_code not in [200, 404]:
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors'))

