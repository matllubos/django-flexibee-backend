from django import forms
from django.utils.translation import ugettext_lazy as _

from is_core.forms import RestFormMixin

from flexibee_backend.is_core.forms.widgets import AttachementWidget


class FlexibeeAttachmentForm(RestFormMixin, forms.Form):

    attachment = forms.FileField(label=_('New attachment'), required=False, widget=AttachementWidget)

    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        if instance:
            kwargs['initial'] = {'attachment': instance}
        super(FlexibeeAttachmentForm, self).__init__(*args, **kwargs)


    def save(self, commit=False):

        file = self.files.get('%s-attachment' % self.prefix)
        if file:
            return self.parent.attachments.add(filename=file.name, content_type=file.content_type, file=file.file)
        return self.instance
