from django.db import transaction

from domain.website.models import SiteDocument


@transaction.atomic
def replace_document(*, kind, file, by):
    """Swap in the new file and delete the old one from disk."""
    document = SiteDocument.current(kind)
    old_file = document.file if document else None

    if document is None:
        document = SiteDocument(kind=kind)
    document.file = file
    document.uploaded_by = by
    document.save()

    if old_file and old_file.name != document.file.name:
        transaction.on_commit(lambda: old_file.storage.delete(old_file.name))
    return document