from django.utils.translation import ugettext_lazy as _
from django import forms
from django.utils.safestring import mark_safe

from is_core.forms import RestModelForm

from flexibee_backend.db.models.fields import Attachement


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


class FlexibeeAttachementsModelForm(PostM2MFormMixin, RestModelForm):

    new_attachement = forms.FileField(label=_('New attachement'), required=False)
    existing_attachements = forms.MultipleChoiceField(label=_('Remove attachements'), choices=((1, 'a'), (2, 'b')),
                                                      widget=forms.CheckboxSelectMultiple, required=False)

    def __init__(self, *args, **kwargs):
        super(FlexibeeAttachementsModelForm, self).__init__(*args, **kwargs)
        self.fields['existing_attachements'].choices = [(attachement.pk, mark_safe('<a href="%s">%s</a>' %
                                                                                   (self.attachement_url(attachement),
                                                                                    attachement.filename)))
                                                        for attachement in self.instance.attachements.all()]

    def attachement_url(self, attachement):
        return 'attachement/%s' % attachement.pk

    def post_save(self):
        for attachement in self.instance.attachements.all():
            if str(attachement.pk) in self.cleaned_data['existing_attachements']:
                attachement.delete()

        new_attachement = self.cleaned_data.get('new_attachement')
        if new_attachement:
            file = self.files.get('%s-new_attachement' % self.prefix)
            self.instance.attachements.create(Attachement(file.name, file.content_type, file=file.file))
