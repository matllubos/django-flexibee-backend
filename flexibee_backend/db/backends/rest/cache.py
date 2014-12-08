from django.core.cache import cache
from flexibee_backend.db.backends.rest.exceptions import ChangesNotActivatedFlexibeeResponseError



class FlexibeeCachedResponseWrapper(object):

    def __init__(self, response, version):
        self.response = response
        self.version = version


class KeyGenerator(object):

    def __init__(self, rest_connector):
        self.rest_connector = rest_connector

    def version_key(self):
        return 'flexibee_version_%s' % self.rest_connector.db_name

    def response_key(self):
        


class ResponseCache(object):

    def __init__(self, rest_connector):
        self.rest_connector = rest_connector
        self.key_generator = KeyGenerator(rest_connector)

    def _load_version_from_flexibee(self):
        try:
            return self.rest_connector.changes(1)
        except ChangesNotActivatedFlexibeeResponseError:
            self.rest_connector.activate_changes()
            return -1

    def get_current_db_version(self):
        db_version = cache.get(self.key_generator.version_key())
        if not db_version:
            db_version = self._load_version_from_flexibee()
            if not db_version == -1:
                cache.set(self.key_generator.version_key(), db_version, 60)
        return db_version
