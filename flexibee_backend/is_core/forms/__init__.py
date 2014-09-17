from django import forms
from django.utils.translation import ugettext_lazy as _

from is_core.forms import RestFormMixin

from flexibee_backend.is_core.forms.widgets import AttachementWidget, EmptyWidget


class FlexibeeItemForm(RestFormMixin, forms.Form):
    """
    Flexibee form for item creation and changes.
    """

    def __init__(self, instance=None, *args, **kwargs):
        self.instance = instance
        initial = kwargs.get('initial', {})
        if instance:
            kwargs['initial'] = self._get_initial(initial, instance)
        super(FlexibeeItemForm, self).__init__(*args, **kwargs)

    def _get_initial(self, initial, instance):
        raise NotImplementedError

    def save(self, commit=False):
        raise NotImplemented


class FlexibeeAttachmentForm(FlexibeeItemForm):
    """
    Form for adding attachement to flexibee models
    """

    file = forms.FileField(label=_('Attachment'), required=False, widget=AttachementWidget)
    link = forms.URLField(label=_('Link'), required=False)
    description = forms.CharField(label=_('Description'), required=False)

    def __init__(self, instance=None, *args, **kwargs):
        super(FlexibeeAttachmentForm, self).__init__(instance=instance, *args, **kwargs)
        if not instance:
            self.fields['link'].widget = EmptyWidget()
            self.fields['description'].widget = EmptyWidget()

    def _get_initial(self, initial, instance):
        initial['file'] = instance
        initial['link'] = instance.link
        initial['description'] = instance.description
        return initial

    def save(self, commit=False):
        description = self.cleaned_data.get('description')
        link = self.cleaned_data.get('link')
        if not self.instance:
            file = self.files.get('%s-file' % self.prefix)
            return self.parent.attachments.add(filename=file.name, content_type=file.content_type, file=file.file,
                                               description=description, link=link)

        self.instance.link = link
        self.instance.description = description

        return self.instance
