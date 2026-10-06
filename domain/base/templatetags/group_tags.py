from django import template

from domain.base.services.groups import in_groups

register = template.Library()


@register.filter
def has_group(user, name):
    return in_groups(user, name)


@register.filter
def has_any_group(user, names):
    return in_groups(user, *[n.strip() for n in names.split(",")])