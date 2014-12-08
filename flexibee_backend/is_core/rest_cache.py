from django.db.transaction import get_connection

from piston.cache import DefaultRestCache

from flexibee_backend import config
from flexibee_backend.db.backends.rest.exceptions import ChangesNotActivatedFlexibeeResponseError


class FlexibeeCachedResponseWrapper(object):

    def __init__(self, response, version):
        self.response = response
        self.version = version


class FlexibeeDefaultRestCache(DefaultRestCache):

    def _cache_response(self, request, response):
        self._get_cache().set(self._get_key(request), FlexibeeCachedResponseWrapper(response,
                                                                                    self._get_changes_version()))

    def _get_response(self, request):
        response_wrapper = self._get_cache().get(self._get_key(request))

        if response_wrapper:
            version = self._get_changes_version()
            if version >= 0 and version <= response_wrapper.version:
                return response_wrapper.response
            else:
                self._get_cache().delete(self._get_key(request))

    def _get_changes_version(self):
        try:
            return get_connection(config.FLEXIBEE_BACKEND_NAME).connector.changes(1)
        except ChangesNotActivatedFlexibeeResponseError:
            get_connection(config.FLEXIBEE_BACKEND_NAME).connector.activate_changes()
            return -1
