"""
Starting values for Hold Time: Silver 6 weeks, Gold 10 weeks. Bronze and Elite stay off.
Admin can change them any time in Settings → Membership tiers.
"""
from django.db import migrations

DEFAULTS = {"silver": 6, "gold": 10}


def set_defaults(apps, schema_editor):
    Tier = apps.get_model("matchmaking", "MembershipTier")
    for name, weeks in DEFAULTS.items():
        Tier.objects.filter(name__iexact=name).update(allows_hold=True, hold_weeks=weeks)


class Migration(migrations.Migration):
    dependencies = [
        ("matchmaking", "0028_membership_hold_term_start_and_more"),
    ]

    operations = [
        migrations.RunPython(set_defaults, migrations.RunPython.noop),
    ]