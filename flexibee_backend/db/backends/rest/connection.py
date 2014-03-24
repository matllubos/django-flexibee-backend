import requests
import json

from django.db.utils import DatabaseError
from django.utils.encoding import force_text
from django.utils.datastructures import SortedDict


class Connector(object):

    URL = 'https://%(hostname)s/c/%(db_name)s/%(table_name)s%(extra)s.json?%(query_string)s'

    def __init__(self, username, password, hostname, port):
        self.username = username
        self.password = password
        self.hostname = hostname
        self.port = port
        self.cache = {}
        self.waiting_writes = SortedDict()

    def _check_settings(self, db_name):
        if db_name is None:
            raise DatabaseError('For flexibee DB connector must be set company')

    def _is_request_for_one_object(self, filters):
        return len(filters) == 1 and filters[0].field == 'id' and filters[0].op == '=' and not filters[0].negated

    def _get_extra_filter(self, filters):
        extra = ''
        if self._is_request_for_one_object(filters):
            extra = '/%s' % filters[0].value
        else:
            filter_string = ' and '.join(['(%s)' % force_text(filter) for filter in filters])
            if filter_string:
                extra = '/(%s)' % filter_string
        return extra

    def _get_query_string(self, fields, relations, ordering, offset, base):
        query_string_list = [
                             ('detail', 'custom:%s' % ','.join(fields)),
        ]
        if relations:
            query_string_list.append(('relations', ','.join(relations)))

        for field in ordering:
            query_string_list.append(('order', field))

        query_string_list.append(('start', offset))
        query_string_list.append(('limit', base))
        query_string_list.append(('add-row-count', 'true'))

        return '&'.join(['%s=%s' % (key, val) for key, val in query_string_list])

    def _generate_key(self, filters, fields, relations, ordering, offset, base):
        filters_key = ','.join([unicode(filter) for filter in filters])
        fields_key = ','.join(fields)
        relations_key = ','.join(relations)
        ordering_key = ','.join(ordering)
        return '__'.join((filters_key, fields_key, relations_key, ordering_key, str(offset), str(base)))

    def _get_from_cache(self, db_name, table_name, filters, fields, relations, ordering, offset, base):
        if table_name in self.cache:
            table_cache = self.cache.get('__'.join((db_name, table_name)))
            key = self._generate_key(filters, fields, relations, ordering, offset, base)
            if key in table_cache:
                return table_cache.get(key)

    def _clear_table_cache(self, db_name, table_name):
        if table_name in self.cache:
            del self.cache['__'.join((db_name, table_name))]

    def _add_to_cache(self, db_name, table_name, filters, fields, relations, ordering, offset, base, data):
        table_cache = self.cache['__'.join((db_name, table_name))] = self.cache.get('__'.join((db_name, table_name)), {})
        key = self._generate_key(filters, fields, relations, ordering, offset, base)
        table_cache[key] = data

    def read(self, db_name, table_name, filters, fields, relations, ordering, offset, base):
        self._check_settings(db_name)

        filters = list(filters)
        fields = list(fields)
        relations = list(relations)
        ordering = list(ordering)

        filters.sort()
        fields.sort()
        ordering.sort()
        relations.sort()

        data = self._get_from_cache(db_name, table_name, filters, fields, relations, ordering, offset, base)
        if data:
            return data

        extra = self._get_extra_filter(filters)


        url = self.URL % {'hostname': self.hostname, 'port': self.port, 'db_name': db_name, 'table_name': table_name,
                          'query_string': self._get_query_string(fields, relations, ordering, offset, base), 'extra': extra}

        r = requests.get(url, auth=(self.username, self.password))
        data = r.json().get('winstrom')
        self._add_to_cache(db_name, table_name, filters, fields, relations, ordering, offset, base, data)
        return data

    def write(self, db_name, table_name, data):
        self._check_settings(db_name)

        url = self.URL % {'hostname': self.hostname, 'port': self.port, 'db_name': db_name,
                          'table_name': table_name, 'query_string': '', 'extra': ''}

        data = {'winstrom': {table_name: data}}
        headers = {'Accept': 'application/json'}

        r = requests.put(url, data=json.dumps(data), headers=headers, auth=(self.username, self.password))

        if r.status_code in [200, 201]:
            self._clear_table_cache(db_name, table_name)
            return True, r.json().get('winstrom')
        else:
            raise False, r.json().get('winstrom')

    def delete(self, db_name, table_name, data):
        self._check_settings(db_name)

        url = self.URL % {'hostname': self.hostname, 'port': self.port, 'db_name': db_name,
                          'table_name': table_name, 'query_string': '', 'extra': ''}
        data = {'winstrom': {table_name: data}}
        headers = {'Accept': 'application/json'}
        r = requests.delete(url, data=json.dumps(data), headers=headers, auth=(self.username,
                                                                            self.password))

        self._clear_table_cache(db_name, table_name)
        if r.status_code not in [200, 404]:
            raise DatabaseError(r.json().get('winstrom').get('results')[0].get('errors'))


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

    def __cmp__(self, other):
        return cmp(unicode(self), unicode(self))


