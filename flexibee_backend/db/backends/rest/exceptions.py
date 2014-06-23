from django.db.utils import DatabaseError


class FlexibeeDatabaseException(DatabaseError):

    def __init__(self, msg, resp):
        super(FlexibeeDatabaseException, self).__init__(msg)
        self.resp = resp
        self.json_data = resp.json().get('winstrom')

    def stat(self):
        return self.json_data.get('stat')

    @property
    def errors(self):
        errors = []
        for result in self.json_data.get('results'):
            if 'errors' in result:
                for error_dict in result.get('errors'):
                    errors.append(error_dict.get('message'))
        return '\n'.join(errors)


class ChangesNotActivatedFlexibeeDatabaseException(FlexibeeDatabaseException):

    def __init__(self, resp):
        super(ChangesNotActivatedFlexibeeDatabaseException, self).__init__('Changes is not activated', resp)
