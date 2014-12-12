import hashlib

from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from flexibee_backend.db.backends.rest.exceptions import ChangesNotActivatedFlexibeeResponseError



class FlexibeeCachedDataWrapper(object):

    def __init__(self, data, version):
        self.data = data
        self.version = version


class FlexibeeDBVersionWrapper(object):

    def __init__(self, version=1, valid=True):
        self.timestamp = timezone.now()
        self.version = version
        self.valid = valid

    def invalidate(self):
        self.valid = False

    def is_valid(self):
        return self.valid and timezone.now() - timedelta(seconds=180) < self.timestamp


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
        hash_object = hashlib.sha1(value)
        return hash_object.hexdigest()

    def response_key(self):
        raise NotImplementedError

    def get_change_name(self):
        raise NotImplementedError


class ModelCacheKeysGenerator(CacheKeysGenerator):

    def __init__(self, db_name, table_name, filters=None, fields=None, relations=None, ordering=None, offset=0, base=0,
                 store_via_table_name=None):
        super(ModelCacheKeysGenerator, self).__init__(db_name, table_name)
        self.filters = self._unicode_and_sort(filters)
        self.fields = self._unicode_and_sort(fields)
        self.relations = self._unicode_and_sort(relations)
        self.ordering = self._unicode_and_sort(ordering, False)
        self.offset = unicode(offset)
        self.base = unicode(base)
        self.store_via_table_name = store_via_table_name

    def _unicode_and_sort(self, values, sort=True):
        values = map(unicode, values or [])
        if sort:
            values.sort()
        return values

    def response_key(self):
        key_parts = (
            self.db_name,
            self.table_name,
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
            self.extra
        )
        return self._hash('flexibee_response_%s_%s' % (self.name, '-'.join(key_parts)))

    def get_change_name(self):
        return self.name


class ResponseCache(object):

    def __init__(self, rest_connector, key_generator):
        self.rest_connector = rest_connector
        self.key_generator = key_generator

    def _load_version_from_flexibee(self, version_id):
        try:
            return self.rest_connector.changes(version_id)
        except ChangesNotActivatedFlexibeeResponseError:
            self.rest_connector.activate_changes()
            return 1

    def get_current_db_version(self):
        return cache.get(self.key_generator.version_key()) or FlexibeeDBVersionWrapper()

    def get_changes(self, version_from, db_version):
        if not db_version.is_valid():
            changes = cache.get(self.key_generator.version_changes_key(version_from, db_version.version))
            if changes is not None:
                return db_version.version, changes

        db_version_num, changes = self.rest_connector.changes(version_from)
        cache.set(self.key_generator.version_key(), FlexibeeDBVersionWrapper(version=db_version_num))
        cache.set(self.key_generator.version_changes_key(version_from, db_version_num), changes, 180)
        return db_version_num, changes

    def is_changed(self, cached_data):
        db_version = self.get_current_db_version()
        if cached_data.version != db_version.version or not db_version.is_valid():
            db_version_num, changes = self.get_changes(cached_data.version, db_version)
            if self.key_generator.get_change_name() not in changes:
                cached_data.version = db_version_num
                cache.set(self.key_generator.response_key(), cached_data)
                return False
            else:
                return True
        return False

    def clear(self):
        db_version = self.get_current_db_version()
        db_version.invalidate()
        cache.set(self.key_generator.version_key(), db_version)

    def get(self):
        cached_data = cache.get(self.key_generator.response_key())
        if cached_data and not self.is_changed(cached_data):
            return cached_data.data

    def add(self, data):
        cache.set(self.key_generator.response_key(), FlexibeeCachedDataWrapper(data,
                                                                               self.get_current_db_version().version))
