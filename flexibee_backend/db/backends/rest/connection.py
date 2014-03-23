import requests
import json

from django.db.utils import DatabaseError
from django.utils.encoding import force_text, iri_to_uri
from django.core.cache import cache


class Connector(object):

    def __init__(self, username, password, hostname, port, company):
        self.username = username
        self.password = password
        self.hostname = hostname
        self.company = company
        self.port = port

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass

    def read(self, url):
        r = requests.get(url, auth=(self.username, self.password))
        print url
        return r.json().get('winstrom')

    def write(self, data, url):
        pass


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


class CachedEntity(object):

    def __init__(self, entity, fields):
        self.entity = entity
        self.fields = fields


class RestCache(object):

    def __init__(self, table_name, fields):
        self.table_name = table_name
        self.fields = fields

    def _get_entity_cache_key(self, pk):
        return '%s__%s' % (self.table_name, pk)

    def cache_entity(self, entity):
        if 'id' in entity:
            key = self._get_entity_cache_key(entity.get('id'))
            cache.set(key, CachedEntity(entity, self.fields), 30)
            return key

    def get_entity(self, pk):
        key = self._get_entity_cache_key(pk)

        cache_entity = cache.get(key)
        if cache_entity and set(self.fields).issubset(set(cache_entity.fields)):
            return cache_entity.entity

    def del_entity(self, pk):
        key = self._get_entity_cache_key(pk)
        cache.delete(key)

    def cache_url(self, data, url):
        pk_list = []
        cache_entities = True

        data = data.copy()

        for entity in data.get(self.table_name):
            pk = entity.get('id')
            if not pk:
                cache_entities = False
            self.cache_entity(entity)
            pk_list.append(pk)

        data[self.table_name] = pk_list

        if cache_entities:
            cache.set(iri_to_uri(url), data, 30)

    def get_url(self, url):
        url_data = cache.get(iri_to_uri(url))

        if not url_data:
            return None

        entities = []
        for pk in url_data.get(self.table_name):
            entity = self.get_entity(pk)
            if not entity:
                cache.delete(iri_to_uri(url))
                return None
            entities.append(entity)

        url_data[self.table_name] = entities
        return url_data


class RestQuery(object):

    URL = 'https://%(hostname)s/c/%(company)s/%(table_name)s%(extra)s.json?%(query_string)s'

    def __init__(self, connector, table_name, fields=[]):
        self.table_name = table_name
        self.connector = connector
        self.fields = fields
        self.query_strings = {'detail': 'custom:%s' % ','.join(self.fields)}
        self.order_fields = []
        self.filters = []
        self.cache = RestCache(table_name, fields)

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

        data = self.cache.get_url(url)
        if data:
            return data

        data = self.connector.read(url)

        self.cache.cache_url(data, url)

        return data

    def count(self):
        query_strings = {'add-row-count':'true', 'detail':'custom:id'}

        if self._is_request_for_one_object():
            return len(self.get(query_strings).get(self.table_name))
        return self.get(query_strings).get('@rowCount')

    def fetch(self, offset, base):
        query_strings = {'start':offset, 'limit': base or 0}
        return self.get(query_strings).get(self.table_name)

    def add_ordering(self, field_name, is_asc):
        self.order_fields.append('%s@%s' % (field_name, is_asc and 'A' or 'D'))

    def add_filter(self, field_name, op, db_value, negated):
        self.filters.append(Filter(field_name, op, db_value, negated))

    def insert(self, data):
        print 'insert'
        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '', 'extra': ''}

        data = {'winstrom': {self.table_name: data}}
        headers = {'Accept': 'application/json'}

        r = requests.put(url, data=json.dumps(data), headers=headers, auth=(self.connector.username, self.connector.password))

        if r.status_code == 200:
            print r.json()
            return r.json().get('winstrom').get('results')[0].get('id')

        else:
            print r.json()
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors')[0].get('message'))

    def update(self, data):

        pk_list = []
        if not self._is_request_for_one_object():
            changes_data = data
            data = []
            query_strings = {'detail':'custom:id'}
            for entity in self.get(query_strings).get(self.table_name):
                entity_value = changes_data.copy()
                pk = entity.get('id')
                entity_value['id'] = entity.get('id')
                pk_list.append(pk)
                data.append(entity_value)
            extra = ''
        else:
            extra = self._extra_filter()
            pk_list.append(self.filters[0].value)


        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '', 'extra': extra}

        data = {'winstrom': {self.table_name: data}}
        headers = {'Accept': 'application/json'}
        r = requests.put(url, data=json.dumps(data), headers=headers, auth=(self.connector.username,
                                                                            self.connector.password))
        if r.status_code == 201:
            for pk in pk_list:
                self.cache.del_entity(pk)

            return int(r.json().get('winstrom').get('stats').get('updated'))
        else:
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors'))

    def delete(self):
        data = []
        pk_list = []
        if not self._is_request_for_one_object():
            query_strings = {'detail':'custom:id'}
            for entity in self.get(query_strings).get(self.table_name):
                pk = entity.get('id')
                data.append({'id': pk})
                pk_list.append(pk)
            extra = ''
        else:
            extra = self._extra_filter()
            pk_list.append(self.filters[0].value)

        url = self.URL % {'hostname': self.connector.hostname, 'port': self.connector.port,
                          'company': self.connector.company, 'table_name': self.table_name,
                          'query_string': '', 'extra': extra}
        data = {'winstrom': {self.table_name: data}}
        headers = {'Accept': 'application/json'}
        r = requests.delete(url, data=json.dumps(data), headers=headers, auth=(self.connector.username,
                                                                            self.connector.password))

        if r.status_code not in [200, 404]:
            for pk in pk_list:
                self.cache.del_entity(pk)
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors'))

