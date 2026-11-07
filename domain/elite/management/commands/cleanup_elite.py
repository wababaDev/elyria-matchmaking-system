from django.core.management.base import BaseCommand

from domain.elite.services.elite_service import abandoned_cases, delete_abandoned


class Command(BaseCommand):
    help = "Delete Elite Grade applications abandoned for 30 days (never confirmed, or no documents recorded)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Only show how many would be deleted.")

    def handle(self, *args, **options):
        if options["dry_run"]:
            self.stdout.write(f"{abandoned_cases().count()} abandoned Elite application(s) would be deleted.")
            return
        self.stdout.write(self.style.SUCCESS(f"Deleted {delete_abandoned()} abandoned Elite application(s)."))