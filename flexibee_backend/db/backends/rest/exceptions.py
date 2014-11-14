from django.db.utils import DatabaseError


class FlexibeeResponseException(DatabaseError):

    def __init__(self, resp=None, url=None, msg=None):
        self.url = url
        self.message = msg
        self.resp = resp
        super(FlexibeeResponseException, self).__init__(self.message)

    def __str__(self):
        print self.resp
        if not self.resp:
            print 'a'
            return self.message
        else:
            print 'ted'
            return 'url: %s\nmessage: %s\nresponse content: %s' % (self.url, self.message, self.resp.content)


class FlexibeeDatabaseException(FlexibeeResponseException):

    def __init__(self, resp=None, url=None, msg=None):
        if resp:
            self.json_data = resp.json().get('winstrom')
        else:
            self.json_data = {'message': msg}
        super(FlexibeeDatabaseException, self).__init__(resp, url, msg)

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
        super(ChangesNotActivatedFlexibeeDatabaseException, self).__init__(resp, msg='Changes is not activated')


class SyncException(FlexibeeResponseException):

    def __init__(self, resp, url, msg=None):
        if not msg:
            msg = 'Company synchronization error'
        super(SyncException, self).__init__(resp, url, msg)

