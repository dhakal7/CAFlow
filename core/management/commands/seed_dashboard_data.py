from django.core.management.base import BaseCommand
from core.services import seed_dashboard_demo_data, get_default_demo_firm


class Command(BaseCommand):
    help = "Seeds production-grade demo data for CAFlow Dashboard (128 clients, 24 tasks, 8 compliance, NPR 45K invoices)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Seeding CAFlow Dashboard demo data..."))
        firm = get_default_demo_firm()
        seed_dashboard_demo_data(firm=firm)
        self.stdout.write(self.style.SUCCESS(f"Successfully seeded demo data for firm: {firm.name} (128 clients, 24 tasks, 8 compliance, NPR 45K invoices)."))