class CachedEntity(object):

    def __init__(self, entity, fields):
        self.entity = entity
        self.fields = fields


class RestQuery(object):

    URL = 'https://%(hostname)s/c/%(company)s/%(table_name)s%(extra)s.json?%(query_string)s'

    def __init__(self, connector, table_name, fields=[], relations=[], via_table_name=None, via_relation_name=None,
                 via_fk_name=None):
        self.table_name = table_name
        self.connector = connector
        self.fields = fields
        self.query_strings = {'detail': 'custom:%s' % ','.join(self.fields)}
        self.order_fields = []
        self.filters = []
        self.relations = []
        self.db_name = None

        self.via_table_name = via_table_name
        self.via_relation_name = via_relation_name
        self.via_fk_name = via_fk_name

    def _extra_filter(self):
        extra = ''
        if self._is_request_for_one_object():
            extra = '/%s' % self.filters[0].value
        else:
            filter_string = ' and '.join(['(%s)' % force_text(filter) for filter in self.filters])
            if filter_string:
                extra = '/(%s)' % filter_string
        return extra

    def get(self, offset=0, base=0, extra_fields=[]):
        fields = list(self.fields)
        fields += extra_fields
        return self.connector.read(self.db_name, self.table_name, self.filters, fields, self.relations, self.order_fields, offset, base)

    def count(self):
        data = self.connector.read(self.db_name, self.table_name, self.filters, ['id'], self.relations, self.order_fields, 0, 0)
        if self.connector._is_request_for_one_object(self.filters):
            return len(data.get(self.table_name))
        return data.get('@rowCount')

    def fetch(self, offset, base):
        return self.get(offset, base or 0).get(self.table_name)

    def add_ordering(self, field_name, is_asc):
        self.order_fields.append('%s@%s' % (field_name, is_asc and 'A' or 'D'))

    def set_db_name(self, db_name):
        self.db_name = db_name

    def add_filter(self, field_name, op, db_value, negated):
        self.filters.append(Filter(field_name, op, db_value, negated))

    def add_relation(self, relation_name):
        self.relations.append(relation_name)

    def _is_via(self):
        return self.via_table_name and self.via_relation_name and self.via_fk_name

    def insert(self, data):
        if self._is_via():
            self._store_via(data)
        else:
            created, output = self.connector.write(self.db_name, self.table_name, data)
            if created:
                return output.get('results')[0].get('id')
            else:
                raise DatabaseError(output.get('results')[0].get('errors')[0].get('message'))

    def _store_via(self, data):
        for obj_data in data:
            store_view_db_query = RestQuery(self.connector, self.via_table_name, ['id'],
                                            [self.via_relation_name])
            store_view_db_query.set_db_name(self.db_name)
            store_view_db_query.add_filter('id', '=', obj_data.get(self.via_fk_name), False)
            via_data = {'id': str(obj_data.get(self.via_fk_name))}
            via_data[self.via_relation_name] = [obj_data]
            store_view_db_query.update(via_data)

    def _delete_via(self, data):
        for obj_data in data:
            store_view_db_query = RestQuery(self.connector, self.via_table_name, ['id'],
                                            [self.via_relation_name])
            store_view_db_query.set_db_name(self.db_name)
            store_view_db_query.add_filter('id', '=', obj_data.get(self.via_fk_name), False)
            via_data = store_view_db_query.fetch(0, 0)[0]
            db_related_objs = via_data[self.via_relation_name]

            via_data[self.via_relation_name] = []
            for relation_obj in db_related_objs:
                if relation_obj.get('id') != str(obj_data.get('id')):
                    via_data[self.via_relation_name].append({'id': relation_obj.get('id')})
            via_data['%s@removeAll' % self.via_relation_name] = 'true'
            store_view_db_query.update(via_data)

    def update(self, data):
        updated_data = data
        data = []
        if not self.connector._is_request_for_one_object(self.filters):
            for entity in self.get().get(self.table_name):
                entity_value = updated_data.copy()
                pk = entity.get('id')
                entity_value['id'] = entity.get('id')
                data.append(entity_value)
        else:
            updated_data['id'] = self.filters[0].value
            data.append(updated_data)

        if self._is_via():
            self._store_via(data)
        else:
            created, output = self.connector.write(self.db_name, self.table_name, data)
            if created:
                return len(data)
            else:
                raise DatabaseError(output.get('results')[0].get('errors'))

    def delete(self):
        data = []
        if not self.connector._is_request_for_one_object(self.filters) or self._is_via():
            extra_fields = ['id']
            if self._is_via():
                extra_fields.append(self.via_fk_name)

            for entity in self.get(extra_fields=extra_fields).get(self.table_name):
                entity_obj = {'id': entity.get('id')}
                if self._is_via():
                    print entity
                    entity_obj[self.via_fk_name] = entity['%s@ref' % self.via_fk_name].split('/')[-1][:-5]
                data.append(entity_obj)

        else:
            data.append({'id': self.filters[0].value})

        if self._is_via():
            self._delete_via(data)
        else:
            self.connector.delete(self.db_name, self.table_name, data)
