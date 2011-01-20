from django.conf.urls.defaults import patterns, url

from feedback import OPINION_PRAISE, OPINION_ISSUE, OPINION_SUGGESTION


urlpatterns = patterns('feedback.views',
    # TODO: combine all beta feedback submissions into beta/feedback.
    # Bug 623364.
    url(r'^happy/?', 'give_feedback', {'type': OPINION_PRAISE},
        name='feedback.happy'),
    url(r'^sad/?', 'give_feedback', {'type': OPINION_ISSUE},
        name='feedback.sad'),
    url(r'^suggestion/?', 'give_feedback', {'type': OPINION_SUGGESTION},
        name='feedback.suggestion'),

    url(r'^thanks/?', 'thanks', name='feedback.thanks'),

    url(r'^feedback/?', 'feedback', name='feedback'),

    url(r'^download/?', 'download', name='feedback.download'),

    # TODO Should this be under beta/release/etc.?
    url(r'^opinion/(?P<id>\d+)$', 'opinion_detail', name='opinion.detail'),
)
