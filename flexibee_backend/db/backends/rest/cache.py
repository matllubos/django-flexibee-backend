from __future__ import unicode_literals

import hashlib
import sys

from django.core.cache import cache

from flexibee_backend.db.backends.rest.exceptions import ChangesNotActivatedFlexibeeResponseError


class FlexibeeCachedDataWrapper(object):

    def __init__(self, data, version):
        self.data = data
        self.version = version


class CacheKeysGenerator(object):

    def __init__(self, db_name, table_name):
        self.db_name = db_name
        self.table_name = table_name

    def version_key(self):
        return self._hash('flexibee_version_%s' % self.db_name)

    def version_changes_key(self, version_from, version_to):
        return self._hash('flexibee_version__changes_%s_%s_%s' % (self.db_name, version_from, version_to))

    def table_version_key(self):
        return self._hash('flexibee_version_%s_%s' % (self.db_name, self.table_name))

    def _hash(self, value):
        hash_object = hashlib.sha1(value.encode('utf-8'))
        return hash_object.hexdigest()

    def response_key(self):
        raise NotImplementedError

    def get_change_name(self):
        raise NotImplementedError


class ModelCacheKeysGenerator(CacheKeysGenerator):

    def __init__(self, db_name, table_name, filters=None, fields=None, relations=None, ordering=None, offset=0, base=0,
                 store_via_table_name=None, type='data'):
        super(ModelCacheKeysGenerator, self).__init__(db_name, table_name)
        self.filters = self._unicode_and_sort(filters)
        self.fields = self._unicode_and_sort(fields)
        self.relations = self._unicode_and_sort(relations)
        self.ordering = self._unicode_and_sort(ordering, False)
        self.offset = unicode(offset)
        self.base = unicode(base)
        self.store_via_table_name = store_via_table_name
        self.type = type

    def _unicode_and_sort(self, values, sort=True):
        values = map(unicode, values or [])
        if sort:
            values.sort()
        return values

    def response_key(self):
        key_parts = (
            self.db_name,
            self.table_name,
            self.type,
            self.offset,
            self.base,
            '(%s)' % '|'.join(self.filters),
            '(%s)' % '|'.join(self.fields),
            '(%s)' % '|'.join(self.relations),
            '(%s)' % '|'.join(self.ordering)
        )
        return self._hash('flexibee_response_%s' % '-'.join(key_parts))

    def get_change_name(self):
        return self.table_name


class ItemCacheKeysGenerator(CacheKeysGenerator):

    def __init__(self, name, db_name, table_name, extra=None):
        super(ItemCacheKeysGenerator, self).__init__(db_name, table_name)
        self.extra = unicode(extra or '')
        self.name = name

    def response_key(self):
        key_parts = (
            self.db_name,
            self.table_name,
            self.extra,
        )
        return self._hash('flexibee_response_%s_%s' % (self.name, '-'.join(key_parts)))

    def get_change_name(self):
        return self.name


class ResponseCache(object):

    # Static variable
    __versions = {}

    def __init__(self, rest_connector):
        self.rest_connector = rest_connector

    def _load_version_from_flexibee(self, version_id):
        try:
            return self.rest_connector.changes(version_id)
        except ChangesNotActivatedFlexibeeResponseError:
            self.rest_connector.activate_changes()
            return 1

    def _get_current_db_version(self, key_generator):
        db_version_num = self.__versions.get(key_generator.version_key())
        if not db_version_num:
            db_version_num, _ = self.rest_connector.changes(sys.maxint)
            self.__versions[key_generator.version_key()] = db_version_num
        return db_version_num

    def _get_changes(self, version_from, db_version, key_generator):
        changes = cache.get(key_generator.version_changes_key(version_from, db_version))
        if changes is not None:
            return db_version, changes

        db_version_num, changes = self.rest_connector.changes(version_from)
        self.__versions[key_generator.version_key()] = db_version_num
        cache.set(key_generator.version_changes_key(version_from, db_version_num), changes, 180)
        return db_version_num, changes

    def _is_changed(self, cached_data, key_generator):
        db_version = self._get_current_db_version(key_generator)
        if cached_data.version != db_version:
            db_version_num, changes = self._get_changes(cached_data.version, db_version, key_generator)
            self.__versions[key_generator.version_key()] = db_version_num
            if key_generator.get_change_name() not in changes:
                cached_data.version = db_version_num
                cache.set(key_generator.response_key(), cached_data)
                return False
            else:
                return True
        return False

    def clear(self, key_generator):
        self.__versions.pop(key_generator.version_key(), None)

    def reset(self):
        ResponseCache.__versions = {}

    def get(self, key_generator):
        cached_data = cache.get(key_generator.response_key())
        if cached_data and not self._is_changed(cached_data, key_generator):
            return cached_data.data

    def add(self, data, key_generator):
        cache.set(key_generator.response_key(),
            FlexibeeCachedDataWrapper(
                data, self._get_current_db_version(key_generator)
            )
        )
        return data
