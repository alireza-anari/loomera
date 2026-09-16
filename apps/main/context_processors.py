from .ui_feedback import pop_redirect_form_errors


def redirect_form_errors(request):
    """Expose one-shot field errors saved by POST endpoints that redirect."""

    return {"lm_redirect_form_errors": pop_redirect_form_errors(request)}
