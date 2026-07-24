from django.core.management.base import BaseCommand

from apps.salons.membership import sync_legacy_membership, ensure_salon_verification
from apps.salons.models import Salon, SalonMembershipStatus
from apps.stylists.models import JobDetails


class Command(BaseCommand):
    help = "Create SalonMembership records from legacy Salon.stylists and JobDetails relations."

    def handle(self, *args, **options):
        created_or_synced = 0
        verification_count = 0
        for salon in Salon.objects.prefetch_related("stylists").all().iterator(chunk_size=200):
            ensure_salon_verification(salon)
            verification_count += 1
            stylist_ids = set(salon.stylists.values_list("pk", flat=True))
            stylist_ids.update(
                JobDetails.objects.filter(salon_id=salon.pk).values_list("stylist_id", flat=True)
            )
            for stylist_id in stylist_ids:
                if not stylist_id:
                    continue
                stylist = salon.stylists.model.objects.filter(pk=stylist_id).first()
                if stylist is None:
                    continue
                sync_legacy_membership(
                    salon=salon,
                    stylist=stylist,
                    status=SalonMembershipStatus.ACTIVE,
                )
                created_or_synced += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Synced {created_or_synced} salon memberships and {verification_count} salon verifications."
            )
        )
