from django.core.management.base import BaseCommand

from domain.elite.services.elite_service import abandoned_cases, cases_to_wipe, delete_abandoned, wipe_named_person


class Command(BaseCommand):
    help = (
        "Elite Grade clean-up: delete applications abandoned for 30 days, and delete the named person's "
        "details 30 days after a case closes. Run daily."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only show what would be deleted.")

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(f"{abandoned_cases().count()} abandoned application(s) would be deleted.")
            self.stdout.write(f"{cases_to_wipe().count()} closed case(s) would have the named person's details deleted.")
            return
        self.stdout.write(self.style.SUCCESS(f"Deleted {delete_abandoned()} abandoned application(s)."))
        self.stdout.write(self.style.SUCCESS(f"Deleted the named person's details on {wipe_named_person()} closed case(s)."))