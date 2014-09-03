from django.utils.translation import ugettext_lazy as _
from django import forms
from django.utils.safestring import mark_safe
from django.utils.http import urlquote

from is_core.forms import RestModelForm

from flexibee_backend.db.models.fields import Attachment


class PostM2MFormMixin(object):

    def post_save(self):
        pass

    def set_post_save(self, commit):
        if commit:
            self.post_save()
        else:
            self.old_save_m2m = self.save_m2m
            def post_save_m2m():
                self.old_save_m2m()
                self.post_save()
            self.save_m2m = post_save_m2m

    def save(self, commit=True):
        obj = super(PostM2MFormMixin, self).save(commit)
        self.set_post_save(commit)
        return obj


class FlexibeeAttachmentsModelForm(PostM2MFormMixin, RestModelForm):

    new_attachment = forms.FileField(label=_('New attachment'), required=False)
    existing_attachments = forms.MultipleChoiceField(label=_('Remove attachments'),
                                                     widget=forms.CheckboxSelectMultiple, required=False)

    def __init__(self, *args, **kwargs):
        super(FlexibeeAttachmentsModelForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['existing_attachments'].choices = [(attachment.pk, mark_safe('<a href="%s">%s</a>' %
                                                                                     (self.attachment_url(attachment),
                                                                                      attachment.filename)))
                                                           for attachment in self.instance.attachments.all()]

    def attachment_url(self, attachment):
        return 'attachment/%s__%s' % (attachment.pk, urlquote(attachment.filename))

    def post_save(self):
        print self.instance.flexibee_company_id
        for attachment in self.instance.attachments.all():
            if str(attachment.pk) in self.cleaned_data['existing_attachments']:
                attachment.delete()

        new_attachment = self.cleaned_data.get('new_attachment')
        if new_attachment:
            file = self.files.get('%s-new_attachment' % self.prefix)
            self.instance.attachments.create(Attachment(file.name, file.content_type, file=file.file))
