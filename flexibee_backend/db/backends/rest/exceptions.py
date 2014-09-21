from django.db.utils import DatabaseError


class FlexibeeDatabaseException(DatabaseError):

    def __init__(self, msg, resp, url=None):
        self.message = msg
        self.url = url
        if url:
            msg = '%s %s ' % (url, msg)
        self.resp = resp
        self.json_data = resp.json().get('winstrom')
        super(FlexibeeDatabaseException, self).__init__('%s errors: %s' % (msg, self.errors))

    def stat(self):
        return self.json_data.get('stat')

    @property
    def errors(self):
        errors = []

        if 'message' in self.json_data:
            errors.append(self.json_data.get('message'))

        if 'results' in self.json_data:
            for result in self.json_data.get('results'):
                if 'errors' in result:
                    for error_dict in result.get('errors'):
                        errors.append(error_dict.get('message'))
        return '\n'.join(errors)


class ChangesNotActivatedFlexibeeDatabaseException(FlexibeeDatabaseException):

    def __init__(self, resp):
        super(ChangesNotActivatedFlexibeeDatabaseException, self).__init__('Changes is not activated', resp)


class SyncException(FlexibeeDatabaseException):

    def __init__(self, msg, resp, url=None):
        if not msg:
            msg = 'Company synchronization error'
        super(SyncException, self).__init__(msg, resp, url)
