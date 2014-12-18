from django.views.generic.base import View
from django.core.exceptions import ObjectDoesNotExist
from django.http.response import Http404

from is_core.generic_views import DefaultCoreViewMixin

from chamber.shortcuts import get_object_or_404


class AttachmentFileView(DefaultCoreViewMixin, View):

    def get_obj(self):
        return get_object_or_404(self.core.get_queryset(self.request), pk=self.request.kwargs.get('pk'))

    def get(self, request, *args, **kwargs):
        try:
            return self.get_obj().attachments.get(self.request.kwargs.get('attachment_pk')).file_response
        except ObjectDoesNotExist:
            raise Http404

    def has_get_permission(self, **kwargs):
        return self.core.has_read_attachment_permission(self.request, self.get_obj())
