from functools import wraps

from django import http
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.vary import vary_on_headers

import jingo
from product_details.version_compare import Version
from tower import ugettext as _

import input
from input.decorators import cache_page, forward_mobile
from input.urlresolvers import reverse
from feedback.forms import PraiseForm, IssueForm, IdeaForm
from feedback.models import Opinion
from feedback.utils import detect_language, ua_parse


def enforce_ua(f):
    """
    View decorator enforcing feedback from the right (latest beta, latest
    release) users only.

    Can be disabled with settings.ENFORCE_USER_AGENT = False.
    """
    @wraps(f)
    def wrapped(request, *args, **kwargs):
        # Validate User-Agent request header.
        ua = request.META.get('HTTP_USER_AGENT', None)
        parsed = ua_parse(ua)

        if not parsed:  # Unknown UA.
            if request.method == 'GET':
                return http.HttpResponseRedirect(
                        reverse('feedback.download'))
            else:
                return http.HttpResponseBadRequest(
                    _('User-Agent request header must be set.'))

        if not settings.ENFORCE_USER_AGENT:
            return f(request, ua=ua, *args, **kwargs)

        this_ver = Version(parsed['version'])
        ref_ver = Version(input.LATEST_RELEASE[parsed['browser']])
        # Check for outdated release.
        if this_ver < ref_ver:
            return http.HttpResponseRedirect(reverse('feedback.download'))

        # If we made it here, it's a valid version.
        return f(request, ua=ua, *args, **kwargs)

    return wrapped

@vary_on_headers('User-Agent')
@cache_page
def feedback_mobile(request, ua):
    """
    The index page for mobile feedback, which shows links to the happy
    and sad feedback pages.
    """
    return jingo.render(request, 'feedback/mobile/beta_index.html')


@forward_mobile
@enforce_ua
@never_cache
@csrf_exempt
def give_feedback(request, ua, type):
    """Submit feedback page."""

    # We are only temporarily supporting the old mobile pages for now,
    # desktop should never hit this view
    if not request.mobile_site:
        url = {
            input.OPINION_PRAISE.id: '/feedback#happy',
            input.OPINION_ISSUE.id: '/feedback#sad',
            input.OPINION_IDEA.id: '/feedback#idea',
        }[type]
        return http.HttpResponseRedirect(url)

    try:
        FormType = {
            input.OPINION_PRAISE.id: PraiseForm,
            input.OPINION_ISSUE.id: IssueForm,
            input.OPINION_IDEA.id: IdeaForm
        }[type]
    except KeyError:
        return http.HttpResponseBadRequest(_('Invalid feedback type'))

    if request.method == 'POST':
        form = FormType(request.POST)
        if form.is_valid():
            # Save to the DB.
            save_opinion_from_form(request, type, ua, form)

            return http.HttpResponseRedirect(reverse('feedback.thanks'))

    else:
        # URL is fed in by the feedback extension.
        url = request.GET.get('url', '')
        form = FormType(initial={'url': url, 'add_url': False, 'type': type})

    # Set the div id for css styling
    div_id = 'feedbackform'
    if type == input.OPINION_IDEA.id:
        div_id = 'ideaform'

    url_idea = request.GET.get('url', 'idea')
    data = {
        'form': form,
        'type': type,
        'div_id': div_id,
        'MAX_FEEDBACK_LENGTH': input.MAX_FEEDBACK_LENGTH,
        'url_idea': url_idea
    }
    template = ('feedback/mobile/feedback.html' if request.mobile_site else
                'feedback/feedback.html')
    return jingo.render(request, template, data)


@forward_mobile
@enforce_ua
@never_cache
@csrf_exempt
def feedback(request, ua):
    """Page to receive feedback under happy/sad/idea categories"""

    # TODO: Implement new designs on mobile so we can use this view there
    # We are temporarily supporting the old mobile site
    if request.mobile_site:
        return feedback_mobile(request, ua)

    if request.method == 'POST':
        typ = int(request.POST.get('type'))

        if typ == input.OPINION_PRAISE.id:
            form = PraiseForm(request.POST, auto_id='happy-%s')
        elif typ == input.OPINION_ISSUE.id:
            form = IssueForm(request.POST, auto_id='sad-%s')
        else:
            form = IdeaForm(request.POST, auto_id='idea-%s')

        if form.is_valid():
            save_opinion_from_form(request, typ, ua, form)

            url = reverse('feedback.thanks')
            return http.HttpResponseRedirect(url)
        else:
            forms = {'happy': (form if typ == input.OPINION_PRAISE.id else
                               PraiseForm(auto_id='happy-%s')),
                     'sad': (form if typ == input.OPINION_ISSUE.id else
                             IssueForm(auto_id='sad-%s')),
                     'idea': (form if typ == input.OPINION_IDEA.id else
                              IdeaForm(auto_id='idea-%s'))}
    else:
        forms = {'happy': PraiseForm(auto_id='happy-%s'),
                 'sad': IssueForm(auto_id='sad-%s'),
                 'idea': IdeaForm(auto_id='idea-%s')}

    return jingo.render(request, 'feedback/index.html',
                        {'forms': forms, 'post_url': reverse('feedback')})


@cache_page
def download(request):
    """Encourage people to download a current version."""

    template = 'feedback/%sdownload.html' % (
        'mobile/' if request.mobile_site else '')
    return jingo.render(request, template)


@cache_page
def thanks(request):
    """Thank you for your feedback."""

    template = 'feedback/%sthanks.html' % (
        'mobile/' if request.mobile_site else '')
    return jingo.render(request, template)


@cache_page
def opinion_detail(request, id):
    o = get_object_or_404(Opinion, pk=id)
    return jingo.render(request, 'feedback/opinion.html', {'opinion': o})


def save_opinion_from_form(request, type, ua, form):
    """Given a (valid) form and feedback type, save it to the DB."""
    locale = detect_language(request)

    # Remove URL if checkbox disabled or no URL submitted. Broken Website
    # report does not have the option to disable URL submission.
    if (type != input.OPINION_BROKEN.id and
        not (form.cleaned_data.get('add_url', False) and
             form.cleaned_data.get('url'))):
        form.cleaned_data['url'] = ''

    if type not in input.OPINION_TYPES:
        raise ValueError('Unknown type %s' % type)

    return Opinion(
        type=type,
        url=form.cleaned_data.get('url', ''),
        description=form.cleaned_data['description'],
        user_agent=ua, locale=locale,
        manufacturer=form.cleaned_data['manufacturer'],
        device=form.cleaned_data['device']).save()
