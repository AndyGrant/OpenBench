from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_http_methods

from OpenBench.configuration import authorize, configuration_user_enabled, current_revision, save_configuration
from OpenBench.configuration_forms import ConfigurationForm
from OpenBench.models import ConfigurationRevision, EngineConfig, OpeningBook, SiteSettings
from OpenBench.views import render


SECTIONS = {'engines': ('Engines', EngineConfig), 'books': ('Books', OpeningBook),
    'site': ('Site settings', SiteSettings), 'history': ('History', ConfigurationRevision)}


@login_required(login_url='/login/')
@require_http_methods(['GET', 'POST'])
def manage(request, section='engines', identifier=None):
    if section not in SECTIONS or (section in ('site', 'history') and identifier is not None):
        raise Http404
    if not configuration_user_enabled(request.user) or (section != 'engines' and not request.user.is_superuser):
        raise PermissionDenied
    if not request.user.is_superuser and not EngineConfig.objects.filter(maintainers__user=request.user).exists():
        raise PermissionDenied
    title, model = SECTIONS[section]
    context = {'title': title, 'section': section,
        'navigation': [(key, label) for key, (label, _) in SECTIONS.items() if request.user.is_superuser or key == 'engines'],
        'singular': {'engines': 'engine', 'books': 'opening book'}.get(section, title.lower())}
    if section == 'site' or identifier is not None:
        if section == 'site':
            instance = get_object_or_404(SiteSettings, pk=1)
        elif identifier == 'new':
            instance = model()
        else:
            instance = get_object_or_404(model, pk=identifier)
        authorize(instance, request.user)
        form = ConfigurationForm(section, instance, current_revision().generation, request.user,
            request.POST if request.method == 'POST' else None)
        if request.method == 'POST' and form.is_valid():
            try:
                save_configuration(form.populate(), request.user, form.cleaned_data['generation'],
                    maintainers=form.cleaned_data.get('maintainers'))
            except ValidationError as error:
                form.add_error(None, error.messages)
            except IntegrityError:
                form.add_error(None, 'An entry with this name already exists. Reload before saving.')
            else:
                request.session['status_message'] = 'Configuration saved.'
                return redirect('configuration', section=section)
        context.update(form=form, instance=instance, is_new=instance._state.adding)
    else:
        if request.method != 'GET':
            raise PermissionDenied
        objects = model.objects.all()
        if section == 'history':
            objects = objects.select_related('actor').defer('snapshot')
        else:
            context['query'] = request.GET.get('q', '').strip()
            if context['query']:
                objects = objects.filter(name__icontains=context['query'])
            if section == 'engines':
                objects = objects.prefetch_related('maintainers__user')
                if not request.user.is_superuser:
                    objects = objects.filter(maintainers__user=request.user)
            context['can_add'] = request.user.is_superuser
        context['page'] = Paginator(objects, 30).get_page(request.GET.get('page'))
    return render(request, 'configuration.html', context)
